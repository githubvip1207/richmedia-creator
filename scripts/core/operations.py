"""Seven public capabilities and their modes, shared by costing and submission."""
OPERATIONS = {
    'text-to-image': {},
    'image-to-image': {},
    'decompose-layers': {},
    'text-to-video': {},
    'image-to-video': {},
    'reference-to-video': {'reference': 'reference-to-video', 'edit': 'edit-video'},
    'extend-video': {'before': 'extend-video', 'after': 'extend-video'},
}


def internal_operation(spec):
    """Resolve the public operation/mode to a private validation and API routing case."""
    operation = spec.get('operation')
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise ValueError('operation must be one of: ' + ', '.join(OPERATIONS))
    if operation == 'image-to-video':
        if 'mode' in spec:
            raise ValueError('image-to-video does not accept mode; use one or two ordered image assets')
        assets = spec.get('assets')
        count = len(assets) if isinstance(assets, list) else spec.get('input_images')
        if type(count) is not int or count not in (1, 2):
            raise ValueError('image-to-video requires one or two ordered image assets')
        return 'first-frame' if count == 1 else 'first-last-frame'
    modes = OPERATIONS[operation]
    mode = spec.get('mode')
    if modes:
        if not isinstance(mode, str) or mode not in modes:
            raise ValueError(operation + ' requires mode: ' + ', '.join(modes))
        return modes[mode]
    if mode is not None:
        raise ValueError(operation + ' does not accept mode')
    return operation


def require_supported_operation(spec):
    """Public execution and estimation share the same capability boundary."""
    if spec.get('provider') not in ('volcengine', 'byteplus') or spec.get('operation') not in (
            'text-to-image', 'image-to-image', 'decompose-layers', 'text-to-video', 'image-to-video'):
        raise ValueError('Only basic text-to-image, image-to-image, decompose-layers, text-to-video and image-to-video are implemented for Volcengine and BytePlus')
