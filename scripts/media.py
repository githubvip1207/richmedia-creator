#!/usr/bin/env python3
# 命令行入口：读取项目配置，计算成本或执行已确认的供应商任务。
# 只有 submit 创建媒体生成请求；check 只读，doctor 可安装依赖或更新项目汇率。
"""RichMedia Creator CLI (Python 3.9+, stdlib only)."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from core.envfile import load_project_env, fx_from_env
# 记录当前项目 .env 的存在状态；实际配置由各命令按需读取，不导入进程环境。
ENV_FILE = load_project_env()
from core import jobs, preflight, workspace, cost_assets
from core.request import CATALOGS, require
from providers import PROVIDERS


# 将结果编码为可读 JSON，保留中文并拒绝 NaN/Infinity，方便 CLI 消费方稳定解析。
def emit(value):
    print(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))


# 注册检查、成本计算、提交、查询和下载命令。供应商取自用户所选任务配置。
def main():
    parser = argparse.ArgumentParser(description='富媒体生成器：estimate costs, confirm in chat, then submit once')
    subs = parser.add_subparsers(dest='command',required=True)
    # check 只读；doctor 可执行依赖安装与汇率 GET，但不提交媒体生成。
    init = subs.add_parser('init', help='Read a JSON object from stdin and save request.json in a private run directory')
    models = subs.add_parser('models')
    models.add_argument('--provider',choices=list(PROVIDERS))
    subs.add_parser('check', help='Read-only configuration and dependency checks')
    repair = subs.add_parser('doctor', help='Repair dependencies and exchange-rate configuration, then recheck')
    repair.add_argument('--dependencies', action='store_true', help='Repair missing dependencies only')
    repair.add_argument('--exchange-rate', action='store_true', help='Refresh USD/CNY and update project .env only')
    estimate = subs.add_parser('estimate-cost', help='Inspect cost assets and estimate costs from JSON on stdin; never submits generation')
    estimate.add_argument('--workdir', required=True, help='Existing task working directory')
    sub = subs.add_parser('submit', help='Submit the confirmed request using its saved supplier cost')
    sub.add_argument('--request',help='Optional task-spec.json path; otherwise read the request JSON from stdin')
    sub.add_argument('--workdir',required=True,help='Existing task directory containing <provider>/cost.json')
    sub.add_argument('--approval-text',required=True,help='Actual user reply, never generated consent')
    sub.add_argument('--accept-uncertain-cost',action='store_true')
    # 已有任务入口：查询/下载不创建生成；attach-task 只关联已核对的现存视频任务。
    status = subs.add_parser('status')
    status.add_argument('--submission',required=True,help='Path to submit-NNN.json')
    status.add_argument('--wait',type=int,default=0,choices=range(46),metavar='0..45')
    dl = subs.add_parser('download')
    dl.add_argument('--submission',required=True,help='Path to submit-NNN.json')
    attach = subs.add_parser('attach-task')
    attach.add_argument('--submission',required=True,help='Path to submit-NNN.json')
    attach.add_argument('--task-id',required=True)
    args = parser.parse_args()
    if args.command == 'init':
        if sys.stdin.isatty():
            parser.error('init requires request.json content through stdin')
        emit(workspace.initialize(sys.stdin.read()))
    elif args.command == 'models':
        emit(CATALOGS[args.provider] if args.provider else {'providers':CATALOGS})
    elif args.command == 'check':
        emit(preflight.check())
    elif args.command == 'doctor':
        result = preflight.doctor(args.dependencies, args.exchange_rate)
        emit(result)
        if any(item['status'] == 'failed' for item in result['repairs']):
            sys.exit(1)
    elif args.command == 'estimate-cost':
        workdir = Path(args.workdir).resolve(strict=True)
        require(workdir.is_dir(), '--workdir must be an existing task directory')
        require(not sys.stdin.isatty(), 'Supply cost inputs as a JSON object on stdin')
        def reject_constant(value):
            raise ValueError('Invalid JSON numeric constant: '+value)
        inputs = json.loads(sys.stdin.read(), parse_constant=reject_constant)
        require(isinstance(inputs, dict), 'Cost input must be a JSON object')
        quote = cost_assets.calculate_asset_inputs(inputs, fx=fx_from_env())
        target = workdir/inputs['provider']
        target.mkdir(mode=0o700, exist_ok=True)
        jobs.prior_submission(workdir)
        jobs.write(target/'cost.json', quote)
        emit(quote)
    elif args.command == 'submit':
        if args.request:
            spec = jobs.read(args.request)
        else:
            require(not sys.stdin.isatty(), 'Supply the request JSON object on stdin')
            def reject_constant(value):
                raise ValueError('Invalid JSON numeric constant: '+value)
            spec = json.loads(sys.stdin.read(), parse_constant=reject_constant)
            require(isinstance(spec, dict), 'Request input must be a JSON object')
        state = jobs.submit(args.workdir,spec,args.approval_text,args.accept_uncertain_cost)
        emit({'submission': state['submission']})
    elif args.command == 'status':
        emit(jobs.status(args.submission,args.wait))
    elif args.command == 'download':
        emit(jobs.download(args.submission))
    elif args.command == 'attach-task':
        emit(jobs.attach_task(args.submission,args.task_id))


if __name__ == '__main__':
    try:
        main()
    # 预期错误统一写入标准错误并返回非零退出码；避免 CLI 调用方将错误当作成功 JSON。
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr)
        sys.exit(1)
