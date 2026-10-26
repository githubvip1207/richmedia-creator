"""离线请求与报价夹具；只构造原生输入，校验和计算全部调用实际脚本。"""
import copy
from pathlib import Path
from core import submission_store as store
from core.cost_quote import billing_inputs
from core.catalogs import CATALOGS
from providers import calculate_inputs, compile_request as compile_native
from core.media_probe import probe_asset


def as_native(spec):
    """把测试中的简写展开为原生请求；此处不实现业务校验或提示词优化。"""
    if 'payload' in spec:
        return copy.deepcopy(spec)
    provider, operation = spec['provider'], spec['operation']
    model = spec['model']
    models = CATALOGS[provider]['models']
    model_id = models.get(model, {}).get('id', model)
    alias = next((key for key, value in models.items() if value['id'] == model_id), model)
    options = copy.deepcopy(spec.get('parameters', {}))
    prompt = spec.get('prompt', '拆分图片中的主要元素')
    result = {key: copy.deepcopy(value) for key, value in spec.items()
              if key in ('provider', 'operation', 'mode', 'estimate_context', 'target_asset_id',
                         'budget_cny', 'budget_usd', 'fx')}
    result['original_prompt'] = spec.get('original_prompt', prompt)
    if operation in ('text-to-image', 'image-to-image', 'decompose-layers'):
        body = dict(model=model_id, prompt=prompt, size=options.pop('size', '1K'),
                    output_format='png', response_format='url', watermark=False,
                    background='opaque', layer_decomposition=operation == 'decompose-layers')
        options.pop('ratio', None)
        body.update(options)
    else:
        # 固定测试规格用于独立核对公式，不代表产品默认值。
        locked = operation == 'image-to-video' or spec.get('mode') in ('edit', 'before', 'after')
        body = dict(model=model_id, content=[{'type': 'text', 'text': prompt}],
                    resolution='480p', ratio='adaptive' if locked else '16:9',
                    duration=-1 if alias == 'seedance-2.5' and spec.get('mode') == 'edit' else 4,
                    generate_audio=False, watermark=False, return_last_frame=False)
        if alias == 'seedance-2.5':
            body['output_format'] = 'mp4'
            if operation in ('reference-to-video', 'extend-video'):
                body['omni_reference_task_type'] = 'extend' if operation == 'extend-video' else spec['mode']
        body.update(options)
    result['payload'] = body
    if operation not in ('text-to-image', 'text-to-video'):
        result['assets'] = [dict(id=asset.get('id', 'asset-' + str(index)), kind=asset['kind'],
                                 source=asset['source'], purpose=asset['purpose'])
                            for index, asset in enumerate(spec.get('assets', []))]
    return result


def measurements(spec, native):
    """远程素材使用明确的离线测量夹具，本地素材通过真实探测读取。"""
    result = []
    for index, asset in enumerate(native.get('assets', [])):
        original = spec.get('assets', [])[index]
        if Path(asset['source']).is_absolute():
            metadata = probe_asset({key: asset[key] for key in ('id', 'kind', 'source')})['metadata']
        else:
            metadata = dict(width=1280, height=720, bytes=200, mime='image/png')
            if asset['kind'] in ('video', 'audio'):
                metadata.update(duration=8, format_name='mov,mp4' if asset['kind'] == 'video' else 'wav',
                                codec_name='h264' if asset['kind'] == 'video' else 'pcm_s16le', frame_rate=24)
            metadata.update(original.get('metadata', {}))
        result.append({**asset, 'metadata': metadata})
    return result


def compile_request(spec):
    native = as_native(spec)
    measured = measurements(spec, native)
    flat = [{key: value for key, value in asset.items() if key not in ('metadata', 'purpose')}
            | asset['metadata'] for asset in measured]
    return compile_native(native, flat)


def calculate(spec, pricing=None):
    compiled = compile_request(spec)
    return calculate_inputs(billing_inputs(compiled), pricing, spec.get('estimate_context'),
                            spec.get('fx'), compiled['assets'])


def save_requirement(spec, out, compiled=None):
    compiled = compiled or compile_request(spec)
    record = store.read(out/'request.json') if (out/'request.json').exists() else {'providers': {}}
    native = as_native(spec)
    selected = dict(model=compiled['payload_template']['model'], operation=native['operation'],
                    parameters=copy.deepcopy(compiled['parameters']),
                    assets=[{'id': asset['id']} for asset in native.get('assets', [])])
    for key in ('mode', 'estimate_context'):
        if key in native:
            selected[key] = copy.deepcopy(native[key])
    record.update(original_prompt=native['original_prompt'], optimized_prompt=compiled['prompt'],
                  intent={'operation': native['operation']}, assets=native.get('assets', []))
    if 'target_asset_id' in native:
        record['target_asset_id'] = native['target_asset_id']
    record['providers'][native['provider']] = selected
    store.write(out/'request.json', record)


def save_with_cost(spec, out, pricing=None):
    out.mkdir(parents=True, exist_ok=True)
    compiled = compile_request(spec)
    quote = calculate_inputs(billing_inputs(compiled), pricing, spec.get('estimate_context'),
                             spec.get('fx'), compiled['assets'])
    native = as_native(spec)
    store.write(out/(native['provider']+'-priceing.json'), quote)
    save_requirement(native, out, compiled)
    store.write(out/'task-spec.json', native)
    return native
