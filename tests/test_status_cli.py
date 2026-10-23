"""状态命令的精简输出和十分钟等待边界。"""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from core import jobs

module_spec = importlib.util.spec_from_file_location('status_cli', ROOT/'scripts/media.py')
cli = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(cli)


class StatusCLI(unittest.TestCase):
    def invoke(self, state, wait=None):
        argv = ['media.py', 'status', '--submission', '/tmp/fixture/submit-001.json']
        if wait is not None:
            argv += ['--wait', str(wait)]
        with patch.object(sys, 'argv', argv), patch.object(jobs, 'status', return_value=state) as status, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            cli.main()
        status.assert_called_once_with('/tmp/fixture/submit-001.json', 0 if wait is None else wait)
        return json.loads(output.getvalue())

    def test_success_output_excludes_internal_details(self):
        self.assertEqual(self.invoke({'state':'succeeded', 'compiled':{}, 'download_complete':False}),
                         {'success':True, 'error':None})

    def test_failure_reason(self):
        self.assertEqual(self.invoke({'state':'failed', 'error':{'code':'bad', 'message':'素材无效'}}),
                         {'success':False, 'error':'素材无效'})
        self.assertEqual(self.invoke({'state':'partial_failed', 'errors':[{'message':'部分图片生成失败'}]}),
                         {'success':False, 'error':'部分图片生成失败'})

    def test_unfinished_and_unknown_are_not_claimed_successful(self):
        self.assertIn('尚未完成', self.invoke({'state':'running'})['error'])
        self.assertIn('尚未确定', self.invoke({'state':'submission_unknown'})['error'])
        self.assertIn('未提供具体原因', self.invoke({'state':'expired'})['error'])

    def test_wait_endpoints(self):
        for wait in (0, 600):
            self.assertTrue(self.invoke({'state':'succeeded'}, wait)['success'])

    def test_wait_outside_range_never_queries(self):
        for wait in (-1, 601):
            with patch.object(sys, 'argv', ['media.py','status','--submission','fixture','--wait',str(wait)]), \
                    patch.object(jobs,'status') as status, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    cli.main()
                self.assertEqual(error.exception.code, 2)
                status.assert_not_called()

    def test_query_exception_returns_failure_reason(self):
        with patch.object(sys, 'argv', ['media.py','status','--submission','missing']), \
                patch.object(jobs,'status',side_effect=OSError('提交文件不存在')), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as error:
                cli.main()
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(json.loads(output.getvalue()), {'success':False,'error':'提交文件不存在'})


class StatusWait(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.record = Path(self.tmp.name)/'submit-001.json'
        jobs.write(self.record, {'execution':{'compiled':{'provider':'volcengine','kind':'video'},
                                            'task_id':'fixture', 'state':'queued'}})

    def test_can_wait_beyond_previous_45_seconds(self):
        clock = [0]
        responses = iter(['running', 'running', 'succeeded'])
        def query(*args, **kwargs):
            clock[0] += 20
            return {'id':'fixture','status':next(responses)}
        def sleep(seconds):
            clock[0] += seconds
        with patch.object(jobs,'query_submission',side_effect=query) as get, \
                patch.object(jobs.time,'monotonic',side_effect=lambda:clock[0]), \
                patch.object(jobs.time,'sleep',side_effect=sleep):
            state = jobs.status(self.record, wait=600)
        self.assertEqual(state['state'],'succeeded')
        self.assertEqual(get.call_count,3)
        self.assertGreater(clock[0],45)

    def test_stops_at_600_seconds_without_starting_another_query(self):
        clock = [0]
        def query(*args, **kwargs):
            clock[0] = 599
            return {'id':'fixture','status':'running'}
        def sleep(seconds):
            clock[0] += seconds
        with patch.object(jobs,'query_submission',side_effect=query) as get, \
                patch.object(jobs.time,'monotonic',side_effect=lambda:clock[0]), \
                patch.object(jobs.time,'sleep',side_effect=sleep) as pause:
            state = jobs.status(self.record, wait=600)
        self.assertEqual(state['state'],'running')
        self.assertEqual(get.call_count,1)
        self.assertEqual(clock[0],600)
        pause.assert_called_once_with(1)

    def test_query_timeout_is_limited_to_remaining_wait(self):
        with patch.object(jobs,'query_submission',return_value={'id':'fixture','status':'succeeded'}) as get, \
                patch.object(jobs.time,'monotonic',side_effect=[0,599,600]):
            jobs.status(self.record,wait=600)
        self.assertEqual(get.call_args.kwargs['timeout'],1)

    def test_zero_wait_performs_one_query_without_sleep(self):
        with patch.object(jobs,'query_submission',return_value={'id':'fixture','status':'running'}) as get, \
                patch.object(jobs.time,'sleep') as pause:
            state = jobs.status(self.record,wait=0)
        self.assertEqual(get.call_count,1)
        self.assertEqual(state['state'],'running')
        pause.assert_not_called()

    def test_image_returns_immediately_even_with_wait(self):
        record=jobs.read(self.record)
        record['execution']['compiled']['kind']='image'
        record['execution']['state']='succeeded'
        jobs.write(self.record,record)
        with patch.object(jobs,'query_submission') as query, patch.object(jobs.time,'sleep') as sleep:
            self.assertEqual(jobs.status(self.record,wait=600)['state'],'succeeded')
        query.assert_not_called()
        sleep.assert_not_called()
