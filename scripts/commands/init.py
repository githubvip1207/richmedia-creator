r"""命令行调用

    python3 "$SKILL/scripts/main.py" init < /absolute/request.json

    # < 将 UTF-8 JSON 文件内容送入 stdin；本命令没有文件路径选项。

输入文件格式

实际文件为 UTF-8 标准 JSON，根节点为对象；下方 JSONC 的 // 仅用于逐字段说明，写文件时删除注释。

输入文件 /absolute/request.json
编码 UTF-8，根节点为 JSON 对象；通过 shell 的 < 写入 stdin，命令不接收文件路径参数。

```jsonc
{
  "original_prompt": "生成一段狐狸在草地奔跑的视频", // string；全部用户原话，按时间顺序换行追加，保留原文。
  "optimized_prompt": "生成一段狐狸在草地奔跑的视频", // string；当前优化结果；未优化时与 original_prompt 完全一致。
  "intent": { // object；用户所需能力，不在此处填写供应商模式。
    "operation": "image-to-video" // Operation；七种能力之一；枚举见 commands/__init__.py。
  },
  "assets": [ // Asset[]；完整素材目录，无素材传 []；逐字段定义见 __init__.py。
    {
      "id": "reference-1", // string?；任务内唯一标识；init/submit 必需，cost 可选。
      "kind": "image", // "image" | "video" | "audio"；素材媒体类型。
      "source": "https://example.com/reference.png", // string；实际 HTTPS URL 或本地绝对路径；视频提交只接受 HTTPS。
      "purpose": "参考主体外观" // string?；素材用途；init/submit 必需；估价入口禁止传此字段。
    }
  ],
  "providers": { // object；候选供应商计划，键为 volcengine 或 byteplus。
    "volcengine": { // object；一家供应商的模型、能力、参数和有序素材引用。
      "model": "doubao-seedance-2-5-260628", // string；本供应商技能模型别名或准确模型 ID。
      "operation": "image-to-video", // Operation；与 intent.operation 对应的已实现能力。
      "parameters": { // object；按该能力已确定的生成参数；每个字段见 __init__.py。
        "ratio": "adaptive", // string?；构图比例；视频还可用 adaptive，图片不直接发送 ratio 字段。
        "resolution": "480p", // string?；视频分辨率，如 480p/720p/1080p/4k，须模型支持。
        "duration": 5, // integer?；视频输出秒数；-1 表示模型自动决定。
        "generate_audio": false, // boolean?；是否生成视频声音。
        "watermark": false, // boolean?；是否添加水印；具体能力可能要求固定值。
        "return_last_frame": false, // boolean?；是否返回视频对应尾帧图。
        "output_format": "mp4", // string?；图片 png/jpeg，视频 mp4/mov，受模型限制。
        "service_tier": "default", // string?；视频服务档位；当前为 default，2.0-mini 必须省略。
        "tools": [] // Tool[]?；视频联网搜索设置；供应商/能力可能限制或省略。
      },
      "assets": [ // AssetRef[]；引用顶层素材 id，保留模型所需顺序，无素材传 []。
        {
          "id": "reference-1" // string；引用顶层同名 id；顺序与模型输入顺序一致。
        }
      ]
    }
  }
}
```

标准输出格式

```jsonc
{
  "workdir": "/tmp/richmedia-example" // string；新建 /tmp/richmedia-<时间戳> 目录的绝对路径。
}
```

文件输出格式

<workdir>/request.json：内容与输入 request.json 完全一致，原样保存，不重复描述。
目录权限为 0700，文件权限为 0600。

失败输出

已捕获异常的 stderr JSON 格式见 __init__.py；命令行参数错误使用 argparse usage 文本。
"""
import datetime as dt
import json
import os
from pathlib import Path

WORK_ROOT = Path('/tmp')


def initialize(content):
    """创建运行目录前先校验标准输入中的 JSON，再以私有权限保存。"""
    def reject_constant(value):
        raise ValueError('request.json must use finite JSON numbers')

    try:
        record = json.loads(content, parse_constant=reject_constant)
    except (ValueError, TypeError):
        raise ValueError('Provide a valid JSON object through stdin') from None
    if not isinstance(record, dict):
        raise ValueError('request.json must be a JSON object')
    timestamp = dt.datetime.now()
    while True:
        directory = WORK_ROOT / timestamp.strftime('richmedia-%Y%m%d%H%M%S')
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            timestamp += dt.timedelta(seconds=1)
            continue
        request = directory / 'request.json'
        try:
            with os.fdopen(os.open(str(request), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                           'w', encoding='utf-8') as output:
                output.write(content)
        except BaseException:
            if request.exists():
                request.unlink()
            directory.rmdir()
            raise
        return {'workdir': str(directory)}

def run(args):
    import sys
    if sys.stdin.isatty():
        raise ValueError('init requires request.json content through stdin')
    return initialize(sys.stdin.read())
