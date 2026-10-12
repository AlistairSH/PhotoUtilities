import unittest
from pathlib import Path

from subject_audit import render, validate_regions


class SubjectAuditTests(unittest.TestCase):
    def test_invalid_geometry_refused(self):
        for box in ([1.1,.1,.2,.2],[0,0,float('nan'),.1],[-.2,0,.1,.1]):
            with self.assertRaises(ValueError):
                validate_regions({'faces':{'status':'ok','regions':[{'box':box}]}})

    def test_outside_boxes_preserve_raw_and_clip_display(self):
        region={'box':[-.1,.2,.4,.9]}
        validate_regions({'people':{'status':'ok','regions':[region]}})
        self.assertEqual(region['box'],[-.1,.2,.4,.9])
        self.assertAlmostEqual(region['display_box'][2],.3)
        self.assertAlmostEqual(region['display_box'][3],.8)

    def test_coordinate_scaling_and_failure_visibility(self):
        row={'path':'/tmp/a&b.jpg','index':0,'max_dimension':1024,'width':1000,'height':500,
             'thumbnail':'','detectors':{'faces':{'status':'ok','revision':3,
                 'regions':[{'box':[.1,.2,.3,.4],'detection_confidence':.9}]},
                 'people':{'status':'failed','revision':2,'error':'Example failure'}}}
        document=render([row],{},Path('/tmp/output/subjects.html'))
        self.assertIn('x="100.000" y="100.000" width="300.000" height="200.000"',document)
        self.assertIn('FAILED',document)
        self.assertIn('Example failure',document)
        self.assertIn('a&amp;b.jpg',document)
        self.assertIn('input.faces:not(:checked)~.canvas .faces',document)


if __name__=='__main__':unittest.main()
