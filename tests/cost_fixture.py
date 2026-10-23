"""Save task inputs and independent costs for mocked submission tests."""
from core import jobs
from core.costing import billing_inputs, calculate_inputs
from core.request import compile_request


def calculate(spec, pricing=None):
    """Build a quote from a mocked task specification for submission tests."""
    compiled = compile_request(spec)
    return calculate_inputs(billing_inputs(compiled), pricing, spec.get('estimate_context'),
                            spec.get('fx'), compiled['assets'])


def save_with_cost(spec, out, pricing=None):
    out.mkdir(parents=True,exist_ok=True)
    target=out/spec['provider']
    target.mkdir(exist_ok=True)
    jobs.write(target/'cost.json',calculate(spec,pricing))
    jobs.write(out/'task-spec.json',spec)
    return spec
