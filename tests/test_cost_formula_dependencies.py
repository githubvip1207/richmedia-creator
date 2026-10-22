"""Formula inputs come from task settings, measured media and explicit billing evidence."""
import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from core.cost_assets import calculate_asset_inputs
from core.costing import consume_quote


class FormulaDependencies(unittest.TestCase):
    def setUp(self):
        self.base = {'provider':'volcengine','model':'seedance-2.5','operation':'text-to-video',
                     'resolution':'480p','ratio':'16:9','duration':4}
        self.probe = self.enterContext(patch('core.cost_assets.probe_asset', side_effect=self.measure))

    def measure(self, asset):
        source = asset['source']
        metadata = {'width':1280,'height':720} if asset['kind'] != 'audio' else {}
        if 'portrait' in source:
            metadata.update(width=720,height=1280)
        if 'arbitrary' in source:
            metadata.update(width=1300,height=1000)
        if asset['kind'] in ('video','audio'):
            metadata['duration'] = 12.0 if 'long' in source else 8.0
        if 'short' in source:
            metadata['duration'] = 1.0
        return {**asset, 'metadata':metadata}

    def asset(self, kind, name='reference'):
        return {'kind':kind,'source':'https://example.com/'+name}

    def quote(self, **updates):
        return calculate_asset_inputs({**self.base, **updates})

    def test_rejects_missing_references_and_incompatible_audio(self):
        cases = [
            {'operation':'reference-to-video', 'mode': 'reference'},
            {'assets':[self.asset('audio')]},
            {'operation':'image-to-video', 'mode': 'first-frame','ratio':'adaptive','assets':[self.asset('image'),self.asset('audio')]},
            {'operation':'reference-to-video', 'mode': 'reference','model':'seedance-2.0','assets':[self.asset('audio')]},
            {'operation':'reference-to-video', 'mode': 'reference','assets':[self.asset('audio','short')]},
            {'operation':'reference-to-video', 'mode': 'reference','assets':[self.asset('audio')]*11},
            {'operation':'reference-to-video', 'mode': 'edit','ratio':'adaptive','duration':-1,'assets':[self.asset('audio')]},
        ]
        for update in cases:
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.quote(**update)
        with self.assertRaises(ValueError):
            calculate_asset_inputs({'provider':'volcengine','model':'seedream-5.0-flash',
                                    'operation':'text-to-image','size':'1K','assets':[self.asset('audio')]})

    def test_audio_is_validated_and_preserved_but_not_added_to_video_seconds(self):
        quote = self.quote(operation='reference-to-video', mode='reference',assets=[self.asset('audio')])
        self.assertEqual(quote['calculation']['input_audio_seconds'],[8])
        self.assertEqual(quote['calculation']['total_input_video_seconds'],0)
        self.assertEqual(quote['calculation']['tokens'],[38430,38430])
        self.assertEqual(quote['calculation']['unit_price_per_million_tokens'],70)

    def test_first_and_last_frame_uses_first_image_ratio_not_input_pixels(self):
        quote = self.quote(operation='image-to-video', mode='first-last-frame',ratio='adaptive',
                           assets=[self.asset('image','portrait'),self.asset('image')])
        estimate = quote['calculation']
        self.assertEqual(estimate['assumed_output_dimensions'],[480,854])
        self.assertEqual(estimate['target_asset_index'],0)
        self.assertEqual(quote['result']['status'],'estimate')
        self.assertEqual(estimate['tokens'],[math.ceil(4*480*854*24/1024)]*2)
        with self.assertRaises(ValueError):
            self.quote(operation='image-to-video', mode='first-last-frame',ratio='adaptive',
                       assets=[self.asset('image'),self.asset('image')],estimate_context={'target_asset_index':1})

    def test_unknown_adaptive_has_an_accepted_resolution_input(self):
        inputs = {**self.base,'operation':'image-to-video', 'mode': 'first-frame','ratio':'adaptive',
                  'assets':[self.asset('image','arbitrary')]}
        unknown = calculate_asset_inputs(inputs)
        self.assertEqual(unknown['result']['status'],'unknown')
        self.assertIn('estimate_context.output_dimensions',[u['field'] for u in unknown['result']['uncertainties'] if u['field'].startswith('estimate_context.') ])
        inputs['estimate_context'] = {'output_dimensions':[728,560]}
        quote = calculate_asset_inputs(inputs)
        self.assertEqual(quote['result']['status'],'estimate')
        self.assertEqual(quote['calculation']['assumed_output_dimensions'],[728,560])
        spec = {'provider':'volcengine','model':'seedance-2.5','operation':'image-to-video', 'mode': 'first-frame','prompt':'测试',
                'parameters':{'resolution':'480p','ratio':'adaptive','duration':4},
                'optimizer':{'skill':'sd25-pe','status':'applied'},
                'assets':[{**inputs['assets'][0],'purpose':'首帧','role':'first_frame',
                           'metadata':self.measure(inputs['assets'][0])['metadata']}]}
        self.assertEqual(consume_quote(spec,quote)[3],quote['result'])
        changed = copy.deepcopy(spec)
        changed['estimate_context'] = {'output_dimensions':[640,640]}
        with self.assertRaisesRegex(ValueError,'differs'):
            consume_quote(changed,quote)

    def test_edit_target_and_floor_range_resolve_all_formula_dependencies(self):
        assets=[self.asset('video'),self.asset('video','portrait-long')]
        unknown = self.quote(operation='reference-to-video', mode='edit',ratio='adaptive',duration=-1,assets=assets)
        self.assertEqual(unknown['result']['status'],'unknown')
        context={'target_asset_index':1,'minimum_billable_tokens':[100000,500000],
                 'minimum_tokens_source':'https://docs.volcengine.com/test-fixture'}
        quote=self.quote(operation='reference-to-video', mode='edit',ratio='adaptive',duration=-1,assets=assets,estimate_context=context)
        estimate=quote['calculation']
        self.assertEqual(estimate['assumed_output_dimensions'],[480,854])
        self.assertEqual(estimate['assumed_output_duration'],[11.6,12])
        self.assertEqual(estimate['total_input_video_seconds'],20)
        raw=[math.ceil((20+d)*480*854*24/1024) for d in (11.6,12)]
        expected=[max(raw[0],100000),max(raw[1],500000)]
        self.assertEqual(estimate['formula_tokens'],raw)
        self.assertEqual(estimate['tokens'],expected)
        self.assertEqual(list(quote['result']['amount'].values()),[round(t*42/1_000_000,6) for t in expected])
        self.assertEqual([u['field'] for u in quote['result']['uncertainties'] if u['field'].startswith('estimate_context.')],[])
        with self.assertRaisesRegex(ValueError,'entire duration range'):
            self.quote(operation='reference-to-video', mode='edit',ratio='adaptive',duration=-1,assets=assets,
                       estimate_context={**context,'minimum_billable_tokens':100000})

    def test_fixed_duration_floor_and_extension(self):
        quote=self.quote(operation='extend-video', mode='after',ratio='adaptive',duration=4,assets=[self.asset('video')],
                         estimate_context={'minimum_billable_tokens':200000,
                                           'minimum_tokens_source':'https://docs.volcengine.com/test-fixture'})
        self.assertEqual(quote['calculation']['tokens'],[200000,200000])
        self.assertEqual(list(quote['result']['amount'].values()),[8.4,8.4])
        self.assertEqual(quote['calculation']['assumed_output_dimensions'],[854,480])

    def test_image_formula_dependency_breakdown(self):
        quote=calculate_asset_inputs({'provider':'volcengine','model':'seedream-5.0-pro',
                                      'operation':'image-to-image','size':'2K','assets':[self.asset('image')]*3})
        self.assertEqual(list(quote['result']['amount'].values()),[0.64,0.64])
        calculation=quote['calculation']
        self.assertEqual(calculation['extra_input_images'],2)
        self.assertEqual(calculation['extra_input_unit_price'],0.02)
        self.assertEqual(calculation['extra_input_cost'],0.04)
        layers=calculate_asset_inputs({'provider':'volcengine','model':'seedream-5.0-pro',
                                       'operation':'decompose-layers','size':'auto','assets':[self.asset('image')]})
        self.assertEqual(list(layers['result']['amount'].values()),[0.15,5.1])
        self.assertEqual(layers['calculation']['output_count_range'],[1,17])

    def test_cli_resolves_adaptive_dimensions_and_verified_floor_evidence(self):
        import json
        import os
        import subprocess
        import tempfile
        from core.request import ROOT
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)
            tool=work/'ffprobe'
            tool.write_text('#!'+sys.executable+'\nimport json\nprint(json.dumps({"streams":[{"codec_type":"video","width":1280,"height":720,"duration":"8"}]}))\n')
            tool.chmod(0o700)
            source=work/'source.mp4';source.touch()
            data={**self.base,'operation':'reference-to-video', 'mode': 'edit','ratio':'adaptive','duration':-1,
                  'assets':[{'kind':'video','source':str(source)}],
                  'estimate_context':{'minimum_billable_tokens':[100000,200000],
                                      'minimum_tokens_source':'https://docs.volcengine.com/test-fixture'}}
            run=subprocess.run([sys.executable,str(ROOT/'scripts/media.py'),'estimate-cost','--workdir',str(work)],
                               input=json.dumps(data),capture_output=True,text=True,cwd=work,
                               env={**os.environ,'PATH':str(work)+os.pathsep+os.environ.get('PATH','')})
            self.assertEqual(run.returncode,0,run.stderr)
            quote=json.loads(run.stdout)
            self.assertEqual(quote,json.loads((work/'volcengine/cost.json').read_text()))
            self.assertEqual(quote['input'],data)
            self.assertEqual(quote['calculation']['assumed_output_dimensions'],[854,480])
            self.assertEqual(quote['calculation']['assumed_output_duration'],[7.6,8])
            self.assertEqual(list(quote['result']['amount'].values()),[round(math.ceil((8+7.6)*854*480*24/1024)*42/1_000_000,6),8.4])
