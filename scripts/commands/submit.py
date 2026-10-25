"""submit: validate the confirmed plan, persist it, then POST exactly once."""
import copy
import json
from pathlib import Path
from core.request import require
from core.cost_quote import consume_quote
from core.cost_record import amount_in
from core.envfile import config_value
from core.dependencies import require_dependencies
from core.operations import require_supported_operation
from core.submission_store import read, write, lock, prior_submission, next_submit_record, now
from providers import get_provider
from providers.transport import ProviderError, response_error, sanitize_response


def validate_requirement(directory, spec, compiled):
    """Bind the submitted content and settings to the current requirement record."""
    record = read(directory / 'request.json')
    require(isinstance(record, dict), 'request.json must be an object')
    require(isinstance(record.get('intent'), dict) and record['intent'].get('operation') == spec['operation'],
            'Submission operation differs from request.json; update the plan and reconfirm')
    require(isinstance(record.get('optimized_prompt'), str) and compiled['prompt'] == record['optimized_prompt'],
            'Submission prompt differs from request.json optimized_prompt; update the plan and reconfirm')
    require(spec.get('original_prompt') == record.get('original_prompt') and isinstance(record.get('original_prompt'), str),
            'Submission original_prompt differs from request.json')
    require(isinstance(record.get('providers'), dict), 'Supplier plans missing from request.json')
    selected = record['providers'].get(compiled['provider'])
    require(isinstance(selected, dict), 'Selected supplier is absent from request.json')
    from core.request import CATALOGS
    expected_model = selected.get('model')
    models = CATALOGS[compiled['provider']]['models']
    expected_model = models.get(expected_model, {}).get('id', expected_model)
    require(expected_model == compiled['payload_template']['model'] and selected.get('operation') == spec['operation'],
            'Submission model/operation differs from request.json; update the plan and reconfirm')
    parameters = selected.get('parameters')
    require(isinstance(parameters, dict), 'Supplier parameters missing from request.json')
    default_tools = ([{'type': 'web_search'}]
                     if compiled['kind'] == 'video' and compiled['provider'] == 'volcengine' else [])
    for key, value in parameters.items():
        # Image composition preferences live in the unchanged prompt, not an API ratio field.
        if compiled['kind'] == 'image' and key == 'ratio':
            size = compiled['parameters']['size']
            if 'x' in size:
                try:
                    width, height = map(int, size.split('x'))
                    numerator, denominator = map(int, value.split(':'))
                except (ValueError, AttributeError):
                    raise ValueError('Invalid image ratio in request.json') from None
                require(width * denominator == height * numerator, 'Pixel dimensions differ from request.json ratio')
            continue
        if compiled['kind'] == 'video' and key == 'tools':
            require(compiled['parameters'].get('tools', []) == value,
                    'Submission search settings differ from request.json; update and reconfirm')
            continue
        require(compiled['parameters'].get(key) == value,
                'Submission parameter ' + key + ' differs from request.json; update the plan and reconfirm')
    if compiled['kind'] == 'video':
        require(parameters.get('tools', default_tools) == compiled['parameters'].get('tools', default_tools),
                'Submission search settings differ from request.json; update and reconfirm')
        required = {'resolution', 'duration', 'generate_audio'}
        if compiled['operation'] == 'text-to-video':
            required.add('ratio')
        require(required <= set(parameters),
                'Video decision parameters missing from request.json; update the plan and reconfirm')
    if compiled['kind'] in ('image', 'video'):
        if compiled['kind'] == 'image':
            require('size' in parameters, 'Image size missing from request.json supplier parameters')
        if spec['operation'] in ('text-to-image', 'text-to-video'):
            require(selected.get('assets') == [], 'Text generation supplier assets must be empty')
        else:
            catalog = record.get('assets')
            refs = selected.get('assets')
            require(isinstance(catalog, list) and all(isinstance(a, dict) for a in catalog),
                    'Image asset catalog missing from request.json')
            ids = [a.get('id') for a in catalog]
            require(all(isinstance(i, str) and i.strip() for i in ids) and len(set(ids)) == len(ids),
                    'Image asset ids must be unique nonempty strings')
            require(isinstance(refs, list) and all(isinstance(a, dict) and set(a) == {'id'} for a in refs),
                    'Supplier assets must contain ordered id references')
            by_id = {a['id']: a for a in catalog}
            require(all(a['id'] in by_id for a in refs), 'Unknown supplier asset reference')
            expected = [by_id[a['id']] for a in refs]
            actual = compiled['assets']
            require(len(expected) == len(actual) and all(
                e.get('kind') == a['kind'] and e.get('source') == a['source']
                and e.get('id') == a.get('id') and e.get('purpose') == a.get('purpose')
                for e, a in zip(expected, actual)),
                'Submission assets/order differ from request.json or cost artifact; update and reconfirm')



def submit(jobdir, spec, approval_text, accept_uncertain=False):
    d = Path(jobdir).resolve()
    require(bool(approval_text.strip()), 'Record the actual user confirmation; never manufacture approval')
    submitted_input = copy.deepcopy(spec)
    with lock(d):
        prior_submission(d)
        require(isinstance(spec,dict) and bool(spec.get('provider')), 'Select an explicit supplier in the task request')
        get_provider(spec['provider'])
        require_supported_operation(spec)
        cost = read(d/(spec['provider'] + '-priceing.json'))
        spec, compiled, pricing, estimate = consume_quote(spec,cost)
        for unit in ('cny','usd'):
            if spec.get('budget_'+unit) is not None:
                upper = amount_in(estimate, unit.upper())['max']
                require(upper is not None, 'Cannot compare budget with unknown amount/conversion')
                require(upper <= spec['budget_'+unit], 'Estimated amount exceeds budget; revise the request')
        validate_requirement(d, spec, compiled)
        require_dependencies()
        plan = {'compiled':compiled,'estimate':estimate}
        info = get_provider(plan['compiled']['provider'])
        adapter = info['adapter']
        if plan['estimate']['amount']['max'] is None:
            require(accept_uncertain, 'Cost upper estimate unknown; require explicit user acceptance of uncertainty')
        require(bool(config_value(adapter.KEY_ENV)), adapter.KEY_ENV + ' is not configured')
        # 先在本地转换素材，检查素材可读性后才记录付费尝试；Base64 正文不写日志。
        # Materialize before recording a paid attempt, but never log Base64 payloads.
        payload = adapter.payload(plan)
        require(len(json.dumps(payload,ensure_ascii=False).encode()) <= 64*1024*1024, 'Request exceeds 64 MB')
        # 先落盘 submitting，再开始网络操作；崩溃或中断也留下不可重复提交的审计记录。
        state = {'state':'submitting', 'created_at':now(), 'compiled':compiled,
                 'approval':{'text':approval_text,'recorded_at':now(),'accept_uncertain_cost':accept_uncertain},
                 'provider':plan['compiled']['provider'],'model':plan['compiled']['model'], 'task_id':None}
        record_path = next_submit_record(d)
        state['submission'] = str(record_path)
        record = {**submitted_input, 'response': None, 'execution': state}
        write(d/'payload.json', submitted_input)
        write(record_path, record)
        try:
            # 本模块唯一的付费网络入口：一次 POST，没有重试循环，也没有备用供应商分支。
            # The only paid network action in this module; exactly one POST, never retried.
            endpoint = '/images/generations' if plan['compiled']['kind'] == 'image' else '/contents/generations/tasks'
            result = adapter.request('POST',endpoint,payload)
            result = sanitize_response(result, secrets=(compiled['prompt'],))
            record['response'] = result
            write(record_path, record)
            if result.get('error'):
                raise response_error(result['error'], provider_name=info['name'], secrets=(compiled['prompt'],))
            # 视频响应只代表任务已创建，进入 queued；图片响应为同步结果，但仍逐项检查错误。
            if plan['compiled']['kind'] == 'video':
                require(isinstance(result.get('id'),str) and bool(result['id']), 'POST response did not contain task ID')
                state.update(state='queued',task_id=result['id'])
            else:
                from commands.status import image_response_state
                state.update(image_response_state(result, compiled))
        # 有不确定性的供应商错误或响应处理异常保留 submission_unknown；明确拒绝才记 rejected。
        except Exception as exc:
            state.update(state='submission_unknown' if not isinstance(exc,ProviderError) or exc.uncertain else 'rejected',
                         error=str(exc) if isinstance(exc,(ValueError,ProviderError)) else type(exc).__name__)
            if isinstance(exc, ProviderError) and exc.details is not None:
                record['response'] = {'error': exc.details}
            write(record_path, record)
            raise
        state['updated_at'] = now()
        write(record_path, record)
        return state


def run(args):
    import sys
    if args.request:
        spec = read(args.request)
    else:
        require(not sys.stdin.isatty(), 'Supply the request JSON object on stdin')
        def reject_constant(value):
            raise ValueError('Invalid JSON numeric constant: ' + value)
        spec = json.loads(sys.stdin.read(), parse_constant=reject_constant)
        require(isinstance(spec, dict), 'Request input must be a JSON object')
    state = submit(args.workdir, spec, args.approval_text, args.accept_uncertain_cost)
    return {'submission': state['submission']}
