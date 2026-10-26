"""离线请求与报价测试数据，不使用真实凭证或网络请求。"""
import copy
from core import submission_store as store
from core.cost_quote import billing_inputs
from providers import calculate_inputs
from providers import compile_request
from legacy_request import compile_request as compile_legacy


def as_native(spec):
    if 'payload' in spec:
        return copy.deepcopy(spec)
    compiled = compile_legacy(spec)
    body = copy.deepcopy(compiled['payload_template'])
    if compiled['operation'] == 'text-to-image':
        # 新提交原样保留提示词，不沿用旧版编译器追加的内容。
        body['prompt'] = spec['prompt']
        body.pop('optimize_prompt_options', None)
    if compiled['assets']:
        if compiled['kind'] == 'image':
            body['image'] = [a['source'] for a in compiled['assets']]
        else:
            for item in body['content']:
                for key in ('image_url', 'video_url', 'audio_url'):
                    if key in item:
                        item[key]['url'] = compiled['assets'][item[key]['url']['asset_index']]['source']
    result = {k: copy.deepcopy(v) for k, v in spec.items() if k in
              ('provider', 'operation', 'mode', 'optimizer', 'estimate_context', 'budget_cny', 'budget_usd', 'fx')}
    result.update(original_prompt=spec.get('original_prompt', spec.get('prompt', '')), payload=body)
    return result


def calculate(spec, pricing=None):
    compiled = compile_legacy(spec)
    return calculate_inputs(billing_inputs(compiled), pricing, spec.get('estimate_context'),
                            spec.get('fx'), compiled['assets'])


def save_requirement(spec, out, compiled=None):
    compiled = compiled or compile_request(spec)
    record = store.read(out/'request.json') if (out/'request.json').exists() else {'providers': {}}
    parameters = {k: v for k, v in compiled['parameters'].items() if k in
                  ('size', 'resolution', 'ratio', 'duration', 'output_format', 'response_format', 'watermark', 'background', 'layer_decomposition')}
    record.update(original_prompt=spec.get('original_prompt'), optimized_prompt=compiled['prompt'],
                  intent={'operation': spec['operation']}, assets=[])
    record['providers'][spec['provider']] = {'model': compiled['payload_template']['model'],
             'operation': spec['operation'], 'parameters': parameters, 'assets': []}
    store.write(out/'request.json', record)


def save_with_cost(spec, out, pricing=None):
    out.mkdir(parents=True, exist_ok=True)
    quote = calculate(spec, pricing)
    compiled = compile_legacy(spec)
    native = as_native(spec)
    store.write(out/(spec['provider']+'-priceing.json'), quote)
    save_requirement(native, out, compiled if 'payload' not in spec else None)
    # 准确保存原生请求正文实际提交的提示词，不保存旧版编译器追加的文本。
    record = store.read(out/'request.json')
    record['optimized_prompt'] = native['payload'].get('prompt', next((x['text'] for x in native['payload'].get('content',[]) if x['type']=='text'), ''))
    store.write(out/'request.json', record)
    store.write(out/'task-spec.json', native)
    return native
