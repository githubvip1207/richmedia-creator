"""check: inspect project configuration and required dependencies, read-only."""
import shutil
from core.envfile import read_config, load_project_env, fx_state
from core import dependencies
from providers import PROVIDERS


def check():
    values = read_config()
    suppliers = []
    issues = []
    for name, info in PROVIDERS.items():
        key = info['adapter'].KEY_ENV
        if values.get(key):
            suppliers.append({'id': name, 'name': info['name']})
        else:
            issues.append({'item': key, 'status': 'missing', 'action': 'Configure this API key locally in .env to enable the supplier'})
    return {
        'configuration': {'file': load_project_env(), 'status': 'ok' if load_project_env() else 'missing',
                          'suppliers': suppliers, 'issues': issues, 'exchange_rate': fx_state()},
        'dependencies': {'sd25_pe': dependencies.skill_status(), 'ffprobe':
                         {'status': 'ok', 'path': shutil.which('ffprobe')} if shutil.which('ffprobe') else
                         {'status': 'missing', 'action': 'Run doctor --dependencies; required for every task'}},
        'network_checked': False,
    }


def run(args):
    return check()
