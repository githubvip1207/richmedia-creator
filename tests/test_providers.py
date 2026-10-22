# 供应商隔离测试：覆盖密钥、模型 ID、独立币种、离线报价及唯一供应商提交。
# 示例密钥和汇率仅是本地测试数据，不能用于真实请求或实际报价。
"""Supplier isolation, native billing, offline comparisons and one-choice submission."""
import copy
import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from providers import byteplus, volcengine, configured
from config_fixture import config_fixture
from core import jobs
from cost_fixture import save_with_cost
from core.request import compile_request, CATALOGS, ROOT
from core.estimate import estimate


# 构造 BytePlus 视频请求夹具，使用逻辑模型别名和测试优化记录，可用 extra 覆盖场景。
def request(provider='byteplus', **extra):
    s = {'provider':provider,'model':'seedance-2.5','operation':'text-to-video','prompt':'一只熊猫在草坡上打滚。',
         'optimizer':{'skill':'sd25-pe','status':'applied'},'parameters':{'ratio':'16:9','duration':5}}
    s.update(extra)
    return s


# 返回带当天核验日期的固定测试汇率，来源为测试夹具 URL，不能作为实际汇率证据。
def fx():
    return {'usd_cny':6.6781, 'expires_at':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat()}


# 验证供应商模型、凭证、原币费率与素材来源彼此隔离。
class SupplierBehavior(unittest.TestCase):
    # 遍历 BytePlus 模型并检查独立 ID；拒绝将国内 doubao 版本 ID 直接用于 BytePlus。
    def test_all_byteplus_ids_independent(self):
        for alias,m in CATALOGS['byteplus']['models'].items():
            s = request(model=alias) if m['kind']=='video' else {'provider':'byteplus','model':alias,'operation':'text-to-image','prompt':'杯子','parameters':{'ratio':'1:1'}}
            self.assertEqual(compile_request(s)['payload_template']['model'],m['id'])
            self.assertNotIn('doubao',m['id'])
        with self.assertRaises(ValueError):
            compile_request(request(model='doubao-seedance-2-5-260628'))

    # 仅配置国内密钥时，BytePlus 在联网前报缺少自身密钥，不能回退使用国内凭证。
    def test_byteplus_key_never_falls_back_to_domestic_key(self):
        with config_fixture({'VOLCENGINE_API_KEY':'domestic-test'},clear=True),patch('urllib.request.build_opener') as net:
            with self.assertRaisesRegex(ValueError,'BYTEPLUS_API_KEY'):
                byteplus.request('POST','/images/generations',{})
            net.assert_not_called()

    # 模拟 opener，分别检查两家请求的实际目标 URL 与 Authorization 使用各自配置。
    def test_transport_uses_correct_supplier_and_key(self):
        with config_fixture({'VOLCENGINE_API_KEY':'domestic-test','BYTEPLUS_API_KEY':'overseas-test'},clear=True):
            for adapter,key in ((byteplus,'overseas-test'),(volcengine,'domestic-test')):
                with patch('urllib.request.build_opener') as opener:
                    opener.return_value.open.return_value=io.BytesIO(b'{"id":"fixture-task"}')
                    adapter.request('POST','/contents/generations/tasks',{'model':'fixture'})
                    sent=opener.return_value.open.call_args.args[0]
                    self.assertEqual(sent.full_url,adapter.BASE+'/contents/generations/tasks')
                    self.assertEqual(sent.get_header('Authorization'),'Bearer '+key)

    # 验证美元原币估算和 BytePlus 单价；未提供汇率时人民币字段必须未知。
    def test_native_usd_no_fake_cny(self):
        e=estimate(compile_request(request()))
        self.assertEqual(e['currency'],'USD')
        self.assertEqual(e['unit_price_per_million_tokens'],10.7)
        self.assertEqual(e['amount'],e['amount_usd'])
        self.assertIsNone(e['amount_cny'])
        self.assertAlmostEqual(e['amount'][0],48038*10.7/1_000_000,places=6)

    # 按测试汇率验证 BytePlus Pro 图片原币价格与人民币换算，来源保持可追溯。
    def test_image_price_and_fx(self):
        c=compile_request({'provider':'byteplus','model':'seedream-5.0-pro','operation':'text-to-image','prompt':'杯子',
                           'parameters':{'size':'1.5K','ratio':'1:1'}})
        e=estimate(c,fx=fx())
        self.assertEqual(e['amount'],[.045,.045])
        self.assertAlmostEqual(e['amount_cny'][0],.045*6.6781,places=6)
        self.assertIn('expires_at', e['fx'])

    # 将国内人民币价目表交给 BytePlus 任务，应因供应商或币种不匹配而拒绝。
    def test_wrong_supplier_pricing_rejected(self):
        with self.assertRaisesRegex(ValueError,'supplier/currency'):
            estimate(compile_request(request()),pricing=jobs.read(ROOT/'models/volcengine-pricing.json'))

    # 验证参考视频按输入加输出时长计 Token，并使用 BytePlus 有视频美元费率。
    # 未独立验证最低计费门槛时，金额上界必须保持未知。
    def test_usd_reference_rate_includes_input_duration(self):
        a={'kind':'video','source':'https://example.com/ref.mp4','purpose':'动作参考','metadata':{'duration':10}}
        c=compile_request(request(operation='reference-to-video', mode='reference',assets=[a],parameters={'ratio':'16:9','duration':10,'resolution':'720p'}))
        e=estimate(c)
        self.assertEqual(e['tokens'][0],432000)
        self.assertEqual(e['unit_price_per_million_tokens'],6.4)
        self.assertEqual(e['amount'][0],2.7648)
        self.assertIsNone(e['amount'][1])  # Separate minimum floor is not yet verified.

    # 将国内素材 ID 用于 BytePlus 时，provenance.provider 不匹配应直接拒绝。
    def test_supplier_scoped_asset_id(self):
        a={'kind':'image','source':'asset://test-asset','purpose':'角色参考','role':'first_frame',
           'provenance':{'provider':'volcengine'}}
        with self.assertRaisesRegex(ValueError,'supplier/account scoped'):
            compile_request(request(operation='image-to-video', mode='first-frame',assets=[a]))


class SelectedSupplierSubmission(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.enterContext(config_fixture({'VOLCENGINE_API_KEY':'domestic-test','BYTEPLUS_API_KEY':'overseas-test'},clear=True))
        for name in ('volcengine','byteplus'):
            save_with_cost(request(name),self.root)

    def test_multi_configuration_requires_selection(self):
        spec=request();spec.pop('provider')
        with self.assertRaisesRegex(ValueError,'Multiple suppliers'):
            compile_request(spec)

    def test_only_selected_supplier_is_submitted_once(self):
        with patch('core.preflight.skill_status',return_value={'status':'ok'}), \
             patch.object(byteplus,'request',return_value={'id':'byteplus-fixture'}) as overseas, \
             patch.object(volcengine,'request') as domestic:
            state=jobs.submit(self.root,request(),'TEST FIXTURE: choose BytePlus')
            self.assertEqual(state['provider'],'byteplus')
            self.assertEqual(overseas.call_args.args[2]['model'],'dreamina-seedance-2-5-260628')
            with self.assertRaisesRegex(ValueError,'already attempted'):
                jobs.submit(self.root,request('volcengine'),'TEST FIXTURE')
            overseas.assert_called_once();domestic.assert_not_called()
        with patch.object(byteplus,'status',return_value={'id':'byteplus-fixture','status':'running'}) as selected, \
             patch.object(volcengine,'status') as other:
            jobs.status(self.root)
            selected.assert_called_once();other.assert_not_called()

    def test_timeout_does_not_fail_over(self):
        with patch('core.preflight.skill_status',return_value={'status':'ok'}), \
             patch.object(byteplus,'request',side_effect=byteplus.ProviderError('fixture timeout',True)), \
             patch.object(volcengine,'request') as domestic:
            with self.assertRaises(byteplus.ProviderError):
                jobs.submit(self.root,request(),'TEST FIXTURE')
            self.assertEqual(jobs.read(self.root/'submit-001.json')['execution']['state'],'submission_unknown')
            with self.assertRaisesRegex(ValueError,'already attempted'):
                jobs.submit(self.root,request('volcengine'),'TEST FIXTURE')
            domestic.assert_not_called()


if __name__=='__main__':
    unittest.main()
