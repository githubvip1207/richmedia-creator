# 离线行为测试：覆盖模型参数、估算、不可变计划、提交保护与媒体保存。
# 所有生成请求通过 mock 替代，不访问真实付费 API；测试素材与批准文本均为测试夹具。
"""Offline behavioral checks. No actual paid API is called."""
import base64
import copy
import datetime as dt
import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from config_fixture import config_fixture
from core import jobs
from cost_fixture import save_with_cost
from core.request import compile_request, CATALOG, ROOT
from core.estimate import estimate
from providers import volcengine


# 构造视频请求测试夹具，默认记录已应用优化器；关键字参数可覆盖不同测试场景。
def video(model='seedance-2.5', operation='text-to-video', **kw):
    s = {'provider':'volcengine','model':model,'operation':operation,'prompt':'固定机位，一只熊猫在草坡上侧滚。',
         'optimizer':{'skill':'sd25-pe','status':'applied'}}
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


# 验证模型请求编译的默认值、显式要求、素材角色及不支持选项的拒绝行为。
class ModelBehavior(unittest.TestCase):
    # 遍历国内六种模型，检查逻辑别名映射到目录中的准确供应商模型 ID。
    def test_all_six_models_compile(self):
        for alias,m in CATALOG['models'].items():
            spec = video(alias) if m['kind']=='video' else {'provider':'volcengine','model':alias,'operation':'text-to-image','prompt':'红色杯子','parameters':{'ratio':'1:1'}}
            self.assertEqual(compile_request(spec)['payload_template']['model'],m['id'])

    # 验证视频默认 480p、4 秒且无生成音频；用户明确的分辨率、时长和音频要求优先。
    def test_low_cost_defaults_and_explicit_requirements(self):
        for alias,m in CATALOG['models'].items():
            if m['kind']!='video':
                continue
            p = compile_request(video(alias))['parameters']
            self.assertEqual((p['resolution'],p['duration'],p['generate_audio']),('480p',4,False))
        p = compile_request(video(parameters={'resolution':'1080p','duration':12,'generate_audio':True}))['parameters']
        self.assertEqual((p['resolution'],p['duration'],p['generate_audio']),('1080p',12,True))

    # 验证 2.5 编辑锁定 duration=-1、ratio=adaptive、任务意图 edit；显式冲突时长应拒绝。
    def test_25_edit_lock_and_type(self):
        c = compile_request(video(operation='reference-to-video', mode='edit',assets=[asset()]))
        self.assertEqual(c['parameters']['duration'],-1)
        self.assertEqual(c['parameters']['ratio'],'adaptive')
        self.assertEqual(c['payload_template']['omni_reference_task_type'],'edit')
        with self.assertRaises(ValueError):
            compile_request(video(operation='reference-to-video', mode='edit',assets=[asset()],parameters={'duration':4}))

    # 延长任务缺少分辨率和时长应拒绝；显式提供后保留设置，不套用普通生成默认值。
    def test_extension_needs_own_settings(self):
        with self.assertRaises(ValueError):
            compile_request(video(operation='extend-video', mode='after',assets=[asset()]))
        c = compile_request(video(operation='extend-video', mode='after',assets=[asset()],parameters={'resolution':'720p','duration':8}))
        self.assertEqual(c['parameters']['resolution'],'720p')

    # 覆盖 seed、camera_fixed、frames 和模型不支持的分辨率，要求编译阶段明确拒绝。
    def test_unsupported_parameters_fail(self):
        for parameters in ({'seed':12},{'camera_fixed':True},{'frames':120},{'resolution':'4k'}):
            with self.assertRaises(ValueError):
                compile_request(video(parameters=parameters))
        with self.assertRaises(ValueError):
            compile_request(video('seedance-2.0-mini',parameters={'resolution':'1080p'}))

    # 缺少已应用 sd25-pe 的记录时，Seedance 2.5 编译必须失败。
    def test_require_optimizer(self):
        with self.assertRaises(ValueError):
            compile_request(video(optimizer={}))

    # 验证首帧模式锁定自适应比例，且不能混入普通视频参考素材。
    def test_first_frame_is_not_reference(self):
        img = asset('image','first_frame')
        c = compile_request(video(operation='image-to-video', mode='first-frame',assets=[img]))
        self.assertEqual(c['parameters']['ratio'],'adaptive')
        with self.assertRaises(ValueError):
            compile_request(video(operation='image-to-video', mode='first-frame',assets=[img,asset()]))

    # 2.0 纯音频参考必须失败；2.5 支持对应输入，检查模型能力差异。
    def test_20_audio_needs_visual_reference(self):
        with self.assertRaises(ValueError):
            compile_request(video('seedance-2.0',operation='reference-to-video', mode='reference',assets=[asset('audio')]))
        compile_request(video(operation='reference-to-video', mode='reference',assets=[asset('audio')]))

    # 检查 2.0 单段超长以及 2.5 多段合计超长输入，均应在联网前拒绝。
    def test_video_duration_limits(self):
        a = asset()
        a['metadata']['duration'] = 16
        with self.assertRaises(ValueError):
            compile_request(video('seedance-2.0',operation='reference-to-video', mode='reference',assets=[a]))
        with self.assertRaises(ValueError):
            compile_request(video(operation='reference-to-video', mode='reference',assets=[asset()]*4))

    # 逐项验证 Pro/Flash 模型 ID、1K 默认值、PNG/URL、水印关闭和标准优化。
    # 图片比例只能进入提示词，不能作为独立 API 字段发送。
    def test_seedream_pro_flash_defaults_and_payload_options(self):
        for alias, model_id in (
            ('seedream-5.0-pro', 'doubao-seedream-5-0-pro-260628'),
            ('seedream-5.0-flash', 'doubao-seedream-5-0-flash-260915'),
        ):
            c = compile_request({'provider':'volcengine','model':alias,'operation':'text-to-image','prompt':'小猫','parameters':{'ratio':'4:3'}})
            payload = c['payload_template']
            self.assertEqual(payload['model'], model_id)
            self.assertEqual(payload['size'], '1K')
            self.assertEqual(payload['watermark'], False)
            self.assertEqual(payload['layer_decomposition'], False)
            self.assertNotIn('ratio', payload)
            self.assertIn('构图比例偏好：4:3。', payload['prompt'])
            self.assertEqual(payload['output_format'], 'png')
            self.assertEqual(payload['response_format'], 'url')
            self.assertEqual(payload['optimize_prompt_options'], {'mode':'standard'})

    # 向 Pro 请求顺序组图参数应失败，防止把多输出方案误当成原生单请求组图。
    def test_image_native_group_not_supported(self):
        with self.assertRaises(ValueError):
            compile_request({'provider':'volcengine','model':'seedream-5.0-pro','operation':'text-to-image','prompt':'分镜',
                             'parameters':{'sequential_image_generation':'auto'}})

    # 验证拆分仅接受一张输入、可省略提示词，并正确开启 layer_decomposition。
    def test_layer_single_input(self):
        s = {'provider':'volcengine','model':'seedream-5.0-pro','operation':'decompose-layers','assets':[asset('image')]}
        c = compile_request(s)
        self.assertTrue(c['payload_template']['layer_decomposition'])
        self.assertNotIn('prompt',c['payload_template'])
        s['assets'] *= 2
        with self.assertRaises(ValueError):
            compile_request(s)

    # 对超过 999、边界倒置和坐标数目错误的 bbox 逐一验证拒绝行为。
    def test_region_coordinates_are_normalized_and_ordered(self):
        for coords in ('0 0 1000 999','900 10 100 20','0 0 1'):
            with self.assertRaises(ValueError):
                compile_request({'provider':'volcengine','model':'seedream-5.0-pro','operation':'image-to-image',
                    'prompt':'替换图1<bbox>'+coords+'</bbox>里的杯子','assets':[asset('image')]})

    # 验证过小像素无效；透明编辑必须有经验证的 Alpha 通道，不能只凭输出选项启用。
    def test_image_size_limits_and_transparency(self):
        s = {'provider':'volcengine','model':'seedream-5.0-flash','operation':'text-to-image','prompt':'杯子','parameters':{'size':'512x512'}}
        with self.assertRaises(ValueError):
            compile_request(s)
        s.update(operation='image-to-image',assets=[asset('image')],parameters={'background':'transparent','ratio':'1:1'})
        with self.assertRaises(ValueError):
            compile_request(s)
        s['assets'][0]['metadata']['has_alpha'] = True
        compile_request(s)


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

    # 输入视频时长必须计入 Token；未验证最低门槛时保留未知上界，提供门槛后使用两者较大值。
    def test_reference_video_not_omitted(self):
        c = compile_request(video(operation='reference-to-video', mode='reference',assets=[asset()],parameters={'ratio':'16:9'}))
        e = estimate(c)
        self.assertEqual(e['input_video_seconds'],8)
        self.assertEqual(e['status'],'lower_bound')
        self.assertIsNone(e['amount_cny'][1])
        floor = e['tokens'][0]*2
        resolved = estimate(c,{'minimum_billable_tokens':floor,'minimum_tokens_source':'https://docs.volcengine.com/example'})
        self.assertEqual(resolved['tokens'],[floor,floor])

    # 自适应比例缺少可靠输出尺寸时，金额应为未知，不能按零费用展示。
    def test_adaptive_unknown_not_zero(self):
        c = compile_request(video(operation='image-to-video', mode='first-frame',assets=[asset('image','first_frame')]))
        c['assets'][0]['metadata'].update(width=1300, height=1000)
        e = estimate(c)
        self.assertIsNone(e['amount_cny'])
        self.assertEqual(e['status'],'unknown')

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
        self.pricing = jobs.read(ROOT/'models/volcengine-pricing.json')
        self.pricing['verified_on'] = dt.datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()

    # 保存当前用例的任务配置与成本，供模拟提交复用。
    def prep(self,spec=None):
        return save_with_cost(spec or video(),self.d,self.pricing)

    def test_cost_recording_is_offline_without_plan(self):
        with patch.object(volcengine,'request',side_effect=AssertionError('network')):
            self.prep()
        self.assertTrue((self.d/'volcengine/cost.json').exists())
        self.assertFalse((self.d/'plan.json').exists())
        self.assertFalse((self.d/'confirmation.md').exists())

    # 提供本地视频路径时应在编译前置检查中拒绝，不能将其编码为 Base64 发给供应商。
    def test_local_video_not_sent_as_base64(self):
        path = Path(self.tmp.name)/'input.mp4'
        path.write_bytes(b'video')
        a = asset()
        a['source'] = str(path)
        with self.assertRaisesRegex(ValueError,'not local video Base64'):
            compile_request(video(operation='reference-to-video', mode='reference',assets=[a]))

    def test_budget_unknown_or_exceeded_rejected(self):
        for spec in (video(budget_cny=.01),video(operation='reference-to-video', mode='reference',assets=[asset()],budget_cny=20)):
            self.prep(spec)
            with patch.object(volcengine,'request') as net:
                with self.assertRaises(ValueError):
                    jobs.submit(self.d,spec,'TEST CONFIRMATION')
                net.assert_not_called()
            self.assertFalse((self.d/'submit-001.json').exists())

    # 同一计划只允许一次模拟 POST；再次提交被挡住，已有任务仍可单独查询状态。
    def test_post_once_then_resume_query_and_download(self):
        h = self.prep()
        with patch('core.preflight.skill_status',return_value={'status':'ok'}),config_fixture({'VOLCENGINE_API_KEY':'test-only'}),\
             patch.object(volcengine,'request',return_value={'id':'task-test'}) as req:
            jobs.submit(self.d,h,'TEST FIXTURE ONLY: confirmed')
            with self.assertRaises(ValueError):
                jobs.submit(self.d,h,'TEST FIXTURE ONLY: confirmed')
            self.assertEqual(req.call_count,1)
        with patch.object(volcengine,'status',return_value={'id':'task-test','status':'expired'}):
            self.assertEqual(jobs.status(self.d)['state'],'expired')

    # 模拟结果不确定的超时，验证写入 submission_unknown 后禁止重发，供应商只被调用一次。
    def test_timeout_unknown_never_retries(self):
        h = self.prep()
        with patch('core.preflight.skill_status',return_value={'status':'ok'}),config_fixture({'VOLCENGINE_API_KEY':'test-only'}),\
             patch.object(volcengine,'request',side_effect=volcengine.ProviderError('timeout',True)) as req:
            with self.assertRaises(volcengine.ProviderError):
                jobs.submit(self.d,h,'TEST FIXTURE ONLY: confirmed')
            self.assertEqual(jobs.read(self.d/'submit-001.json')['execution']['state'],'submission_unknown')
            with self.assertRaises(ValueError):
                jobs.submit(self.d,h,'TEST FIXTURE ONLY: confirmed')
            self.assertEqual(req.call_count,1)

    # 费用上界未知且没有明确接受标志时，必须在任何供应商请求之前拒绝提交。
    def test_uncertain_cost_requires_specific_flag(self):
        h = self.prep(video(operation='reference-to-video', mode='reference',assets=[asset()]))
        with patch('core.preflight.skill_status',return_value={'status':'ok'}),config_fixture({'VOLCENGINE_API_KEY':'test-only'}),\
             patch.object(volcengine,'request') as req:
            with self.assertRaises(ValueError):
                jobs.submit(self.d,h,'TEST FIXTURE ONLY: confirmed')
            req.assert_not_called()

    # 即使默认输出为 JPEG，透明图层仍保存 PNG；清单保留边界框、用量，并可重复读取。
    def test_layer_download_preserves_metadata_and_png(self):
        spec = self.prep({'provider':'volcengine','model':'seedream-5.0-pro','operation':'decompose-layers','assets':[asset('image')],
                   'parameters':{'output_format':'jpeg'}})
        jobs.write(self.d/'submit-001.json', {**spec,
                   'execution': {'state':'succeeded','compiled':compile_request(spec)},
                   'response': {'data':[{'b64_json':base64.b64encode(png()).decode(),
                   'z_index':1,'bounding_box':{'absolute':[1,2,3,4]}}],'usage':{'total_tokens':22}}})
        result = jobs.download(self.d)
        self.assertTrue(result['files'][0]['path'].endswith('.png'))
        self.assertEqual(result['files'][0]['origin']['bounding_box']['absolute'],[1,2,3,4])
        self.assertEqual(jobs.download(self.d)['usage']['total_tokens'],22)

    # 缺少真实批准文本时，提交不得创建 job.json，也不能留下已尝试状态。
    def test_missing_approval_does_not_create_attempt(self):
        h = self.prep()
        with self.assertRaises(ValueError):
            jobs.submit(self.d,h,'')
        self.assertFalse((self.d/'submit-001.json').exists())

    # 本地输入只在提交时转换为 Base64，计划中不保存 data URI。
    # 检查模拟图片同步成功、下载字节保持原样、usage 保留且实际扣费金额仍未知。
    def test_image_submit_materializes_and_downloads_once(self):
        path = Path(self.tmp.name)/'input.png'
        data = png()
        path.write_bytes(data)
        h = self.prep({'provider':'volcengine','model':'seedream-5.0-pro','operation':'image-to-image','prompt':'把杯子换成蓝色','parameters':{'ratio':'1:1'},
                      'assets':[{'kind':'image','source':str(path),'purpose':'编辑原图'}]})
        reply = {'data':[{'b64_json':base64.b64encode(data).decode(),'output_format':'png'}],
                 'usage':{'total_tokens':88,'generated_images':1}}
        with patch('core.preflight.skill_status',return_value={'status':'ok'}),config_fixture({'VOLCENGINE_API_KEY':'test-only'}),\
             patch.object(volcengine,'request',return_value=reply) as req:
            state = jobs.submit(self.d,h,'TEST FIXTURE ONLY: confirmed')
            self.assertEqual(state['state'],'succeeded')
            payload = req.call_args.args[2]
            self.assertTrue(payload['image'][0].startswith('data:image/png;base64,'))
            self.assertNotIn('data:image/',(self.d/'submit-001.json').read_text())
        result = jobs.download(self.d)
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
