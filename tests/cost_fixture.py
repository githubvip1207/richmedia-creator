"""Save task inputs and independent costs for mocked submission tests."""
from core import jobs
from core.costing import calculate


def save_with_cost(spec, out, pricing=None):
    out.mkdir(parents=True,exist_ok=True)
    target=out/spec['provider']
    target.mkdir(exist_ok=True)
    jobs.write(target/'cost.json',calculate(spec,pricing))
    jobs.write(out/'task-spec.json',spec)
    return spec
