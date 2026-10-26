#!/usr/bin/env python3
# 命令行入口：读取项目配置，计算成本或执行已确认的供应商任务。
# 只有 submit 创建媒体生成请求；check 只读，doctor 可安装依赖或更新项目汇率。
"""富媒体生成器命令行入口，要求 Python 3.9 及以上，仅使用标准库。"""
import argparse
import json
import subprocess
import sys
from commands import (init as init_command,
                      check as check_command, doctor as doctor_command,
                      cost as cost_command, submit as submit_command,
                      status as status_command, deliver as deliver_command)

COMMANDS = {'init': init_command, 'check': check_command,
            'doctor': doctor_command, 'cost': cost_command,
            'submit': submit_command, 'status': status_command, 'deliver': deliver_command}


# 将结果编码为可读 JSON，保留中文并拒绝 NaN/Infinity，方便 CLI 消费方稳定解析。
def emit(value):
    print(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))


# 注册检查、成本计算、提交、查询和交付命令。供应商取自用户所选任务配置。
def main():
    parser = argparse.ArgumentParser(description='富媒体生成器：estimate costs, confirm in chat, then submit once')
    subs = parser.add_subparsers(dest='command',required=True)
    # check 只读；doctor 可执行依赖安装与汇率 GET，但不提交媒体生成。
    init = subs.add_parser('init', help='Read a JSON object from stdin and save request.json in a private run directory')
    subs.add_parser('check', help='Read-only configuration and dependency checks')
    repair = subs.add_parser('doctor', help='Repair dependencies and exchange-rate configuration, then recheck')
    repair.add_argument('--dependencies', action='store_true', help='Repair missing dependencies only')
    repair.add_argument('--exchange-rate', action='store_true', help='Refresh USD/CNY and update project .env only')
    repair.add_argument('--pricing', action='store_true', help='Verify official pricing; update only completely parsed supplier snapshots')
    estimate = subs.add_parser('cost', help='Inspect cost assets and estimate costs from JSON on stdin; never submits generation')
    estimate.add_argument('--workdir', required=True, help='Existing task working directory')
    sub = subs.add_parser('submit', help='Submit the confirmed request using its saved supplier cost')
    sub.add_argument('--request',help='Optional task-spec.json path; otherwise read the request JSON from stdin')
    sub.add_argument('--workdir',required=True,help='Existing task directory containing <provider>-priceing.json')
    sub.add_argument('--approval-text',required=True,help='Actual user reply, never generated consent')
    sub.add_argument('--accept-uncertain-cost',action='store_true')
    # 已有任务入口：查询和交付不创建生成。
    status = subs.add_parser('status')
    status.add_argument('--submission',required=True,help='Path to submit-NNN.json')
    status.add_argument('--wait',type=int,default=0,choices=range(601),metavar='0..600')
    dl = subs.add_parser('deliver', help='Retrieve, validate and deliver final outputs into the current project directory')
    dl.add_argument('--submission',required=True,help='Path to submit-NNN.json')
    args = parser.parse_args()
    try:
        result = COMMANDS[args.command].run(args)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        if args.command != 'status':
            raise
        emit({'success': False, 'error': str(exc)})
        sys.exit(1)
    emit(result)
    if args.command == 'doctor' and any(item['status'] == 'failed' for item in result['repairs']):
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
