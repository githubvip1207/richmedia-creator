"""estimate-cost: measure input media, calculate costs and save a supplier quote."""
import json
import sys
from pathlib import Path
from core.envfile import fx_from_env
from core.media_probe import calculate_asset_inputs
from core.request import require
from core.operations import require_supported_operation
from core.submission_store import lock, prior_submission, write


def run(args):
    workdir = Path(args.workdir).resolve(strict=True)
    require(workdir.is_dir(), '--workdir must be an existing task directory')
    require(not sys.stdin.isatty(), 'Supply cost inputs as a JSON object on stdin')
    def reject_constant(value):
        raise ValueError('Invalid JSON numeric constant: ' + value)
    inputs = json.loads(sys.stdin.read(), parse_constant=reject_constant)
    require(isinstance(inputs, dict), 'Cost input must be a JSON object')
    require_supported_operation(inputs)
    require(not inputs.get('assets'), 'Text-to-image must not include input assets')
    quote = calculate_asset_inputs(inputs, fx=fx_from_env())
    target = workdir/(inputs['provider'] + '-priceing.json')
    with lock(workdir):
        prior_submission(workdir)
        write(target, quote)
    return {'workdir': str(workdir), 'quote': str(target), **quote}
