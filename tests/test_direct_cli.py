"""Direct CLI submission uses saved costs, never preparation or confirmation hashes."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from core import jobs
from core.request import ROOT
from core.costing import calculate
from providers import volcengine
from config_fixture import config_fixture


class DirectCLI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work=Path(self.tmp.name)
        self.spec={'provider':'volcengine','model':'seedream-5.0-flash',
                   'operation':'text-to-image','prompt':'cat','parameters':{'ratio':'1:1'}}
        (self.work/'volcengine').mkdir()
        jobs.write(self.work/'volcengine/cost.json',calculate(self.spec))
        jobs.write(self.work/'task-spec.json',self.spec)

    def test_cli_submits_and_downloads_without_plan(self):
        module_spec=importlib.util.spec_from_file_location('direct_cli',ROOT/'scripts/media.py')
        cli=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(cli)
        with config_fixture({'VOLCENGINE_API_KEY':'fixture-only'}), \
             patch.object(volcengine,'request',return_value={'data':[{'url':'https://example.com/cat.png'}]}) as post, \
             patch('core.costing.estimate',side_effect=AssertionError('No recalculation')), \
             patch.object(cli,'emit'), \
             patch.object(sys,'argv',['media.py','submit','--workdir',str(self.work),
                                     '--request',str(self.work/'task-spec.json'),'--approval-text','TEST: selected supplier']):
            cli.main()
        state=jobs.read(self.work/'submit-001.json')['execution']
        self.assertEqual(state['state'],'succeeded')
        self.assertEqual(state['compiled']['prompt'],'cat\n构图比例偏好：1:1。')
        self.assertNotIn('plan_hash',state)
        self.assertFalse((self.work/'plan.json').exists())
        self.assertFalse((self.work/'comparison.json').exists())
        self.assertEqual(jobs.status(self.work)['state'],'succeeded')
        post.assert_called_once()

    def test_removed_commands_are_unavailable(self):
        for command in ['prepare','compare','show']:
            result=subprocess.run([sys.executable,str(ROOT/'scripts/media.py'),command],cwd=self.work,
                                  text=True,capture_output=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('invalid choice',result.stderr)

    def test_missing_cost_never_posts(self):
        (self.work/'volcengine/cost.json').unlink()
        with patch.object(volcengine,'request') as post:
            with self.assertRaises(FileNotFoundError):
                jobs.submit(self.work,self.spec,'TEST CONFIRMATION')
            post.assert_not_called()
        self.assertFalse((self.work/'submit-001.json').exists())

    def test_explicit_uncertainty_acceptance_uses_saved_cost(self):
        cost=jobs.read(self.work/'volcengine/cost.json')
        cost['result']['amount']={'min':0.12,'max':None}
        jobs.write(self.work/'volcengine/cost.json',cost)
        with config_fixture({'VOLCENGINE_API_KEY':'fixture-only'}), \
             patch.object(volcengine,'request',return_value={'data':[{'url':'https://example.com/cat.png'}]}) as post:
            jobs.submit(self.work,self.spec,'TEST: accept unknown upper cost',accept_uncertain=True)
            post.assert_called_once()
        self.assertTrue(jobs.read(self.work/'submit-001.json')['execution']['approval']['accept_uncertain_cost'])
