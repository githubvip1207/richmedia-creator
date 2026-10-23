"""Shared dependency discovery and mandatory pre-submission checks."""
import os
import shutil
from pathlib import Path


def dependency_paths():
    codex = Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex')))
    return [codex/'skills/sd25-pe/SKILL.md', Path.home()/'.agents/skills/sd25-pe/SKILL.md']


def skill_status():
    """安装判定不仅要求路径存在，还要能读取且内容非空。"""
    for path in dependency_paths():
        try:
            if path.is_file() and path.read_text(encoding='utf-8').strip():
                return {'status': 'ok', 'path': str(path)}
        except (OSError, UnicodeError):
            continue
    return {'status': 'missing', 'action': 'Run doctor --dependencies'}


def require_dependencies():
    """Check both mandatory dependencies without installing or submitting anything."""
    if skill_status()['status'] != 'ok':
        raise ValueError('Required sd25-pe missing; run doctor --dependencies')
    if not shutil.which('ffprobe'):
        raise ValueError('Required ffprobe missing; run doctor --dependencies')


