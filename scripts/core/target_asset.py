"""通过素材 ID 定位编辑或延长目标，兼容历史记录中的数组下标。"""

from core.validation import require


def target_index(assets, target_asset_id=None, context=None, require_target=False):
    require(context is None or isinstance(context, dict), 'estimate_context must be an object')
    videos = [i for i, asset in enumerate(assets) if asset['kind'] == 'video']
    legacy = (context or {}).get('target_asset_index')
    require(legacy is None or (type(legacy) is int and legacy in videos),
            'target_asset_index must identify the editing/extension source video')
    if target_asset_id is not None:
        require(isinstance(target_asset_id, str) and bool(target_asset_id.strip()),
                'target_asset_id must be a nonempty string')
        matches = [i for i, asset in enumerate(assets) if asset.get('id') == target_asset_id]
        require(len(matches) == 1 and matches[0] in videos,
                'target_asset_id must identify exactly one input video')
        selected = matches[0]
        require(legacy is None or legacy == selected,
                'target_asset_id conflicts with legacy target_asset_index')
        return selected
    if legacy is not None:
        return legacy
    if len(videos) == 1:
        return videos[0]
    require(not require_target, 'Multiple videos require target_asset_id for editing/extension')
    return None


def validate_target_scope(spec):
    if 'target_asset_id' in spec:
        require(spec.get('operation') == 'extend-video' or
                (spec.get('operation') == 'reference-to-video' and spec.get('mode') == 'edit'),
                'target_asset_id is only supported for video editing/extension')
        require(isinstance(spec['target_asset_id'], str) and bool(spec['target_asset_id'].strip()),
                'target_asset_id must be a nonempty string')
