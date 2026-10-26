"""发布验证通过的缓存文件，不覆盖用户已有文件。"""

import os
import shutil
from pathlib import Path
from core.validation import require
from core.submission_store import read, write, lock, now
from core.file_hash import sha256_file


def verified_delivery(record):
    """按清单和哈希核对当前或历史交付，支持缓存清理及发布中断后的恢复。"""
    result = record.get("result", {})
    expected = list(result.get("files", []))
    if not expected:
        return None
    if result.get("metadata"):
        expected.append(result["metadata"])
    candidates = [record.get("delivery"), *reversed(record.get("delivery_history", []))]
    for previous in candidates:
        if not previous:
            continue
        actual = list(previous.get("files", []))
        if bool(result.get("metadata")) != bool(previous.get("metadata")):
            continue
        if previous.get("metadata"):
            actual.append(previous["metadata"])
        directory = Path(previous["directory"])
        if (len(expected) != len(actual) or not directory.is_dir() or directory.is_symlink()):
            continue
        if all(Path(item["path"]).parent == directory
               and Path(item["path"]).name == Path(source["path"]).name
               and item["sha256"] == source["sha256"]
               and not Path(item["path"]).is_symlink()
               and Path(item["path"]).is_file()
               and sha256_file(item["path"]) == source["sha256"]
               for source, item in zip(expected, actual)):
            return previous
    return None


def publish_outputs(record_path, destination):
    with lock(record_path.parent):
        record = read(record_path)
        result = record["result"]
        completed = verified_delivery(record)
        if completed:
            record["execution"]["download_complete"] = True
        record["execution"]["delivery_complete"] = False
        write(record_path, record)
        require(
            record["execution"].get("download_complete") is True, "Media retrieval is incomplete"
        )
        sources = [*result["files"]]
        if result.get("metadata"):
            sources.append(result["metadata"])
        if completed:
            delivered_sources = list(completed["files"])
            if completed.get("metadata"):
                delivered_sources.append(completed["metadata"])
            sources = [item if Path(item["path"]).is_file() and sha256_file(item["path"]) == item["sha256"]
                       else delivered for item, delivered in zip(sources, delivered_sources)]
        for item in sources:
            require(
                Path(item["path"]).is_file() and sha256_file(item["path"]) == item["sha256"],
                "Cached output changed; retry deliver",
            )
        previous = record.get("delivery")
        directory = Path(previous["directory"]) if previous else None
        reusable = (
            directory is not None
            and directory.is_dir()
            and (not directory.is_symlink())
            and (directory.parent == destination)
            and all(
                (
                    not (directory / Path(item["path"]).name).exists()
                    and (not (directory / Path(item["path"]).name).is_symlink())
                    or (
                        (directory / Path(item["path"]).name).is_file()
                        and (not (directory / Path(item["path"]).name).is_symlink())
                        and (sha256_file(directory / Path(item["path"]).name) == item["sha256"])
                    )
                    for item in sources
                )
            )
        )
        if not reusable:
            base = "richmedia-" + record_path.parent.name + "-" + record_path.stem
            counter = 0
            while True:
                directory = destination / (base + ("-" + str(counter) if counter else ""))
                try:
                    directory.mkdir(mode=448)
                    break
                except FileExistsError:
                    counter += 1
            if previous:
                record.setdefault("delivery_history", []).append(previous)
        delivered = {"directory": str(directory), "files": [], "delivered_at": now()}
        if result.get('cost_comparison'):
            delivered['cost_comparison'] = result['cost_comparison']
        record["delivery"] = delivered
        write(record_path, record)
        for item in sources:
            target = directory / Path(item["path"]).name
            if not target.exists():
                with open(item["path"], "rb") as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                    output.flush()
                    os.fsync(output.fileno())
            require(sha256_file(target) == item["sha256"], "Delivered file checksum mismatch")
            final = {"path": str(target), "sha256": item["sha256"]}
            if result.get("metadata") and Path(item["path"]).name == Path(result["metadata"]["path"]).name:
                delivered["metadata"] = final
            else:
                final.update(
                    {k: item[k] for k in ("kind", "provider", "model", "metadata", "verification") if k in item}
                )
                delivered["files"].append(final)
            write(record_path, record)
        record["execution"]["delivery_complete"] = True
        write(record_path, record)
        return delivered
