import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import tifffile
from photo_utils import database
from photo_utils.cli import main,build_parser
from photo_utils.processing import plan_cards,process_sheet,ProcessingError
from photo_utils.rotation import publish_rotations

class PrintTests(unittest.TestCase):
    def test_variable_prints_depth_resume_and_original_preservation(self):
        for bg,fg in ((0,40000),(65535,10000)):
            with self.subTest(bg=bg),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);source=root/'sheet.tif'
                image=np.full((800,1000,3),bg,np.uint16)
                image[80:320,80:420]=fg;image[440:720,560:920]=fg
                tifffile.imwrite(source,image,photometric='rgb')
                with database.use_state(root/'state'),contextlib.redirect_stdout(io.StringIO()):
                    sha=database.digest(source);outputs=process_sheet(source,kind='prints')
                    self.assertEqual(len(outputs),2)
                    self.assertTrue(all(tifffile.imread(p).dtype==np.uint16 for p in outputs))
                    self.assertEqual(outputs,process_sheet(source,kind='prints'))
                    self.assertEqual(sha,database.digest(source))
                    self.assertFalse(list(root.rglob('*.json')))

    def test_ambiguous_touching_boundaries_refuse(self):
        image=np.zeros((800,1000,3),np.uint8)
        image[80:320,80:420]=180;image[280:600,350:750]=180
        with self.assertRaises(ProcessingError):plan_cards(image,kind='prints')

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'sheet.tif'
            image=np.zeros((800,1000,3),np.uint8);image[80:320,80:420]=180
            tifffile.imwrite(source,image,photometric='rgb')
            with database.use_state(root/'state'),contextlib.redirect_stdout(io.StringIO()):
                process_sheet(source,kind='prints',dry_run=True)
            self.assertEqual(list(root.iterdir()),[source])

class RotationTests(unittest.TestCase):
    def test_pixels_depth_reuse_and_changed_output_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'photo.tif'
            image=np.arange(80*120*3,dtype=np.uint16).reshape(80,120,3)
            tifffile.imwrite(source,image,photometric='rgb')
            with database.use_state(root/'state'):
                sha=database.digest(source)
                result={'job_id':'rotate-test','images':[{'path':str(source),'sha256':sha,'rotation':{'quarter_turns_clockwise':1,'status':'assessed'}}]}
                with database.transaction() as db:database.save_job(db,'rotate-test','similarity',{'status':'running'})
                publish_rotations(result);output=Path(result['images'][0]['rotation']['output'])
                np.testing.assert_array_equal(tifffile.imread(output),np.rot90(image,k=-1))
                publish_rotations(result);self.assertEqual(sha,database.digest(source))
                output.write_bytes(b'changed')
                with self.assertRaisesRegex(Exception,'changed'):publish_rotations(result)

class MenuTests(unittest.TestCase):
    def test_process_defaults_and_scan_without_edits_still_splits(self):
        args=build_parser().parse_args(['process','folder'])
        self.assertTrue(args.tier_review);self.assertTrue(args.auto_rotate)
        with patch('photo_utils.cli.run_scan',return_value=Path('master.tif')),patch('photo_utils.cli.process_and_retouch',return_value=None) as process:
            self.assertEqual(main(['scan','--retouch','none']),0)
            self.assertEqual(process.call_args.kwargs['profile'],'none')
            self.assertTrue(process.call_args.kwargs['tier_review'])

    def test_process_and_review_menu_routes(self):
        with patch('builtins.input',side_effect=['p','/photos','n','n','n','n','q']),patch('sys.stdin.isatty',return_value=True),patch('photo_utils.cli.process_batch',return_value=Path('/photos/review.html')) as process:
            self.assertEqual(main([]),0)
            process.assert_called_once_with([Path('/photos')],recursive=False,profile='none',dry_run=False)
        with patch('builtins.input',side_effect=['v','job123','q']),patch('sys.stdin.isatty',return_value=True),patch('photo_utils.cli.serve_review') as review:
            self.assertEqual(main([]),0);review.assert_called_once_with('job123')
