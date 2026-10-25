"""Video web search: API transport, confirmation binding and usage audit."""
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from test_native_video import request, prepare
from core.request import compile_request
from core.cost_quote import consume_quote
from core.media_probe import calculate_asset_inputs
from core import submission_store as store
from providers import volcengine
from providers.transport import payload
from commands import submit, status, estimate_cost
from config_fixture import config_fixture

TOOL = [{'type':'web_search'}]


class VideoWebSearch(unittest.TestCase):
    def test_every_volcengine_model_and_mode_preserves_search_setting(self):
        for model in ('seedance-2.5','seedance-2.0','seedance-2.0-fast','seedance-2.0-mini'):
            for mode in (None,'first-frame','first-last-frame'):
                with self.subTest(model=model,mode=mode), tempfile.TemporaryDirectory() as tmp:
                    spec=request(model=model,mode=mode); spec['payload']['tools']=copy.deepcopy(TOOL)
                    before=copy.deepcopy(spec); quote=prepare(Path(tmp),spec)
                    _,compiled,_,_=consume_quote(spec,quote)
                    self.assertEqual(payload({'compiled':compiled})['tools'],TOOL)
                    self.assertEqual(compiled['prompt'],spec['original_prompt'])
                    self.assertEqual(spec,before)
                    self.assertNotIn('tools',quote['input'])
                    self.assertNotIn('tools',quote['calculation'])
                    self.assertEqual(quote['result']['status'],'estimate' if model=='seedance-2.5' or mode is None else 'unknown')
                    self.assertNotIn('tools.web_search_cost',[u['field'] for u in quote['result']['uncertainties']])

    def test_only_documented_tool_shape_is_accepted(self):
        for tools in (None,True,{},'web_search',[{'type':'other'}],TOOL*2,
                      [{'type':'web_search','limit':1}],[{'name':'web_search'}]):
            with self.subTest(tools=tools):
                spec=request();spec['payload']['tools']=tools
                with self.assertRaises(ValueError):compile_request(spec)
        for tools in ([],TOOL):
            spec=request();spec['payload']['tools']=tools
            self.assertEqual(compile_request(spec)['parameters']['tools'],tools)

    def test_byteplus_and_image_tools_are_not_silently_enabled(self):
        spec=request(provider='byteplus');spec['payload']['tools']=TOOL
        with self.assertRaisesRegex(ValueError,'Volcengine'):compile_request(spec)
        for provider,op in [('byteplus','text-to-video'),('volcengine','text-to-image')]:
            inputs={'provider':provider,'model':'seedance-2.5' if op=='text-to-video' else 'seedream-5.0-flash',
                    'operation':op,'tools':TOOL,'resolution':'480p','ratio':'16:9','duration':4}
            with self.assertRaisesRegex(ValueError,'Unknown cost input fields'):calculate_asset_inputs(inputs)

    def test_requirement_binds_both_enabling_and_disabling_search(self):
        for enabled in (False,True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);spec=request()
                spec['payload']['tools']=copy.deepcopy(TOOL) if enabled else []
                quote=prepare(work,spec)
                spec['payload']['tools']=[] if enabled else copy.deepcopy(TOOL)
                consume_quote(spec,quote)
                with patch.object(volcengine,'request') as post, self.assertRaisesRegex(ValueError,'search settings'):
                    submit.submit(work,spec,'TEST')
                post.assert_not_called()

    def test_requirement_binds_search_even_though_it_does_not_change_video_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);spec=request();spec['payload']['tools']=TOOL;prepare(work,spec)
            record=store.read(work/'request.json');record['providers']['volcengine']['parameters']['tools']=[]
            store.write(work/'request.json',record)
            with patch.object(volcengine,'request') as post, self.assertRaisesRegex(ValueError,'search settings'):
                submit.submit(work,spec,'TEST',accept_uncertain=True)
            post.assert_not_called()

    def test_submit_retains_tool_usage_without_inventing_a_search_fee(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);spec=request();spec['payload']['tools']=TOOL;prepare(work,spec)
            with config_fixture({'VOLCENGINE_API_KEY':'fixture'}),patch('commands.submit.require_dependencies'), \
                    patch.object(volcengine,'request',return_value={'id':'task'}) as post:
                state=submit.submit(work,spec,'TEST')
            post.assert_called_once_with('POST','/contents/generations/tasks',spec['payload'])
            usage={'completion_tokens':100,'tool_usage':{'web_search':1}}
            with patch.object(volcengine,'status',return_value={'id':'task','status':'succeeded','usage':usage}):
                checked=status.status(state['submission'])
            self.assertEqual(checked['usage'],usage)
            self.assertEqual(store.read(state['submission'])['queries'][-1]['response']['usage'],usage)

    def test_tools_are_generation_options_not_cost_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);spec=request();spec['payload']['tools']=[];plain=prepare(work,spec)
            spec['payload']['tools']=TOOL;search=prepare(work,spec)
            self.assertEqual(search['result'],plain['result'])
            self.assertNotIn('tools',search['input'])
            self.assertNotIn('tools',search['calculation'])
            self.assertFalse(any('search' in step['name'] for step in search['calculation']['steps']))
            invalid={**search['input'],'tools':TOOL}
            with patch('sys.stdin',io.StringIO(json.dumps(invalid))), self.assertRaisesRegex(ValueError,'Unknown cost input fields'):
                estimate_cost.run(SimpleNamespace(workdir=tmp))

    def test_recorded_disabled_search_rejects_implicit_enabled_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);spec=request();prepare(work,spec)
            record=store.read(work/'request.json')
            record['providers']['volcengine']['parameters']['tools']=[]
            store.write(work/'request.json',record)
            with patch.object(volcengine,'request') as post, self.assertRaisesRegex(ValueError,'search settings'):
                submit.submit(work,spec,'TEST')
            post.assert_not_called()

    def test_implicit_default_is_sent_in_actual_post_without_changing_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);spec=request();prepare(work,spec)
            record=store.read(work/'request.json')
            record['providers']['volcengine']['parameters'].pop('tools')
            store.write(work/'request.json',record)
            with config_fixture({'VOLCENGINE_API_KEY':'fixture'}),patch('commands.submit.require_dependencies'), \
                    patch.object(volcengine,'request',return_value={'id':'task'}) as post:
                submit.submit(work,spec,'TEST')
            self.assertEqual(post.call_args.args[2]['tools'],TOOL)
            self.assertEqual(post.call_args.args[2]['content'],spec['payload']['content'])
            self.assertNotIn('tools',spec['payload'])

    def test_omitting_tools_keeps_existing_quote_and_approval_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec=request();quote=prepare(Path(tmp),spec)
            self.assertEqual(quote['result']['status'],'estimate')
            self.assertEqual(quote['result']['amount']['min'],quote['result']['amount']['max'])
            self.assertNotIn('tools',quote['calculation'])
            _,compiled,_,_=consume_quote(spec,quote)
            self.assertEqual(payload({'compiled':compiled})['tools'],TOOL)
