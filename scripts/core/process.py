"""按调用方提供的参数和超时设置执行外部工具。"""

import subprocess


def run(arguments, **options):
    return subprocess.run(arguments, **options)
