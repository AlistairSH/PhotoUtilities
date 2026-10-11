import unittest
from group_report import accepted, bridges, components


class GroupTests(unittest.TestCase):
    def test_chained_group_and_isolated_photo(self):
        groups, neighbors=components(5,[(0,1),(1,2),(2,3)])
        self.assertEqual(groups,[[0,1,2,3],[4]])
        self.assertNotIn(3,neighbors[0])
        self.assertEqual(bridges(groups[0],[(0,1),(1,2),(2,3)]),{(0,1),(1,2),(2,3)})

    def test_clique_has_no_bridge(self):
        self.assertEqual(bridges([0,1,2],[(0,1),(1,2),(0,2)]),set())

    def test_union_and_exact_boundary(self):
        self.assertTrue(accepted({'vision_distance':.44,'sift_candidate':False}))
        self.assertTrue(accepted({'vision_distance':.8,'sift_candidate':True}))
        self.assertFalse(accepted({'vision_distance':.45,'sift_candidate':False}))


if __name__=='__main__':unittest.main()
