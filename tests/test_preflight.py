"""运行前检查/修复的离线测试：真实网络和安装命令均替换为 mock。"""
import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from core import preflight, envfile, jobs
from cost_fixture import save_with_cost
from core.request import compile_request
from core.estimate import estimate
from providers import configured, volcengine


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.old = Path.cwd()
        os.chdir(self.directory.name)
        self.addCleanup(os.chdir, self.old)
        self.path = Path('.env')

    def test_env_variables_are_ignored(self):
        with patch.dict(os.environ, {'VOLCENGINE_API_KEY': 'env-only', 'BYTEPLUS_API_KEY': 'env-only'}):
            self.assertEqual(configured(), [])
            self.path.write_text('VOLCENGINE_API_KEY=file-only\n')
            self.assertEqual(configured(), ['volcengine'])
            self.assertEqual(envfile.config_value('VOLCENGINE_API_KEY'), 'file-only')

    def test_check_is_read_only_and_hides_keys(self):
        self.path.write_text('BYTEPLUS_API_KEY=secret-test-value\n')
        original = self.path.read_bytes()
        with patch.object(preflight.urllib.request, 'urlopen') as net, patch.object(preflight.subprocess, 'run') as installer:
            result = preflight.check()
            net.assert_not_called()
            installer.assert_not_called()
        self.assertNotIn('secret-test-value', json.dumps(result))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(result['configuration']['suppliers'], [{'id': 'byteplus', 'name': 'BytePlus'}])

    def test_expired_invalid_and_valid_fx(self):
        for date, status in [('2000-01-01T00:00:00Z', 'expired'), ('not-a-date', 'invalid'), ('2099-01-01T00:00:00+08:00', 'ok')]:
            self.path.write_text('USD_CNY=7\nUSD_CNY_EXPIRES_AT='+date+'\n')
            self.assertEqual(envfile.fx_state()['status'], status)
            self.assertEqual(envfile.fx_from_env() is not None, status == 'ok')
        self.path.write_text('USD_CNY=NaN\nUSD_CNY_EXPIRES_AT=2099-01-01T00:00:00Z\n')
        self.assertEqual(envfile.fx_state()['status'], 'invalid')

    def test_update_preserves_config_comments_and_crlf(self):
        self.path.write_bytes(b'# settings\r\nBYTEPLUS_API_KEY=private\r\nUSD_CNY=1 # cached\r\nOTHER=x\r\n')
        preflight.save_exchange_rate(7.1, '2099-01-01T00:00:00+00:00')
        data = self.path.read_bytes()
        self.assertIn(b'BYTEPLUS_API_KEY=private\r\n', data)
        self.assertIn(b'USD_CNY=7.1 # cached\r\n', data)
        self.assertIn(b'OTHER=x\r\n', data)
        self.assertEqual(data.count(b'USD_CNY='), 1)

    def test_rate_update_uses_fixed_pair_and_data_date(self):
        date = dt.datetime.now(dt.timezone.utc).date()
        reply = {'base': 'USD', 'quote': 'CNY', 'date': date.isoformat(), 'rate': 7.1}
        with patch.object(preflight.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(reply).encode())) as net:
            result = preflight.update_exchange_rate()
        self.assertEqual(net.call_args.args[0].full_url, envfile.FX_URL)
        self.assertEqual(envfile.fx_from_env()['usd_cny'], 7.1)
        self.assertEqual(envfile.parse_expiry(result['expires_at']).date(), date+dt.timedelta(days=7))

    def test_bad_network_preserves_original(self):
        self.path.write_text('USD_CNY=7\nUSD_CNY_EXPIRES_AT=2000-01-01T00:00:00Z\n')
        original = self.path.read_bytes()
        with patch.object(preflight.urllib.request, 'urlopen', side_effect=OSError('private-url')):
            result = preflight.doctor(exchange_rate=True)
        self.assertEqual(result['repairs'][0]['status'], 'failed')
        self.assertEqual(self.path.read_bytes(), original)
        self.assertNotIn('private-url', json.dumps(result))

    def test_wrong_pair_stale_future_or_invalid_rate_never_writes(self):
        date = dt.datetime.now(dt.timezone.utc).date()
        for changes in [{'quote':'EUR'}, {'date':'2000-01-01'}, {'date':(date+dt.timedelta(days=1)).isoformat()}, {'rate':-1}, {'rate':float('inf')}]:
            reply = {'base':'USD','quote':'CNY','date':date.isoformat(),'rate':7}
            reply.update(changes)
            with patch.object(preflight.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(reply).encode())):
                with self.assertRaises(ValueError):
                    preflight.update_exchange_rate()
            self.assertFalse(self.path.exists())

    def test_dependencies_install_and_recheck(self):
        available = {'npx':'/npx','brew':'/brew'}
        calls = []
        skill = {'ready':False}
        def install(command):
            calls.append(command)
            if command[0] == 'npx': skill['ready'] = True
            if command[0] == 'brew': available['ffprobe']='/ffprobe'
            return True
        with patch.object(preflight, 'skill_status', side_effect=lambda:{'status':'ok' if skill['ready'] else 'missing'}), patch.object(preflight.shutil,'which',side_effect=available.get), patch.object(preflight,'run_installer',side_effect=install):
            result=preflight.repair_dependencies()
        self.assertEqual([r['status'] for r in result], ['repaired','repaired'])
        self.assertEqual(calls[-1], ['brew','install','ffmpeg'])

    def test_dependency_missing_installers(self):
        with patch.object(preflight,'skill_status',return_value={'status':'missing'}), patch.object(preflight.shutil,'which',return_value=None):
            results=preflight.repair_dependencies()
        self.assertEqual([r['status'] for r in results], ['failed','failed'])

    def test_unreadable_or_empty_skill_not_accepted(self):
        skill=Path('SKILL.md');skill.write_text('')
        with patch.object(jobs,'dependency_paths',return_value=[skill]):
            self.assertEqual(preflight.skill_status()['status'], 'missing')
            skill.write_text('instructions')
            self.assertEqual(preflight.skill_status()['status'], 'ok')

    def test_image_submit_does_not_require_video_optimizer(self):
        self.path.write_text('VOLCENGINE_API_KEY=test-key\n')
        with tempfile.TemporaryDirectory() as d:
            plan=save_with_cost({'provider':'volcengine','model':'seedream-5.0-flash','operation':'text-to-image','prompt':'cat','parameters':{'ratio':'9:16'}},Path(d)/'job')
            with patch.object(preflight,'skill_status',return_value={'status':'missing'}), patch.object(volcengine,'request',return_value={'data':[{'url':'https://example.com/a.png'}]}):
                result=jobs.submit(Path(d)/'job',plan,'TEST CONFIRMATION')
            self.assertEqual(result['state'], 'succeeded')

    def test_expiry_flows_through_saved_cost(self):
        from core.costing import calculate
        spec={'provider':'byteplus','model':'seedream-5.0-flash','operation':'text-to-image','prompt':'cat','parameters':{'ratio':'9:16'},
              'fx':{'usd_cny':7,'expires_at':'2099-01-01T00:00:00Z'}}
        quote=calculate(spec)
        self.assertEqual(quote['calculation']['fx']['expires_at'],spec['fx']['expires_at'])
        self.assertAlmostEqual(quote['result']['conversion']['amount']['min'],.126)
