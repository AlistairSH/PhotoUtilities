import unittest

from photo_utils.tiers import assign_tier, remove_composition_culls


def row(ident, detail=1, face=None):
    return dict(id=ident, reasons=[], possible_cull=False, laplacian=detail,
                tenengrad=detail, face_quality=face, detail_kind='faces',
                laplacian_percentile=50, tenengrad_percentile=50,
                aesthetic_percentile=50)


class TierTests(unittest.TestCase):
    def test_close_group_has_no_forced_top_pick(self):
        rows = [row('a', face=.60), row('b', face=.59)]
        for r in rows:
            assign_tier(r, rows)
        self.assertEqual([r['tier'] for r in rows], ['Review', 'Review'])

    def test_clear_face_advantage_and_missing_score_is_not_zero(self):
        rows = [row('a', face=.65), row('b', face=.50)]
        assign_tier(rows[0], rows)
        self.assertEqual(rows[0]['tier'], 'Top Pick')
        rows[1]['face_quality'] = None
        assign_tier(rows[0], rows)
        self.assertEqual(rows[0]['tier'], 'Review')

    def test_detail_requires_both_metrics_and_all_comparable_peers(self):
        rows = [row('a', 2), row('b', 1), row('c', 1.8)]
        assign_tier(rows[0], rows)
        self.assertEqual(rows[0]['tier'], 'Review')
        rows[2]['laplacian'] = rows[2]['tenengrad'] = 1
        assign_tier(rows[0], rows)
        self.assertEqual(rows[0]['tier'], 'Top Pick')
        rows[0]['tenengrad'] = 1
        assign_tier(rows[0], rows)
        self.assertEqual(rows[0]['tier'], 'Review')

    def test_technical_flag_and_low_detail_block_promotion(self):
        rows = [row('a', 2, .8), row('b', 1, .4)]
        rows[0]['possible_cull'] = True
        assign_tier(rows[0], rows)
        self.assertEqual(rows[0]['tier'], 'Possible Cull')
        rows[0]['possible_cull'] = False
        rows[0]['tenengrad_percentile'] = 5
        assign_tier(rows[0], rows)
        self.assertEqual(rows[0]['tier'], 'Review')

    def test_composition_is_advisory_but_other_faults_stay(self):
        r = row('a')
        r['reasons'] = ['Farther from center/thirds anchors — provisional composition suggestion']
        remove_composition_culls(r)
        self.assertFalse(r['possible_cull'])
        self.assertEqual(len(r['composition_advisories']), 1)
        r['reasons'] = ['Utility image', 'Farther from center/thirds anchors']
        remove_composition_culls(r)
        self.assertTrue(r['possible_cull'])
        self.assertEqual(r['reasons'], ['Utility image'])

    def test_solo_uses_full_sample_not_solo_only_percentiles(self):
        solo = row('solo', 1)
        solo['aesthetic_percentile'] = 95
        reference = [solo] + [row(str(i), 2) for i in range(20)]
        assign_tier(solo, reference, solo=True)
        self.assertEqual(solo['tier'], 'Review')
        solo['laplacian'] = solo['tenengrad'] = 3
        assign_tier(solo, reference, solo=True)
        self.assertEqual(solo['tier'], 'Top Pick')


if __name__ == '__main__':
    unittest.main()
