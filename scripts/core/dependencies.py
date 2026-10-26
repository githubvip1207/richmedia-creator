"""共用的依赖查找及提交前必需检查。"""

from core import process
import os
import shutil
import subprocess
from pathlib import Path


def dependency_paths():
    codex = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    return [codex / "skills/sd25-pe/SKILL.md", Path.home() / ".agents/skills/sd25-pe/SKILL.md"]


def skill_status():
    """安装判定不仅要求路径存在，还要能读取且内容非空。"""
    for path in dependency_paths():
        try:
            if path.is_file() and path.read_text(encoding="utf-8").strip():
                return {"status": "ok", "path": str(path)}
        except (OSError, UnicodeError):
            continue
    return {"status": "missing", "action": "Run doctor --dependencies"}


def require_dependencies():
    """检查两项必需依赖，不安装依赖或提交生成任务。"""
    if skill_status()["status"] != "ok":
        raise ValueError("Required sd25-pe missing; run doctor --dependencies")
    if not shutil.which("ffprobe"):
        raise ValueError("Required ffprobe missing; run doctor --dependencies")


def run_installer(command):
    """不把安装器输出直接回显，避免外部配置或日志中的敏感信息进入诊断结果。"""
    try:
        result = process.run(command, capture_output=True, text=True, timeout=600)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def repair_dependencies():
    results = []
    if skill_status()["status"] != "ok":
        if not shutil.which("npx"):
            results.append(
                {
                    "item": "sd25-pe",
                    "status": "failed",
                    "reason": "npx is unavailable; install Node.js/npm first",
                }
            )
        else:
            ok = run_installer(
                [
                    "npx",
                    "--yes",
                    "skills@latest",
                    "add",
                    "https://arkdocs.tos-cn-beijing.volces.com/skills/",
                    "--skill",
                    "sd25-pe",
                    "--global",
                    "--yes",
                ]
            )
            results.append(
                {
                    "item": "sd25-pe",
                    "status": "repaired" if ok and skill_status()["status"] == "ok" else "failed",
                }
            )
    if not shutil.which("ffprobe"):
        if not shutil.which("brew"):
            results.append(
                {
                    "item": "ffprobe",
                    "status": "failed",
                    "reason": "Homebrew is unavailable; install FFmpeg using your system package manager",
                }
            )
        else:
            ok = run_installer(["brew", "install", "ffmpeg"])
            results.append(
                {
                    "item": "ffprobe",
                    "status": "repaired" if ok and shutil.which("ffprobe") else "failed",
                }
            )
    return results
