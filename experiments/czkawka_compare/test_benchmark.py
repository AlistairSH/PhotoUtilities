import unittest
from pathlib import Path
from benchmark import command, memberships, CONFIGS


class BenchmarkTests(unittest.TestCase):
    def test_group_membership_is_not_a_direct_distance(self):
        images=[{'path':str(Path('/tmp')/f'{i}.jpg')}for i in range(3)]
        groups=[[{'path':row['path'],'difference':i*3}for i,row in enumerate(images)]]
        self.assertEqual(memberships(groups,images),{(0,1),(0,2),(1,2)})
        self.assertRaises(ValueError,memberships,[[{'path':'/tmp/unexpected.jpg'}]],images)

    def test_read_only_command(self):
        args=command('/tmp/binary',Path('/tmp/images'),Path('/tmp/results.json'),CONFIGS[0])
        self.assertEqual(args[args.index('-D')+1],'NONE')
        self.assertIn('-Q',args)
        self.assertIn('-H',args)
        self.assertNotIn('-y',args)
        self.assertNotIn('-J',args)
        self.assertNotIn('-Z',args)
        self.assertEqual(args[args.index('-T')+1],'2')


if __name__=='__main__':unittest.main()
