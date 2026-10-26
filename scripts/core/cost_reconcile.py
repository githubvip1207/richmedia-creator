"""按实际 API 用量和输出规格核对预估；刊例价核算与真实账单分开。"""

import math
import struct
from pathlib import Path


def difference(actual, bounds):
    if not bounds or bounds.get('min') is None or bounds.get('max') is None:
        return None
    lo, hi = bounds['min'], bounds['max']
    reference = lo if actual < lo else hi if actual > hi else actual
    return round((actual - reference) / reference * 100, 3) if reference else None


def image_dimensions(path):
    with open(path, 'rb') as stream:
        head = stream.read(24)
    if head[:8] == b'\x89PNG\r\n\x1a\n' and head[12:16] == b'IHDR':
        return list(struct.unpack('>II', head[16:24]))
    from core.media_probe import probe_asset
    m = probe_asset({'kind': 'image', 'source': str(Path(path).resolve())})['metadata']
    return [m['width'], m['height']]


def reconcile(record, usage, manifest):
    quote = record.get('execution', {}).get('cost_record')
    if not quote:
        return {'status': 'unavailable', 'reason': '历史提交未保存报价快照，无法可靠还原预估。'}
    c, estimate = quote['calculation'], quote['result']
    compiled = record['execution']['compiled']
    out = {'status': 'compared', 'currency': estimate['currency'],
           'estimated_amount': estimate['amount'], 'outputs': [],
           'actual_billed_amount': None,
           'basis': '按提交时刊例单价与实际用量核算，不代表账户实付账单。'}
    if compiled['kind'] == 'video':
        tokens = (usage or {}).get('completion_tokens')
        if type(tokens) is int and tokens >= 0:
            actual = round(tokens * c['unit_price_per_million_tokens'] / 1_000_000, 6)
            out.update(actual_tokens=tokens, estimated_tokens=c.get('tokens'),
                       usage_cost_at_list_price=actual,
                       difference_percent_outside_estimate=difference(actual, estimate['amount']),
                       token_difference_percent_outside_estimate=difference(
                           tokens, dict(zip(('min', 'max'), c['tokens']))) if c.get('tokens') else None)
        else:
            out.update(status='partial', reason='API 未返回 completion_tokens；保留实测输出规格供核对。')
        for f in manifest:
            if f['kind'] == 'video':
                metadata = f.get('metadata', {})
                out['outputs'].append(metadata)
        out['assumed_dimensions'] = c.get('assumed_output_dimensions')
        out['assumed_duration'] = c.get('assumed_output_duration')
    else:
        rates = c['pricing']['rates']
        units = rates['layer'] if compiled['operation'] == 'decompose-layers' else rates['single']
        lo = hi = c.get('extra_input_cost', 0)
        for f in manifest:
            if f['kind'] != 'image':
                continue
            try:
                dims = image_dimensions(f['path'])
                price = units[int(math.prod(dims) > rates['threshold_pixels'])]
                lo += price
                hi += price
                out['outputs'].append({'dimensions': dims, 'unit_price': price})
            except (OSError, ValueError, KeyError):
                lo += min(units)
                hi += max(units)
                out['outputs'].append({'dimensions': None, 'unit_price_range': units})
                out['status'] = 'partial'
        out['output_count'] = len(out['outputs'])
        out['observed_output_cost_at_list_price'] = {'min': round(lo, 6), 'max': round(hi, 6)}
        if lo == hi:
            out['difference_percent_outside_estimate'] = difference(round(lo, 6), estimate['amount'])
    return out
