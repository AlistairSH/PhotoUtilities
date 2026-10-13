import importlib.util
import unittest
from pathlib import Path

def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
experiment=load('experiment');evaluation=load('evaluate')

def fixture():
    return {'experiment_id':'test','images':[{'path':f'/tmp/{i}.jpg','aesthetics':{'status':'ok','overallScore':s},'focus_comparison':c} for i,s,c in
        [(0,.9,{'role':'softer','softer_than':[1]}),(1,.8,{'role':'sharper','sharper_than':[0]}),(2,.7,{})]],
        'groups':[{'members':[0,1,2],'level':'likely'}],
        'pairs':[{'a':a,'b':b,'level':'likely'} for a,b in [(0,1),(0,2),(1,2)]]}

class RankingTests(unittest.TestCase):
    def test_direct_exclusion(self):
        g=experiment.rank_groups(fixture())[0]
        self.assertEqual(g['winner_a'],0);self.assertEqual(g['winner_b'],1);self.assertEqual(g['ranking_c'],g['ranking_a'])
    def test_chaining_never_propagates_focus(self):
        r=fixture();r['pairs'][1]['level']='unmatched';g=experiment.rank_groups(r)[0]
        self.assertTrue(g['chained']);self.assertEqual(g['excluded'],{});self.assertIsNone(g['winner_a'])
    def test_weak_group_withheld(self):
        r=fixture();r['pairs'][0]['level']='potential';g=experiment.rank_groups(r)[0]
        self.assertTrue(g['weak']);self.assertEqual(g['excluded'],{});self.assertIsNone(g['winner_b'])
    def test_failure_cannot_win(self):
        r=fixture();r['images'][0]['aesthetics']={'status':'failed','error':'bad'};g=experiment.rank_groups(r)[0]
        self.assertNotIn(0,g['ranking_a']);self.assertIsNone(g['winner_a']);self.assertTrue(g['incomplete'])
    def test_exact_tie(self):
        r=fixture();r['images'][1]['aesthetics']['overallScore']=.9
        self.assertTrue(experiment.rank_groups(r)[0]['exact_tie'])
    def test_no_human_statistics_without_labels(self):
        r=fixture();r['comparisons']=experiment.rank_groups(r)
        s=evaluation.evaluate(r,{'experiment_id':'test','answers':{}})
        self.assertEqual(s['human_judged_groups'],0);self.assertIsNone(s['approaches']['a']['candidate_top1_rate'])
    def test_blind_choice_and_focus_worsening(self):
        r=fixture();r['comparisons']=experiment.rank_groups(r)
        s=evaluation.evaluate(r,{'experiment_id':'test','answers':{'group-001':{'choice':1,'blind_choice':0,'changed_after_reveal':True}}})
        self.assertEqual(s['focus_worsened'],1);self.assertEqual(s['approaches']['a']['candidate_top1_rate'],1)
    def test_reject_wrong_experiment_and_choice(self):
        r=fixture();r['comparisons']=experiment.rank_groups(r)
        with self.assertRaises(ValueError):evaluation.evaluate(r,{'experiment_id':'other'})
        with self.assertRaises(ValueError):evaluation.evaluate(r,{'experiment_id':'test','answers':{'group-001':{'choice':999}}})

if __name__=='__main__':unittest.main()

class ProtocolTests(unittest.TestCase):
    def helper(self, folder, code):
        p=folder/'helper';p.write_text('#!/usr/bin/env python3\n'+code);p.chmod(0o755);return p
    def test_truncated_process_never_publishes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);h=self.helper(d,'import sys\nsys.stdin.read()\nprint("{}")\n')
            with self.assertRaises((ValueError,KeyError)):
                experiment.score_rows([Path('/tmp/a.jpg')],h,d/'errors',d/'checkpoint',2)
    def test_timeout_kills_process(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);h=self.helper(d,'import sys,time\nsys.stdin.read()\ntime.sleep(10)\n')
            with self.assertRaisesRegex(ValueError,'timed out'):
                experiment.score_rows([Path('/tmp/a.jpg')],h,d/'errors',d/'checkpoint',.1)
    def test_interrupted_run_marked_without_report(self):
        import argparse,tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);source=d/'a.jpg';source.write_bytes(b'test');helper=d/'helper';helper.write_text('test')
            args=argparse.Namespace(folder=d,output_dir=d/'output',helper=helper,database=d/'absent')
            with patch.object(experiment,'analyze',side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):experiment.run(args)
            import json
            self.assertEqual(json.loads((d/'output/run.json').read_text())['status'],'interrupted')
            self.assertFalse((d/'output/review.html').exists())
    def test_report_escapes_and_starts_blind(self):
        r=fixture();r['images'][0]['path']='/tmp/<script>.jpg'
        for image in r['images']:
            image['aesthetics'].update({'preview':'','isUtility':False});image['thumbnail']=''
        for pair in r['pairs']:pair.update({'vision_distance':.2,'sift_candidate':False})
        r['comparisons']=experiment.rank_groups(r)
        document=experiment.render(r)
        self.assertIn('&lt;script&gt;.jpg',document)
        self.assertIn('class="model" hidden',document)
        self.assertIn('blind_choice',document)
        self.assertNotIn('fetch(',document)
