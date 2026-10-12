import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import threading
import urllib.request
import urllib.error
import numpy as np
from photo_utils import database
from photo_utils.focus import decisions,relative_focus,measure
from photo_utils.focus_policy import screen
from photo_utils.similarity_native import SimilarityError
from photo_utils.review_archive import archive_selected,restore_archive
from photo_utils.review_server import make_server
from photo_utils.cli import main,build_parser


def row(path,scale, *,global_flag=False,semantic=True,ratio=2.,supported=True,detail=1.):
    kind='faces 1' if semantic else 'objectness 1'
    r={'id':kind,'box':[.2,.2,.4,.4],'usable':True,'smoothed':{'region':{'laplacian_variance':detail,'tenengrad':detail},'outside':{'laplacian_variance':1.,'tenengrad':1.},'region_to_outside':{'laplacian_variance':ratio,'tenengrad':ratio}}}
    m={'sufficient':supported,'contrast_soft_fraction':.4 if semantic else .8}
    return {'path':path,'max_dimension':scale,'focus':{'global':{'smoothed':{'laplacian_variance':detail,'tenengrad':detail}},'tile_tenengrad':[detail],'regions':[r]},'edge_flags':{'contrast_proxy':global_flag},'edge_regions':[{'id':kind,'box':r['box'],'metrics':m}]}


class FocusTests(unittest.TestCase):
    def test_baseline_always_wins_over_scale_confirmation(self):
        rows=[row('a',1024,global_flag=True,ratio=.5),row('a',2048,ratio=.5)]
        d=decisions(rows)[0]
        self.assertTrue(d['baseline_review']);self.assertTrue(d['review_suggestion'])

    def test_global_both_scales_or_sparse_regions_cannot_be_cleared(self):
        rows=[row('a',1024,global_flag=True),row('a',2048,global_flag=True)]
        self.assertTrue(decisions(rows)[0]['review_suggestion'])
        rows[1]['edge_flags']['contrast_proxy']=False;rows[0]['edge_regions'][0]['metrics']['sufficient']=False
        self.assertTrue(decisions(rows)[0]['review_suggestion'])

    def test_single_scale_global_confirmed_by_semantic_regions(self):
        d=decisions([row('a',1024,global_flag=True),row('a',2048)])[0]
        self.assertFalse(d['baseline_review']);self.assertTrue(d['scale_confirmation_cleared']);self.assertFalse(d['review_suggestion'])

    def test_regional_fallback_preserved_without_semantics(self):
        d=decisions([row('a',1024,semantic=False),row('a',2048,semantic=False)])[0]
        self.assertTrue(d['regional_fallback_review']);self.assertTrue(d['review_suggestion'])

    def test_attention_only_fallback_and_ties(self):
        a=row('a',1024,ratio=.5);b=row('a',2048,ratio=.5)
        for r in (a,b):r['focus']['regions'][0]['id']='attention 1'
        self.assertTrue(screen([a,b])[0]['review_suggestion'])
        for r in (a,b):r['focus']['regions'].append({**copy.deepcopy(r['focus']['regions'][0]),'id':'objectness 1','smoothed':None})
        self.assertFalse(screen([a,b])[0]['review_suggestion'])
        rows=[row(str(i),scale,ratio=2) for i in range(20) for scale in (1024,2048)]
        self.assertFalse(any(d['global_low_detail'] for d in screen(rows)))

    def test_failed_detector_not_empty_subjects(self):
        with self.assertRaises(SimilarityError):measure(np.zeros((50,50,3),np.uint8),{},'a',1024)

    def test_relative_highlight_direct_matches_only(self):
        rows=[row('a',s,detail=3.) for s in (1024,2048)]+[row('b',s,detail=1.) for s in (1024,2048)]+[row('c',s,detail=.2) for s in (1024,2048)]
        result={'images':[{'path':p} for p in ['a','b','c']],'groups':[{'members':[0,1,2]}],'pairs':[{'a':0,'b':1,'level':'likely'},{'a':1,'b':2,'level':'unmatched'}]}
        relative_focus(result,rows)
        self.assertEqual(result['images'][0]['focus_comparison']['role'],'sharper')
        self.assertEqual(result['images'][1]['focus_comparison']['role'],'softer')
        self.assertIsNone(result['images'][2]['focus_comparison']['role'])


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();self.state=self.root/'state';self.context=database.use_state(self.state);self.context.__enter__();self.addCleanup(self.context.__exit__,None,None,None)
        self.photos=self.root/'photos';self.photos.mkdir();self.source=self.photos/'a.jpg';self.source.write_bytes(b'original bytes');self.sidecar=self.photos/'a.xmp';self.sidecar.write_bytes(b'original notes');self.report=self.photos/'review.html';self.report.write_text('<html>Review</html>')
        self.job='review-fixture'
        with database.transaction() as db:
            payload={'status':'completed','focus_version':'test','created_at':database.now(),'report':str(self.report),'report_sha256':database.digest(self.report),'images':[]}
            database.save_job(db,self.job,'similarity',payload,self.report)
            aid=database.asset(db,self.source,job=self.job,sha=database.digest(self.source))
            payload['images']=[{'path':str(self.source),'sha256':database.digest(self.source),'asset_id':aid}]
            database.save_job(db,self.job,'similarity',payload,self.report)
        self.archive=self.root/'Blurry'

    def test_verified_archive_companions_restore_and_preserve_identity(self):
        before=database.query_assets()[0]['asset_id'];r=archive_selected(self.job,[0],archive_root=self.archive)
        self.assertEqual(r['files'],2);self.assertFalse(self.source.exists());self.assertFalse(self.sidecar.exists())
        with zipfile.ZipFile(r['archive']) as z:
            self.assertEqual(z.read('photos/0001-a.jpg'),b'original bytes')
        original=next(a for a in database.query_assets() if a['asset_id']==before)
        self.assertEqual(original['status'],'archived');self.assertTrue(Path(original['path']).exists())
        restore_archive(r['archive_job']);self.assertEqual(self.source.read_bytes(),b'original bytes');self.assertEqual(self.sidecar.read_bytes(),b'original notes');self.assertTrue(Path(r['archive']).exists())
        self.assertEqual(next(a for a in database.query_assets() if a['asset_id']==before)['path'],str(self.source))
        self.assertFalse(database.check_database(True)['changed_files'])

    def test_changed_source_and_symlink_companion_prevent_moves(self):
        self.source.write_bytes(b'changed')
        with self.assertRaises(SimilarityError):archive_selected(self.job,[0],archive_root=self.archive)
        self.assertTrue(self.sidecar.exists())
        self.source.write_bytes(b'original bytes');self.sidecar.unlink();self.sidecar.symlink_to(self.source)
        with self.assertRaises(SimilarityError):archive_selected(self.job,[0],archive_root=self.archive)
        self.assertTrue(self.source.exists())

    def test_failed_second_move_rolls_back_first(self):
        import photo_utils.review_archive as ar
        original=ar.move_no_replace;calls=0
        def failure(source,dest):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('simulated disk failure')
            return original(source,dest)
        with patch.object(ar,'move_no_replace',side_effect=failure):
            with self.assertRaises(OSError):archive_selected(self.job,[0],archive_root=self.archive)
        self.assertTrue(self.source.exists());self.assertTrue(self.sidecar.exists());self.assertEqual(database.query_jobs(job_type='review-archive')[0]['processing_status'],'failed')

    def test_zip_verification_failure_retains_every_source(self):
        import io
        import photo_utils.review_archive as ar
        real=ar.zipfile.ZipFile
        class CorruptRead(real):
            def open(self,name,mode='r',*args,**kwargs):
                if mode=='r' and str(name).startswith('photos/'):
                    return io.BytesIO(b'corrupt bytes')
                return super().open(name,mode,*args,**kwargs)
        with patch.object(ar.zipfile,'ZipFile',CorruptRead):
            with self.assertRaises(SimilarityError):archive_selected(self.job,[0],archive_root=self.archive)
        self.assertEqual(self.source.read_bytes(),b'original bytes')
        self.assertEqual(self.sidecar.read_bytes(),b'original notes')

    def test_no_clobber_move_never_replaces_existing_file(self):
        from photo_utils.review_archive import move_no_replace
        dest=self.root/'occupied.jpg';dest.write_bytes(b'user data')
        with self.assertRaises(FileExistsError):move_no_replace(self.source,dest)
        self.assertEqual(dest.read_bytes(),b'user data')
        self.assertEqual(self.source.read_bytes(),b'original bytes')

    def test_restore_refuses_collision(self):
        r=archive_selected(self.job,[0],archive_root=self.archive);self.source.write_bytes(b'new user photo')
        with self.assertRaises(SimilarityError):restore_archive(r['archive_job'])
        self.assertEqual(self.source.read_bytes(),b'new user photo')

    def test_master_and_unknown_index_are_protected(self):
        with self.assertRaises(SimilarityError):archive_selected(self.job,[-1],archive_root=self.archive)
        with database.transaction() as db:db.execute("UPDATE assets SET asset_type='master'")
        with self.assertRaises(SimilarityError):archive_selected(self.job,[0],archive_root=self.archive)
        self.assertTrue(self.source.exists())

    def test_loopback_archive_requires_session_and_origin(self):
        server,url=make_server(self.job,archive_root=self.archive);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=url.split('/#')[0];token=url.split('#')[1]
        self.assertIn(b'Review',urllib.request.urlopen(base).read())
        req=urllib.request.Request(base+'/archive',data=b'{"indices":[0]}',headers={'Content-Type':'application/json'},method='POST')
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
        self.assertEqual(error.exception.code,403);self.assertTrue(self.source.exists())
        req.add_header('Authorization','Bearer '+token);req.add_header('Origin','http://untrusted.example')
        with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
        self.assertTrue(self.source.exists())
        req.remove_header('Origin');result=json.loads(urllib.request.urlopen(req).read());self.assertEqual(result['files'],2)


class CliFocusTests(unittest.TestCase):
    def test_explicit_no_focus_keeps_old_sheet_flow(self):
        with patch('photo_utils.cli.process_and_retouch') as p:
            self.assertEqual(main(['process-sheet','a.tif','--no-focus-review','--dry-run']),0)
            self.assertFalse(p.call_args.kwargs['focus_review'])
        self.assertTrue(build_parser().parse_args(['scan']).focus_review)
        self.assertEqual(build_parser().parse_args(['process','folder']).retouch,'none')

if __name__=='__main__':unittest.main()
