#!/usr/bin/env python3
# 命令行入口：读取项目配置，计算成本或执行已确认的供应商任务。
# 只有 submit 创建媒体生成请求；check 只读，doctor 可安装依赖或更新项目汇率。
"""RichMedia Creator CLI (Python 3.9+, stdlib only)."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from core.envfile import fx_from_env
from core import jobs, preflight, workspace, cost_assets
from core.request import CATALOGS, require
from providers import PROVIDERS


# 将结果编码为可读 JSON，保留中文并拒绝 NaN/Infinity，方便 CLI 消费方稳定解析。
def emit(value):
    print(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))


# 命令行仅返回是否生成成功及原因；完整执行状态仍保留在提交文件中。
def status_result(state):
    if state.get('state') == 'succeeded':
        return {'success': True, 'error': None}
    error = state.get('error') or state.get('errors')
    if error:
        if isinstance(error, dict):
            error = error.get('message') or json.dumps(error, ensure_ascii=False)
        elif isinstance(error, list):
            error = '；'.join(str(item.get('message') or json.dumps(item, ensure_ascii=False))
                             if isinstance(item, dict) else str(item) for item in error)
        return {'success': False, 'error': str(error)}
    status = state.get('state', 'unknown')
    if status in ('queued', 'running'):
        error = '任务尚未完成（状态：' + status + '），可继续查询'
    elif status in ('submitting', 'submission_unknown', 'unknown'):
        error = '生成结果尚未确定（状态：' + status + '），需核对供应商记录'
    else:
        error = '任务未成功（状态：' + status + '），供应商未提供具体原因'
    return {'success': False, 'error': error}


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
    # 已有任务入口：查询和下载不创建生成。
    status = subs.add_parser('status')
    status.add_argument('--submission',required=True,help='Path to submit-NNN.json')
    status.add_argument('--wait',type=int,default=0,choices=range(601),metavar='0..600')
    dl = subs.add_parser('download')
    dl.add_argument('--submission',required=True,help='Path to submit-NNN.json')
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
        try:
            emit(status_result(jobs.status(args.submission,args.wait)))
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            emit({'success': False, 'error': str(exc)})
            sys.exit(1)
    elif args.command == 'download':
        emit(jobs.download(args.submission))


if __name__ == '__main__':
    try:
        main()
    # 预期错误统一写入标准错误并返回非零退出码；避免 CLI 调用方将错误当作成功 JSON。
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr)
        sys.exit(1)
