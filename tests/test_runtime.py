# 离线行为测试：覆盖费用估算、提交保护与媒体保存。
# 所有生成请求通过 mock 替代，不访问真实付费 API；测试素材与批准文本均为测试夹具。
"""离线行为校验，不调用真实付费 API。"""
import base64
import datetime as dt
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from commands import submit as submit_command, status as status_command, deliver as download_command
from config_fixture import config_fixture
from core import submission_store as store
from cost_fixture import save_with_cost
from core.catalogs import ROOT
from cost_fixture import compile_request
from providers import estimate
from providers.volcengine import client as volcengine


# 构造视频场景夹具；原生请求由 cost_fixture 展开，关键字参数用于覆盖场景。
def video(model='seedance-2.5', operation='text-to-video', **kw):
    s = {'provider':'volcengine','model':model,'operation':operation,'prompt':'固定机位，一只熊猫在草坡上侧滚。'}
    s.update(kw)
    return s


# 构造带角色、用途和已知尺寸/时长的远程素材测试夹具，不实际请求该 URL。
def asset(kind='video',role=None):
    return {'kind':kind,'source':'https://example.com/input.'+('mp4' if kind=='video' else 'png'),
            'role':role or 'reference_'+kind,'purpose':'参考动作',
            'metadata':{'duration':8,'width':1280,'height':720}}


# 仅用标准库构造 400×400、带 Alpha 通道的 PNG 原始字节，供本地素材和下载测试复用。
def png():
    # 构造 PNG 数据块：长度、类型、数据和 CRC 校验码按格式拼接。
    def chunk(kind,data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',400,400,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\xff\0\0\xff'*400)*400))+chunk(b'IEND',b'')


# 验证刊例价估算公式、模型尺寸差异、参考素材成本及未知金额表达。
class PriceBehavior(unittest.TestCase):
    # 独立按像素、帧率及时长计算 Token，核对向上取整和人民币刊例价金额。
    def test_generation_tokens_and_money(self):
        e = estimate(compile_request(video(parameters={'duration':5})))
        expected = (854*480*24*5+1023)//1024
        self.assertEqual(e['tokens'],[expected,expected])
        self.assertEqual(e['unit_price_cny_per_million_tokens'],70)
        self.assertAlmostEqual(e['amount_cny'][0],expected*70/1_000_000,places=6)

    # 验证 2.0 的 480p 采用其独立 864×496 映射，而非直接套用 2.5 尺寸。
    def test_model_specific_pixels(self):
        e = estimate(compile_request(video('seedance-2.0')))
        self.assertEqual(e['assumed_output_dimensions'],[864,496])

    # 输入视频时长必须计入 Token；补充明确门槛后使用公式值和门槛中的较大值。
    def test_reference_video_not_omitted(self):
        c = compile_request(video(operation='reference-to-video', mode='reference',assets=[asset()],parameters={'ratio':'16:9'}))
        e = estimate(c)
        self.assertEqual(e['input_video_seconds'],8)
        self.assertEqual(e['status'],'estimate')
        self.assertGreaterEqual(e['amount_cny'][1], e['amount_cny'][0])
        floor = e['tokens'][0]*2
        from core.pricing import load_pricing
        pricing=load_pricing('volcengine')
        pricing['minimum_token_estimation']['rules']=[{'model':c['model'],
            'resolution':c['parameters']['resolution'],'ratio':c['parameters']['ratio'],
            'duration':c['parameters']['duration'],'tokens':floor,
            'source':'https://docs.volcengine.com/example','verified_on':'2026-10-26'}]
        resolved = estimate(c,pricing=pricing)
        self.assertEqual(resolved['tokens'],[floor,floor])

    # 自适应输出尺寸无法精确预知时，仍提供非零估算并说明不确定性。
    def test_adaptive_estimate_is_nonzero_and_records_uncertainty(self):
        c = compile_request(video(operation='image-to-video', assets=[asset('image','first_frame')]))
        c['assets'][0]['metadata'].update(width=1300, height=1000)
        e = estimate(c)
        self.assertGreater(e['amount_cny'][0], 0)
        self.assertEqual(e['status'],'estimate')
        self.assertTrue(e['uncertainties'])

    # 多图融合的 Pro 报价必须包含第一张之后的输入附加费，图片 Token 仍保持未知。
    def test_image_price_includes_references(self):
        c = compile_request({'provider':'volcengine','model':'seedream-5.0-pro','operation':'image-to-image','prompt':'融合',
                             'parameters':{'size':'1.5K','ratio':'1:1'},'assets':[asset('image')]*3})
        e = estimate(c)
        self.assertIsNone(e['tokens'])
        self.assertEqual(e['amount_cny'],[.34,.34])

    # 图层拆分价格应覆盖一至十七份输出与像素档位，不能只报一张图片价格。
    def test_layers_range_not_single_price(self):
        c = compile_request({'provider':'volcengine','model':'seedream-5.0-pro','operation':'decompose-layers','assets':[asset('image')]})
        self.assertEqual(estimate(c)['amount_cny'],[.15,5.1])


# 验证直接提交、恢复状态及原始媒体保存，生成调用全部模拟。
class JobBehavior(unittest.TestCase):
    # 为每个用例创建独立临时目录，并将测试价格核验日期设为当天。
    # 夹具清理由 unittest 注册；涉及密钥时仅设置不可用于真实请求的测试值。
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)/'job'
        self.pricing = store.read(ROOT/'models/volcengine-pricing.json')
        self.pricing['verified_on'] = dt.datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()

    # 保存当前用例的任务配置与成本，供模拟提交复用。
    def prep(self,spec=None):
        return save_with_cost(spec or video(),self.d,self.pricing)

    def test_cost_recording_is_offline_without_plan(self):
        with patch.object(volcengine,'request',side_effect=AssertionError('network')):
            self.prep()
        self.assertTrue((self.d/'volcengine-priceing.json').exists())
        self.assertFalse((self.d/'plan.json').exists())
        self.assertFalse((self.d/'confirmation.md').exists())

    # 提供本地视频路径时应在编译前置检查中拒绝，不能将其编码为 Base64 发给供应商。
    def test_existing_local_video_is_rejected_before_probe_or_post(self):
        from providers import compile_request as compile_native
        from cost_fixture import as_native
        path = Path(self.tmp.name)/'input.mp4'
        path.write_bytes(b'video')
        source = asset()
        source['source'] = str(path)
        spec = as_native(video(operation='reference-to-video', mode='reference', assets=[source]))
        with patch('core.media_probe.probe_asset') as probe, patch.object(volcengine, 'request') as post:
            with self.assertRaisesRegex(ValueError, 'Video input requires an accessible HTTPS URL'):
                compile_native(spec)
        probe.assert_not_called()
        post.assert_not_called()

    def test_budget_limit_and_missing_conversion_stop_before_post(self):
        from test_native_video import request, prepare
        from providers import consume_quote
        for key, value, message in (('budget_cny', .01, 'exceeds budget'),
                                    ('budget_usd', 100, 'Cannot compare budget with unknown amount/conversion')):
            with self.subTest(budget=key), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                spec = request()
                quote = prepare(work, spec)
                # 先确认基础请求合法，避免因其他前置校验错误而误通过。
                consume_quote(spec, quote)
                spec[key] = value
                with patch.object(volcengine, 'request') as post, \
                        patch('commands.submit.require_dependencies') as dependencies:
                    with self.assertRaisesRegex(ValueError, message):
                        submit_command.submit(work, spec, 'TEST CONFIRMATION')
                post.assert_not_called()
                dependencies.assert_not_called()
                self.assertFalse((work/'submit-001.json').exists())


    # 一次图片提交后读取已保存响应，不因状态检查再次请求供应商。
    def test_image_post_then_saved_status_does_not_call_supplier_again(self):
        h = self.prep({'provider': 'volcengine', 'model': 'seedream-5.0-flash',
                       'operation': 'text-to-image', 'prompt': 'cat', 'parameters': {'ratio': '1:1'}})
        with config_fixture({'VOLCENGINE_API_KEY': 'test-only'}), patch.object(
                volcengine, 'request', return_value={'data': [{'url': 'https://example.com/out.png'}]}) as req:
            submit_command.submit(self.d, h, 'TEST FIXTURE ONLY: confirmed')
            self.assertEqual(status_command.status(self.d)['state'], 'succeeded')
            req.assert_called_once()

    # 模拟结果不确定的超时，验证写入 submission_unknown 后禁止重发，供应商只被调用一次。
    def test_timeout_unknown_never_retries(self):
        h = self.prep({'provider': 'volcengine', 'model': 'seedream-5.0-flash',
                       'operation': 'text-to-image', 'prompt': 'cat', 'parameters': {'ratio': '1:1'}})
        with patch('core.dependencies.skill_status',return_value={'status':'ok'}),config_fixture({'VOLCENGINE_API_KEY':'test-only'}),\
             patch.object(volcengine,'request',side_effect=volcengine.ProviderError('timeout',True)) as req:
            with self.assertRaises(volcengine.ProviderError):
                submit_command.submit(self.d,h,'TEST FIXTURE ONLY: confirmed')
            self.assertEqual(store.read(self.d/'submit-001.json')['execution']['state'],'submission_unknown')
            with self.assertRaises(ValueError):
                submit_command.submit(self.d,h,'TEST FIXTURE ONLY: confirmed')
            self.assertEqual(req.call_count,1)

    # 费用上界未知且没有明确接受标志时，必须在任何供应商请求之前拒绝提交。
    def test_unknown_cost_requires_acceptance_and_accepted_request_posts_once(self):
        from test_native_video import request, prepare
        work = self.d
        work.mkdir()
        spec = request()
        quote = prepare(work, spec)
        quote['result']['amount']['max'] = None
        store.write(work/'volcengine-priceing.json', quote)
        with config_fixture({'VOLCENGINE_API_KEY': 'fixture-only'}), \
                patch('commands.submit.require_dependencies'), \
                patch.object(volcengine, 'request', return_value={'id': 'task'}) as post:
            with self.assertRaisesRegex(ValueError, 'Cost upper estimate unknown'):
                submit_command.submit(work, spec, 'TEST CONFIRMATION')
            post.assert_not_called()
            self.assertFalse((work/'submit-001.json').exists())
            state = submit_command.submit(work, spec, 'TEST ACCEPT UNKNOWN COST', accept_uncertain=True)
        post.assert_called_once()
        self.assertEqual(state['state'], 'queued')
        self.assertTrue(state['approval']['accept_uncertain_cost'])


    # PNG 图层输出保留边界框和用量，并可复用已保存文件。
    def test_layer_download_preserves_metadata_and_png(self):
        spec = {'provider':'volcengine','model':'seedream-5.0-pro','operation':'decompose-layers','assets':[asset('image')],
                'parameters':{'output_format':'png'}}
        self.d.mkdir()
        store.write(self.d/'submit-001.json', {**spec,
                   'execution': {'state':'succeeded','compiled':compile_request(spec)},
                   'response': {'data':[{'b64_json':base64.b64encode(png()).decode(),
                   'z_index':0,'size':'400x400','output_format':'png'},
                   {'b64_json':base64.b64encode(png()).decode(),'z_index':1,
                    'size':'400x400','output_format':'png','name':'element','description':'element',
                    'bounding_box':{'absolute':[1,2,3,4],'normalized':[2,5,7,10]}}],'usage':{'total_tokens':22}}})
        result = download_command._download(self.d)
        self.assertTrue(result['files'][0]['path'].endswith('.png'))
        self.assertEqual(result['files'][1]['origin']['bounding_box']['absolute'],[1,2,3,4])
        self.assertEqual(download_command._download(self.d)['usage']['total_tokens'],22)

    # 缺少真实批准文本时，提交不得创建 job.json，也不能留下已尝试状态。
    def test_missing_approval_does_not_create_attempt(self):
        h = self.prep()
        with self.assertRaises(ValueError):
            submit_command.submit(self.d,h,'')
        self.assertFalse((self.d/'submit-001.json').exists())

    # 本地输入只在提交时转换为 Base64，计划中不保存 data URI。
    # 检查模拟图片同步成功、下载字节保持原样、usage 保留且实际扣费金额仍未知。
    def test_local_image_materialization_and_original_download(self):
        from core.payload import payload
        path = Path(self.tmp.name)/'input.png'
        data = png()
        path.write_bytes(data)
        spec = {'provider':'volcengine','model':'seedream-5.0-pro','operation':'image-to-image',
                'prompt':'把杯子换成蓝色','parameters':{'ratio':'1:1'},
                'assets':[{'kind':'image','source':str(path),'purpose':'编辑原图'}]}
        compiled = compile_request(spec)
        body = payload({'compiled': compiled})
        self.assertTrue(body['image'][0].startswith('data:image/png;base64,'))
        self.assertNotIn('data:image/',json.dumps(compiled))
        self.d.mkdir()
        store.write(self.d/'submit-001.json', {'execution':{'state':'succeeded','compiled':compiled},
                   'response':{'data':[{'b64_json':base64.b64encode(data).decode(),'output_format':'png'}],
                               'usage':{'total_tokens':88}}})
        result = download_command._download(self.d)
        self.assertEqual(Path(result['files'][0]['path']).read_bytes(),data)
        self.assertEqual(result['usage']['total_tokens'],88)
        self.assertIsNone(result['actual_billed_amount_cny'])

    # 模拟带敏感代理 URL 的 URLError，验证保留底层异常类型与原因、隐藏秘密且只调用一次。
    def test_urlerror_reports_sanitized_underlying_reason_without_retry(self):
        import urllib.error
        reason = ConnectionRefusedError('connection refused via https://user:secret@proxy.invalid/path')
        err = urllib.error.URLError(reason)
        with config_fixture({'VOLCENGINE_API_KEY':'test-only'}),patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = err
            with self.assertRaises(volcengine.ProviderError) as caught:
                volcengine.request('POST','/images/generations',{'provider':'volcengine','model':'test'})
            message = str(caught.exception)
            self.assertIn('ConnectionRefusedError', message)
            self.assertIn('connection refused', message)
            self.assertNotIn('secret', message)
            self.assertNotIn('test-only', message)
            self.assertTrue(caught.exception.uncertain)
            self.assertEqual(opener.return_value.open.call_count,1)

    # 模拟 HTTP 503，验证被标记为提交结果未知，且不重试生成、不泄露测试密钥。
    def test_http_error_is_not_retried(self):
        import urllib.error
        from email.message import Message
        headers = Message()
        headers['X-Request-Id'] = 'test-request-id'
        err = urllib.error.HTTPError(volcengine.BASE,503,'unavailable',headers,None)
        with config_fixture({'VOLCENGINE_API_KEY':'test-only'}),patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = err
            with self.assertRaises(volcengine.ProviderError) as caught:
                volcengine.request('POST','/images/generations',{'provider':'volcengine','model':'test'})
            self.assertTrue(caught.exception.uncertain)
            self.assertNotIn('test-only',str(caught.exception))
            self.assertEqual(opener.return_value.open.call_count,1)


if __name__ == '__main__':
    unittest.main()
