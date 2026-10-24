"""Seven public capabilities and their modes, shared by costing and submission."""
OPERATIONS = {
    'text-to-image': {},
    'image-to-image': {},
    'decompose-layers': {},
    'text-to-video': {},
    'image-to-video': {'first-frame': 'first-frame', 'first-last-frame': 'first-last-frame'},
    'reference-to-video': {'reference': 'reference-to-video', 'edit': 'edit-video'},
    'extend-video': {'before': 'extend-video', 'after': 'extend-video'},
}


def internal_operation(spec):
    """Resolve the public operation/mode to a private validation and API routing case."""
    operation = spec.get('operation')
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise ValueError('operation must be one of: ' + ', '.join(OPERATIONS))
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
    if (spec.get('operation') != 'text-to-image'
            and not (spec.get('provider') in ('volcengine', 'byteplus') and spec.get('operation') == 'image-to-image')):
        raise ValueError('Only basic text-to-image and image-to-image are implemented for Volcengine and BytePlus')
