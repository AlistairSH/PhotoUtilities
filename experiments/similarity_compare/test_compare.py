import unittest

import cv2
import numpy as np

from compare import hashes, sift_pair


def extract(gray):
    keys, descriptors = cv2.SIFT_create(nfeatures=500).detectAndCompute(gray, None)
    return {'points': np.float32([k.pt for k in keys]), 'descriptors': descriptors, 'shape': gray.shape}


def fixture(seed):
    rng = np.random.default_rng(seed)
    gray = np.full((400, 500), 60, np.uint8)
    for _ in range(130):
        xy = tuple(map(int, rng.integers([0, 0], [500, 400])))
        cv2.circle(gray, xy, int(rng.integers(3, 18)), int(rng.integers(80, 250)), -1)
    return gray


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cv2.setNumThreads(2)

    def test_identical_and_warped_content(self):
        image = fixture(4)
        a = extract(image)
        matcher = cv2.BFMatcher(cv2.NORM_L2)
        result = sift_pair(a, a, matcher)
        self.assertTrue(result['sift_candidate'])
        self.assertGreater(result['inliers'], 100)
        for one, two in zip(hashes(image), hashes(image.copy())):
            self.assertEqual(np.count_nonzero(one != two), 0)
        transform = np.float32([[0.9, 0.04, 20], [-0.03, 0.9, 25], [0.00002, -0.00003, 1]])
        shifted = cv2.warpPerspective(image, transform, (500, 400))
        result = sift_pair(a, extract(shifted), matcher)
        self.assertTrue(result['sift_candidate'])
        self.assertGreater(result['inliers'], 30)

    def test_unrelated_textures(self):
        result = sift_pair(extract(fixture(2)), extract(fixture(19)), cv2.BFMatcher(cv2.NORM_L2))
        self.assertFalse(result['sift_candidate'])

    def test_uniform_images_are_not_sift_matches(self):
        flat_a = np.full((100, 150), 40, np.uint8)
        flat_b = np.full((100, 150), 200, np.uint8)
        result = sift_pair(extract(flat_a), extract(flat_b), cv2.BFMatcher(cv2.NORM_L2))
        self.assertEqual(result['status'], 'insufficient-features')
        # Hash collisions on featureless but different images are a known limitation.
        for one, two in zip(hashes(flat_a), hashes(flat_b)):
            self.assertEqual(np.count_nonzero(one != two), 0)

    def test_hash_bit_count_and_direction(self):
        increasing = np.tile(np.arange(90, dtype=np.uint8), (80, 1))
        decreasing = increasing[:, ::-1].copy()
        self.assertEqual(hashes(increasing)[1].shape, (64,))
        self.assertEqual(np.count_nonzero(hashes(increasing)[1] != hashes(decreasing)[1]), 64)


if __name__ == '__main__':
    unittest.main()
