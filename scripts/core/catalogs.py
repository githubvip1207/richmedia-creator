"""读取本地模型目录，不读取凭证或发起请求。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOGS = {
    name: json.loads((ROOT / "models" / (name + ".json")).read_text())
    for name in ("volcengine", "byteplus")
}
RATIOS = ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"]
