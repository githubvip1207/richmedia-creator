"""命令行直接提交使用已保存报价，不依赖准备流程或确认哈希。"""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from commands import submit as submit_command, status as status_command
from core import submission_store as store
from core.catalogs import ROOT
from cost_fixture import save_with_cost
from providers.volcengine import client as volcengine
from config_fixture import config_fixture


class DirectCLI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work=Path(self.tmp.name)
        self.spec={'provider':'volcengine','model':'seedream-5.0-flash',
                   'operation':'text-to-image','prompt':'cat','parameters':{'ratio':'1:1'}}
        (self.work/'volcengine').mkdir()
        self.spec = save_with_cost(self.spec, self.work)
        store.write(self.work/'task-spec.json',self.spec)

    def test_cli_submits_and_checks_saved_status_without_plan(self):
        module_spec=importlib.util.spec_from_file_location('direct_cli',ROOT/'scripts/main.py')
        cli=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(cli)
        with config_fixture({'VOLCENGINE_API_KEY':'fixture-only'}), \
             patch.object(volcengine,'request',return_value={'data':[{'url':'https://example.com/cat.png'}]}) as post, \
             patch('providers.estimate',side_effect=AssertionError('No recalculation')), \
             patch.object(cli,'emit'), \
             patch.object(sys,'argv',['main.py','submit','--workdir',str(self.work),
                                     '--request',str(self.work/'task-spec.json'),'--approval-text','TEST: selected supplier']):
            cli.main()
        state=store.read(self.work/'submit-001.json')['execution']
        self.assertEqual(state['state'],'succeeded')
        self.assertEqual(state['compiled']['prompt'],'cat')
        self.assertNotIn('plan_hash',state)
        self.assertFalse((self.work/'plan.json').exists())
        self.assertFalse((self.work/'comparison.json').exists())
        self.assertEqual(status_command.status(self.work)['state'],'succeeded')
        post.assert_called_once()

    def test_removed_commands_are_unavailable(self):
        for command in ['prepare','compare','show','attach-task']:
            result=subprocess.run([sys.executable,str(ROOT/'scripts/main.py'),command],cwd=self.work,
                                  text=True,capture_output=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('invalid choice',result.stderr)

    def test_missing_cost_never_posts(self):
        (self.work/'volcengine-priceing.json').unlink()
        with patch.object(volcengine,'request') as post:
            with self.assertRaises(FileNotFoundError):
                submit_command.submit(self.work,self.spec,'TEST CONFIRMATION')
            post.assert_not_called()
        self.assertFalse((self.work/'submit-001.json').exists())

    def test_explicit_uncertainty_acceptance_uses_saved_cost(self):
        cost=store.read(self.work/'volcengine-priceing.json')
        cost['result']['amount']={'min':0.12,'max':None}
        store.write(self.work/'volcengine-priceing.json',cost)
        with config_fixture({'VOLCENGINE_API_KEY':'fixture-only'}), \
             patch.object(volcengine,'request',return_value={'data':[{'url':'https://example.com/cat.png'}]}) as post:
            submit_command.submit(self.work,self.spec,'TEST: accept unknown upper cost',accept_uncertain=True)
            post.assert_called_once()
        self.assertTrue(store.read(self.work/'submit-001.json')['execution']['approval']['accept_uncertain_cost'])
