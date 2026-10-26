"""价格快照日期校验；CLI 估价会尝试刷新过期快照，失败保留旧依据。"""

import contextlib
import contextvars
import copy
import datetime as dt
import json
import re
import urllib.request
from core.catalogs import ROOT, CATALOGS
from core.submission_store import write
from core.validation import require

SESSION = contextvars.ContextVar('pricing_session', default=None)
SOURCES = {
    'byteplus': 'https://ai.byteplus.com/ark/region:ap-southeast-1/docs/model-pricing.md',
    'volcengine': 'https://console.volcengine.com/ark/region:cn-beijing/docs/model-pricing.md',
}


def parse_volcengine_markdown(text, original):
    require('元/百万token' in text and '261 万像素' in text, 'Pricing units/pixel tiers missing')
    require('$' not in text[text.find('# 视频生成模型'):text.find('# 图片生成模型')],
            'Unexpected currency in video prices')
    updated = copy.deepcopy(original)
    for alias, resolutions in original['video'].items():
        label = 'doubao-' + alias
        match = re.search(r'^\|' + re.escape(label) + r'\s*\|', text, re.M)
        require(match is not None, 'Missing supported video model')
        block = text[match.end():]
        block = re.split(r'\n\|doubao-seedance-', block, maxsplit=1)[0]
        pairs = re.findall(r'输入不含视频[：:]\s*([0-9.]+).*?输入包含视频[：:]\s*([0-9.]+)', block, re.S)
        expected_count = len(resolutions) - 1  # 480p 与720p共用一组价格。
        require(len(pairs) == expected_count, 'Incomplete supported video resolution rates')
        for resolution in resolutions:
            index = 0 if resolution in ('480p', '720p') else 1 if resolution == '1080p' else 2
            updated['video'][alias][resolution] = list(map(float, pairs[index]))
    start = text.find('|doubao-seedream-5-0-pro ')
    require(start >= 0, 'Missing Pro image price')
    block = text[start:].split('|doubao-seedream-5-0-flash', 1)[0]
    input_rate = re.search(r'第 2 张起[：:]\s*([0-9.]+)', block)
    tiers = re.findall(r'261 万像素[：:]\s*([0-9.]+)', block)
    require(input_rate is not None and len(tiers) == 4, 'Incomplete image input/tier rates')
    updated['image']['seedream-5.0-pro'].update(input_after_first=float(input_rate[1]),
            single=list(map(float, tiers[:2])), layer=list(map(float, tiers[2:])))
    flash = re.search(r'\|doubao-seedream-5-0-flash\s*\|免费\s*\|([0-9.]+)\s*\|', text)
    require(flash is not None, 'Missing Flash image price')
    value = float(flash[1])
    updated['image']['seedream-5.0-flash'].update(input_after_first=0, single=[value, value], layer=[value, value])
    require(all(v > 0 for rows in updated['video'].values() for rates in rows.values() for v in rates),
            'Invalid nonpositive rate')
    updated.update(verified_on=dt.datetime.now(dt.timezone.utc).date().isoformat(),
                   verification_source=SOURCES['volcengine'])
    return updated


def freshness(price, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    try:
        age = (today - dt.date.fromisoformat(price['verified_on'])).days
        status = 'fresh' if 0 <= age <= 7 else 'stale'
    except (KeyError, ValueError, TypeError):
        age, status = None, 'invalid'
    return {'status': status, 'age_days': age, 'verified_on': price.get('verified_on')}


@contextlib.contextmanager
def pricing_session(directory):
    token = SESSION.set({'directory': directory, 'loaded': {}})
    try:
        yield
    finally:
        SESSION.reset(token)


def parse_markdown(text, provider, original):
    """只在所有已支持模型的单价都能核对时更新；网页结构变化不覆盖原价。"""
    require('minimum' in text.lower() or '最低' in text, 'Pricing page incomplete')
    if provider == 'volcengine':
        return parse_volcengine_markdown(text, original)
    require('2.61' in text or '261' in text, 'Image pixel-tier rule missing')
    updated = copy.deepcopy(original)
    mode, found = None, set()
    for line in text.splitlines():
        if 'Tab: Input without video' in line:
            mode = 0
        elif 'Tab: Input with video' in line:
            mode = 1
        if mode is None or not line.startswith('|'):
            continue
        cells = [c.strip().strip('`') for c in line.split('|')[1:-1]]
        for alias, model in CATALOGS[provider]['models'].items():
            if alias not in original['video'] or not cells or cells[0] != model['id']:
                continue
            for resolution, index in [('480p', 1), ('720p', 1), ('1080p', 2), ('4k', 3)]:
                if resolution not in original['video'][alias]:
                    continue
                match = re.fullmatch((r'\$?' if provider == 'byteplus' else r'[¥￥]?')
                                     + r'([0-9]+(?:\.[0-9]+)?)', cells[index])
                require(match is not None, 'Cannot parse supported video rate')
                updated['video'][alias][resolution][mode] = float(match[1])
                found.add((alias, resolution, mode))
    expected = {(m, r, i) for m, rows in original['video'].items() for r in rows for i in (0, 1)}
    require(found == expected, 'Cannot verify every supported video rate; use browser/manual official review')
    # Pro 图像价格的每个像素档与第二张输入价均在同一连续模型块内。
    image_section = text[text.lower().find('## image generation'):]
    pro_id = CATALOGS[provider]['models']['seedream-5.0-pro']['id']
    flash_id = CATALOGS[provider]['models']['seedream-5.0-flash']['id']
    require(pro_id in image_section and flash_id in image_section, 'Image model prices missing')
    block = image_section.split(pro_id, 1)[1].split(flash_id, 1)[0]
    money = (r'\$' if provider == 'byteplus' else r'[¥￥]') + r'([0-9]+(?:\.[0-9]+)?)'
    values = [float(v) for v in re.findall(money, block)]
    require(len(values) == 5 and all(v > 0 for v in values), 'Cannot verify image tier prices')
    pro = updated['image']['seedream-5.0-pro']
    pro.update(input_after_first=values[0], single=values[1:3], layer=values[3:5])
    flash_line = image_section.split(flash_id, 1)[1].splitlines()[0]
    values = re.findall(money, flash_line)
    require(len(values) == 1 and 'Free' in flash_line, 'Cannot verify Flash rate')
    value = float(values[0])
    updated['image']['seedream-5.0-flash'].update(input_after_first=0, single=[value, value], layer=[value, value])
    updated.update(verified_on=dt.datetime.now(dt.timezone.utc).date().isoformat(),
                   verification_source=SOURCES[provider])
    return updated


def refresh(provider, original, directory):
    from pathlib import Path
    try:
        request = urllib.request.Request(SOURCES[provider], headers={'User-Agent': 'RichMedia-Creator/1.0'})
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read(2_000_001)
        require(len(raw) <= 2_000_000, 'Pricing page too large')
        result = parse_markdown(raw.decode('utf-8'), provider, original)
        if directory is not None:
            write(Path(directory) / (provider + '-pricing-cache.json'), result)
        return result
    except (OSError, ValueError, IndexError, KeyError, TypeError):
        result = copy.deepcopy(original)
        result['refresh_status'] = 'failed: official page unavailable or schema not fully verified; previous prices retained'
        return result


def load_pricing(provider):
    from pathlib import Path
    original = json.loads((ROOT / 'models' / (provider + '-pricing.json')).read_text())
    session = SESSION.get()
    if session is None:
        return original
    if provider in session['loaded']:
        return session['loaded'][provider]
    cache = Path(session['directory']) / (provider + '-pricing-cache.json')
    if cache.is_file():
        try:
            saved = json.loads(cache.read_text())
            if saved.get('currency') == original['currency'] and freshness(saved)['status'] == 'fresh':
                original = saved
        except (OSError, ValueError, KeyError):
            pass
    result = refresh(provider, original, session['directory']) if freshness(original)['status'] != 'fresh' else original
    session['loaded'][provider] = result
    return result
