"""Cost estimates derive billing inputs from media, not agent measurements."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from core.media_probe import calculate_asset_inputs, probe_asset
from core import submission_store as store


class CostAssets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name)/'input.png'
        self.source.touch()

    def image_input(self):
        return {'provider':'volcengine', 'model':'seedream-5.0-pro', 'operation':'image-to-image',
                'size':'1K', 'assets':[{'kind':'image','source':str(self.source)}]}

    def probe_result(self, stream, **kwargs):
        return subprocess.CompletedProcess([], 0, json.dumps({'streams':[stream], **kwargs}), '')

    def test_image_dimensions_count_and_price_are_derived(self):
        spec=self.image_input()
        result=self.probe_result({'codec_type':'video','width':1200,'height':900})
        with patch('core.media_probe.shutil.which', return_value='/bin/ffprobe'), patch('core.media_probe.subprocess.run', return_value=result):
            quote=calculate_asset_inputs(spec)
        self.assertEqual(quote['input'], spec)
        self.assertEqual({k: v for k, v in quote['calculation']['assets'][0].items() if k in ('width','height','duration')}, {'width':1200,'height':900})
        self.assertEqual(quote['calculation']['input_images'], 1)
        self.assertEqual(list(quote['result']['amount'].values()), [0.3,0.3])

    def test_https_video_duration_falls_back_to_format(self):
        spec={'provider':'volcengine','model':'seedance-2.0','operation':'reference-to-video', 'mode': 'reference',
              'resolution':'480p','ratio':'16:9','duration':4,
              'assets':[{'kind':'video','source':'https://example.com/input.mp4'}]}
        result=self.probe_result({'codec_type':'video','width':1280,'height':720,'duration':'N/A'},format={'duration':'8.25'})
        with patch('core.media_probe.shutil.which', return_value='/bin/ffprobe'), patch('core.media_probe.subprocess.run', return_value=result) as run:
            quote=calculate_asset_inputs(spec)
        self.assertEqual(run.call_args.args[0][-1],spec['assets'][0]['source'])
        self.assertEqual(quote['calculation']['input_video_seconds'],[8.25])
        self.assertEqual(quote['calculation']['total_input_video_seconds'],8.25)
        self.assertEqual(quote['result']['status'],'lower_bound')

    def test_no_media_needs_no_ffprobe(self):
        with patch('core.media_probe.shutil.which', side_effect=AssertionError('No media')):
            quote=calculate_asset_inputs({'provider':'byteplus','model':'seedream-5.0-flash','operation':'text-to-image','size':'1K'})
        self.assertEqual(quote['result']['currency'],'USD')

    def test_reject_manual_measurements_and_price_inputs(self):
        for key,value in [('input_images',1),('input_video_seconds',[8]),('pricing','prices.json')]:
            with self.assertRaisesRegex(ValueError,'Unknown cost input'):
                calculate_asset_inputs({**self.image_input(),key:value})

    def test_probe_failure_hides_signed_url(self):
        asset={'kind':'video','source':'https://example.com/video?token=secret'}
        with patch('core.media_probe.shutil.which',return_value='/bin/ffprobe'), patch('core.media_probe.subprocess.run',return_value=subprocess.CompletedProcess([],1,'','secret')):
            with self.assertRaises(ValueError) as error:
                probe_asset(asset)
        self.assertNotIn('secret',str(error.exception))

    def test_missing_file_dependency_and_duration_stop_estimation(self):
        with self.assertRaisesRegex(ValueError,'existing absolute'):
            probe_asset({'kind':'video','source':'/nonexistent/video.mp4'})
        with patch('core.media_probe.shutil.which',return_value=None):
            with self.assertRaisesRegex(ValueError,'ffprobe is required'):
                calculate_asset_inputs(self.image_input())
        with patch('core.media_probe.shutil.which',return_value='/bin/ffprobe'), patch('core.media_probe.subprocess.run',return_value=self.probe_result({'codec_type':'video','width':640,'height':480})):
            with self.assertRaisesRegex(ValueError,'no valid dimensions/duration'):
                probe_asset({'kind':'video','source':str(self.source)})

    def test_asset_id_is_preserved_without_changing_cost(self):
        spec=self.image_input()
        spec['assets'][0]['id']='product'
        result=self.probe_result({'codec_type':'video','width':1200,'height':900})
        with patch('core.media_probe.shutil.which',return_value='/bin/ffprobe'), patch('core.media_probe.subprocess.run',return_value=result):
            quote=calculate_asset_inputs(spec)
        self.assertEqual(quote['input']['assets'][0]['id'],'product')
        self.assertEqual(quote['calculation']['assets'][0]['id'],'product')
        self.assertEqual(list(quote['result']['amount'].values()),[0.3,0.3])

    def test_invalid_asset_id_is_rejected_before_probing(self):
        for identifier in ('', ' ', None, 1):
            with self.subTest(identifier=identifier), patch('core.media_probe.subprocess.run') as probe:
                with self.assertRaisesRegex(ValueError,'Asset id'):
                    probe_asset({'id':identifier,'kind':'image','source':str(self.source)})
                probe.assert_not_called()
