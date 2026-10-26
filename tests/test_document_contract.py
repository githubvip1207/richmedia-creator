"""对文档约定的命令行接口执行回归检查；全部付费调用均使用模拟对象。"""
import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from commands import submit as submit_command, deliver as download_command
from core import dependencies
from core import submission_store as store
from providers import compile_request
from core.catalogs import ROOT
from providers.volcengine import client as volcengine
from providers.byteplus import client as byteplus
from config_fixture import config_fixture
from cost_fixture import save_with_cost
from test_runtime import png

REAL_DEPENDENCIES = dependencies.require_dependencies


def image(provider='volcengine'):
    prefix = 'doubao' if provider == 'volcengine' else 'dola'
    return {'provider':provider, 'operation':'text-to-image', 'original_prompt':'生成熊猫\n保留蓝色背景',
            'payload':{'model':prefix+'-seedream-5-0-flash-260915','prompt':'生成熊猫\n保留蓝色背景',
                       'size':'1K','output_format':'png','response_format':'url','watermark':False,
                       'background':'opaque','layer_decomposition':False}}


class DocumentContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.spec = save_with_cost(image(), self.work)

    def assert_no_post(self, spec, message=None):
        with config_fixture({'VOLCENGINE_API_KEY':'fixture-key'}), patch.object(volcengine,'request') as post:
            with self.assertRaises((ValueError, FileNotFoundError)) as error:
                submit_command.submit(self.work,spec,'TEST CONFIRMATION')
            if message:
                self.assertIn(message,str(error.exception))
            post.assert_not_called()
        self.assertFalse((self.work/'submit-001.json').exists())
        self.assertFalse((self.work/'payload.json').exists())

    def test_changed_prompt_is_blocked_without_changing_quote(self):
        self.spec['payload']['prompt']='生成老虎'
        self.assert_no_post(self.spec,'optimized_prompt')

    def test_original_words_cannot_be_replaced_with_summary(self):
        self.spec['original_prompt']='熊猫背景需求摘要'
        self.assert_no_post(self.spec,'original_prompt')

    def test_supplier_plan_model_size_and_operation_are_bound(self):
        before=store.read(self.work/'request.json')
        for field, value in [('model','seedream-5.0-pro'), ('parameters',{'size':'2K'}), ('operation','image-to-image')]:
            record=copy.deepcopy(before)
            record['providers']['volcengine'][field]=value
            store.write(self.work/'request.json',record)
            self.assert_no_post(self.spec,'differs')

    def test_supplier_must_be_listed_in_current_requirement(self):
        record=store.read(self.work/'request.json');record['providers']={}
        store.write(self.work/'request.json',record)
        self.assert_no_post(self.spec,'absent')

    def test_missing_requirement_never_posts(self):
        (self.work/'request.json').unlink()
        self.assert_no_post(self.spec)

    def test_exact_ratio_must_match_pixel_dimensions(self):
        self.spec['payload']['size']='1280x720'
        save_with_cost(self.spec,self.work)
        record=store.read(self.work/'request.json')
        record['providers']['volcengine']['parameters']['ratio']='1:1'
        store.write(self.work/'request.json',record)
        self.assert_no_post(self.spec,'ratio')

    def test_both_suppliers_reject_changes_to_fixed_output_settings(self):
        for provider in ('volcengine','byteplus'):
            for field,value in [('output_format','jpeg'),('response_format','b64_json'),('watermark',True),
                                ('background','transparent'),('layer_decomposition',True),
                                ('optimize_prompt_options',{'mode':'standard'})]:
                with self.subTest(provider=provider,field=field):
                    spec=image(provider);spec['payload'][field]=value
                    with self.assertRaises(ValueError):compile_request(spec)

    def test_missing_required_payload_fields_are_rejected(self):
        for key in image()['payload']:
            with self.subTest(field=key):
                spec=image();spec['payload'].pop(key)
                with self.assertRaises(ValueError):compile_request(spec)

    def test_both_dependencies_are_required_before_post(self):
        for skill,probe,expected in [('missing','/fixture/ffprobe','sd25-pe'),('ok',None,'ffprobe')]:
            with self.subTest(dependency=expected), config_fixture({'VOLCENGINE_API_KEY':'fixture-key'}), \
                    patch('commands.submit.require_dependencies',new=REAL_DEPENDENCIES), \
                    patch.object(dependencies, 'skill_status',return_value={'status':skill}), \
                    patch.object(dependencies.shutil,'which',return_value=probe), patch.object(volcengine,'request') as post:
                with self.assertRaisesRegex(ValueError,expected):
                    submit_command.submit(self.work,self.spec,'TEST CONFIRMATION')
                post.assert_not_called()
                self.assertFalse((self.work/'submit-001.json').exists())

    def test_legacy_envelope_is_blocked_at_submission_boundary(self):
        legacy={'provider':'volcengine','model':'seedream-5.0-flash','operation':'text-to-image',
                'prompt':'生成熊猫','parameters':{'ratio':'1:1'}}
        self.assert_no_post(legacy,'provider-native payload')

    def test_prompt_is_posted_verbatim_and_payload_file_is_saved(self):
        with config_fixture({'VOLCENGINE_API_KEY':'fixture-key'}), \
                patch.object(volcengine,'request',return_value={'data':[{'url':'https://example.com/result.png'}]}) as post:
            state=submit_command.submit(self.work,self.spec,'TEST CONFIRMATION')
        self.assertEqual(post.call_args.args[2],self.spec['payload'])
        self.assertEqual(post.call_args.args[2]['prompt'],self.spec['original_prompt'])
        self.assertEqual(store.read(self.work/'payload.json'),self.spec)
        self.assertEqual(store.read(state['submission'])['payload'],self.spec['payload'])

    def test_top_level_error_is_rejected_with_specific_reason(self):
        with config_fixture({'VOLCENGINE_API_KEY':'fixture-key'}), \
                patch.object(volcengine,'request',return_value={'error':{'code':'InvalidParameter','message':'size is not supported'}}) as post:
            with self.assertRaisesRegex(volcengine.ProviderError,'size is not supported'):
                submit_command.submit(self.work,self.spec,'TEST CONFIRMATION')
        post.assert_called_once()
        record=store.read(self.work/'submit-001.json')
        self.assertEqual(record['execution']['state'],'rejected')
        self.assertEqual(record['response']['error']['code'],'InvalidParameter')

    def test_http_error_retains_sanitized_diagnostics_and_blocks_unknown_retry(self):
        for status,state in [(400,'rejected'),(503,'submission_unknown')]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);save_with_cost(self.spec,work)
                body={'error':{'code':'InvalidParameter' if status==400 else 'InternalError',
                       'message':'size invalid; fixture-key https://example.com/private?sig=secret data:image/png;base64,PRIVATE'}}
                http=urllib.error.HTTPError(volcengine.BASE,status,'fixture',{'X-Request-Id':'fixture-rid'},io.BytesIO(json.dumps(body).encode()))
                with config_fixture({'VOLCENGINE_API_KEY':'fixture-key'}), patch('urllib.request.build_opener') as opener:
                    opener.return_value.open.side_effect=http
                    with self.assertRaises(volcengine.ProviderError):submit_command.submit(work,self.spec,'TEST CONFIRMATION')
                    if status==503:
                        with self.assertRaises(ValueError):submit_command.submit(work,self.spec,'TEST AGAIN')
                self.assertEqual(opener.return_value.open.call_count,1)
                record=store.read(work/'submit-001.json')
                self.assertEqual(record['execution']['state'],state)
                error=record['response']['error']
                self.assertIn('size invalid',error['message'])
                self.assertEqual(error['request_id'],'fixture-rid')
                for private in ('fixture-key','sig=secret','PRIVATE'):
                    self.assertNotIn(private,json.dumps(error))

    def test_read_only_http_error_does_not_imply_unknown_submission(self):
        error=urllib.error.HTTPError(volcengine.BASE,503,'fixture',{},io.BytesIO(b'{"error":{"message":"temporarily unavailable"}}'))
        with config_fixture({'VOLCENGINE_API_KEY':'fixture-key'}), patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=error
            with self.assertRaises(volcengine.ProviderError) as caught:
                volcengine.status('fixture-task')
        self.assertFalse(caught.exception.uncertain)
        self.assertIn('temporarily unavailable',str(caught.exception))

    def test_legacy_download_manifest_remains_reusable(self):
        spec=self.spec
        with config_fixture({'VOLCENGINE_API_KEY':'fixture-key'}), \
                patch.object(volcengine,'request',return_value={'data':[{'url':'https://example.com/result.png'}]}):
            state=submit_command.submit(self.work,spec,'TEST CONFIRMATION')
        output=self.work/'outputs'/'submit-001';output.mkdir(parents=True)
        file=output/'00-image.png';file.write_bytes(png())
        record=store.read(state['submission'])
        record['result']={'files':[{'path':str(file),'sha256':download_command.sha256_file(file)}]}
        store.write(state['submission'],record)
        with patch('core.download.download_url') as get:
            result=download_command._download(state['submission'])
        get.assert_not_called()
        self.assertEqual(Path(result['files'][0]['path']).resolve(),file.resolve())

    def test_estimate_cli_returns_existing_documented_quote_path(self):
        module=importlib.util.spec_from_file_location('contract_cli',ROOT/'scripts/main.py')
        cli=importlib.util.module_from_spec(module);module.loader.exec_module(cli)
        inputs={'provider':'volcengine','model':'seedream-5.0-flash','operation':'text-to-image','size':'1K'}
        with patch.object(sys,'argv',['main.py','cost','--workdir',str(self.work)]), \
                patch.object(sys,'stdin',io.StringIO(json.dumps(inputs))), patch.object(cli,'emit') as emit:
            cli.main()
        result=emit.call_args.args[0]
        self.assertEqual(Path(result['cost_file']).resolve(),(self.work/'volcengine-priceing.json').resolve())
        self.assertEqual(store.read(result['cost_file']),{k:result[k] for k in ('input','calculation','result')})

    def test_documented_cli_lifecycle_for_both_suppliers(self):
        from commands import init as init_command
        module=importlib.util.spec_from_file_location('lifecycle_cli',ROOT/'scripts/main.py')
        cli=importlib.util.module_from_spec(module);module.loader.exec_module(cli)
        def invoke(arguments, content=None):
            with patch.object(sys,'argv',['main.py',*arguments]), \
                    patch.object(sys,'stdin',io.StringIO(json.dumps(content) if content is not None else '')), \
                    patch.object(cli,'emit') as emit:
                cli.main()
            return emit.call_args.args[0]
        for provider,adapter in [('volcengine',volcengine),('byteplus',byteplus)]:
            with self.subTest(provider=provider), patch.object(init_command,'WORK_ROOT',self.work):
                spec=image(provider)
                requirement={'original_prompt':spec['original_prompt'],'optimized_prompt':spec['payload']['prompt'],
                             'intent':{'operation':'text-to-image'},'assets':[],
                             'providers':{provider:{'model':'seedream-5.0-flash','operation':'text-to-image',
                                                   'parameters':{'size':'1K','ratio':'1:1'},'assets':[]}}}
                task=Path(invoke(['init'],requirement)['workdir'])
                quoted=invoke(['cost','--workdir',str(task)],
                              {'provider':provider,'model':'seedream-5.0-flash','operation':'text-to-image','size':'1K'})
                self.assertTrue(Path(quoted['cost_file']).is_file())
                reply={'data':[{'url':'https://example.com/result.png','output_format':'png'}]}
                with config_fixture({adapter.KEY_ENV:'fixture-key'}),patch.object(adapter,'request',return_value=reply) as post:
                    submitted=invoke(['submit','--workdir',str(task),'--approval-text','TEST CONFIRMATION'],spec)
                post.assert_called_once_with('POST','/images/generations',spec['payload'])
                status=invoke(['status','--submission',submitted['submission']])
                self.assertEqual(status,{'success':True,'error':None})
                with patch('core.download.download_url',side_effect=lambda url,path:path.write_bytes(png())):
                    with patch('commands.deliver.Path.cwd',return_value=self.work):
                        downloaded=invoke(['deliver','--submission',submitted['submission']])
                file=Path(downloaded['files'][0]['path'])
                self.assertEqual(file.parent.parent, self.work.resolve())
                self.assertEqual(file.read_bytes(),png())
                self.assertEqual(store.read(task/'payload.json'),spec)
