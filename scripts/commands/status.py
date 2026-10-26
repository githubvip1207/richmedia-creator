r"""命令行调用

    python3 "$SKILL/scripts/main.py" status --submission /absolute/submit-001.json
    python3 "$SKILL/scripts/main.py" status --submission /absolute/submit-001.json --wait 60

    # --submission：必填，由 submit 生成的提交记录 JSON 文件。
    # --wait：可选，默认 0；等待视频任务的秒数，允许 0～600。

输入文件格式

实际文件为 UTF-8 标准 JSON，根节点为对象；下方 JSONC 的 // 仅用于逐字段说明，写文件时删除注释。

--submission 指向 submit-NNN.json，必须使用 submit 自动保存的完整记录；
不能仅提供 task_id，也不是原始 task-spec.json。
该文件与 submit.py 的文件输出完全相同，JSON 格式统一见 submit.py 的“文件输出格式”，此处不重复。
其中 execution.compiled 决定供应商与能力，execution.task_id 用于视频查询；
视频交付还使用 queries 中最近一次成功响应的 content.video_url。

标准输出格式

```jsonc
{
  "success": false, // boolean；仅当前状态为 succeeded 时 true；排队/运行/部分失败均 false。
  "error": "示例文本" // string | null；成功时 null；其他状态为供应商错误、未完成或需核对的原因。
}
```

文件输出格式

更新传入的 submit-NNN.json：保留原始 POST response；更新 execution，并按查询追加 queries。
文件结构与输入相同，不重复展开；其完整字段见 submit.py 的“文件输出格式”。

失败输出

运行异常仍按上述 {success,error} 格式输出 stdout 并退出 1。正常查询但未完成时 success=false，退出码仍为 0。
"""

import json
import time
from core.validation import require
from core.submission_store import read, write, lock, submission_path, now
from providers import capability_for_record
from core.http import ProviderError, sanitize_response, response_error


def status_result(state):
    if state.get("state") == "succeeded":
        return {"success": True, "error": None}
    error = state.get("error") or state.get("errors")
    if error:
        if isinstance(error, dict):
            error = error.get("message") or json.dumps(error, ensure_ascii=False)
        elif isinstance(error, list):
            error = "；".join(
                (
                    str(item.get("message") or json.dumps(item, ensure_ascii=False))
                    if isinstance(item, dict)
                    else str(item)
                )
                for item in error
            )
        return {"success": False, "error": str(error)}
    status = state.get("state", "unknown")
    if status in ("queued", "running"):
        error = "任务尚未完成（状态：" + status + "），可继续查询"
    elif status in ("submitting", "submission_unknown", "unknown"):
        error = "生成结果尚未确定（状态：" + status + "），需核对供应商记录"
    else:
        error = "任务未成功（状态：" + status + "），供应商未提供具体原因"
    return {"success": False, "error": error}


def status(submission, wait=0):
    path = submission_path(submission)
    with lock(path.parent):
        record = read(path)
        state = record["execution"]
        capability = capability_for_record(record)
        # POST 响应先于执行状态落盘；恢复两次写入之间发生中断的提交。
        saved = record.get("response")
        if state["state"] == "submitting" and isinstance(saved, dict) and not saved.get("error"):
            if state["compiled"]["kind"] == "video":
                task_id = saved.get("id")
                if isinstance(task_id, str) and task_id:
                    require(state.get("task_id") in (None, task_id), "Saved POST task ID conflicts with execution task ID")
                    state.update(state="queued", task_id=task_id, error=None, updated_at=now())
                    write(path, record)
            elif saved.get("data"):
                state.update(capability.response_state(saved, state["compiled"]), error=None, updated_at=now())
                write(path, record)
        if state["compiled"]["kind"] == "image":
            # 使用本能力的规则重新检查已保存的同步图片响应。
            # 结果未知或已拒绝的提交保留原状态，绝不自动重新提交。
            if state["state"] in ("succeeded", "partial_failed", "failed"):
                try:
                    state.update(capability.status(record), error=None)
                except ValueError as exc:
                    state.update(
                        state="submission_unknown",
                        error=str(exc),
                        download_complete=False,
                        delivery_complete=False,
                    )
                if state["state"] != "succeeded":
                    state["delivery_complete"] = False
                state["updated_at"] = now()
                write(path, record)
            return state
        if not state.get("task_id"):
            return state
        wait = min(max(wait, 0), 600)
        deadline = time.monotonic() + wait
        while True:
            # 不在截止时间后开始新查询；单次请求超时不超过剩余等待时间。
            if wait:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return state
                result = query_submission(
                    record, path, capability, state["task_id"], timeout=min(25, remaining)
                )
            else:
                result = query_submission(record, path, capability, state["task_id"])
            require(
                result.get("id", state["task_id"]) == state["task_id"],
                "Provider returned a different task ID",
            )
            state.update(
                capability.response_state(result, state["compiled"], state["task_id"]),
                updated_at=now(),
            )
            write(path, record)
            remaining = deadline - time.monotonic()
            if state["state"] not in ("queued", "running") or not wait or remaining <= 0:
                return state
            time.sleep(min(10, remaining))


def query_submission(record, path, capability, task_id, timeout=None):
    """分别保存每次状态 GET 响应，保持原始 POST 响应不变。"""
    query = {"requested_at": now(), "request": capability.status_request(record), "response": None}
    record.setdefault("queries", []).append(query)
    write(path, record)
    try:
        query["response"] = capability.status(record, timeout=timeout)
    except Exception as exc:
        query["error"] = str(exc) if isinstance(exc, ProviderError) else type(exc).__name__
        write(path, record)
        raise
    query["response"] = sanitize_response(
        query["response"], secrets=(record["execution"]["compiled"].get("prompt", ""),)
    )
    write(path, record)
    return query["response"]


def run(args):
    return status_result(status(args.submission, args.wait))
