import unittest
from cascade_report import apply_scope, percentile


def row(ident, detail=1, kind='faces'):
    return dict(id=ident, utility=False, detail_kind=kind, laplacian=detail,
                tenengrad=detail, clipping=0, closed_fraction=None,
                open_fraction=None, smile_fraction=None, face_quality=None,
                layout=None, aesthetic=.5, detail_percentile=50)


class CascadeTests(unittest.TestCase):
    def test_no_forced_quota_or_missing_face_fault(self):
        rows = [row(str(i)) for i in range(6)]
        ordered, tie = apply_scope(rows, rows)
        self.assertTrue(tie)
        self.assertFalse(any(r['possible_cull'] for r in ordered))

    def test_detail_requires_both_metrics_and_same_region_kind(self):
        weak, strong = row('weak'), row('strong', 2)
        strong['tenengrad'] = 1
        apply_scope([weak, strong], [weak, strong])
        self.assertFalse(weak['possible_cull'])
        strong['tenengrad'] = 2
        strong['detail_kind'] = 'global'
        apply_scope([weak, strong], [weak, strong])
        self.assertFalse(weak['possible_cull'])
        strong['detail_kind'] = 'faces'
        apply_scope([weak, strong], [weak, strong])
        self.assertTrue(weak['possible_cull'])

    def test_expression_requires_open_alternative(self):
        closed, unknown = row('closed'), row('unknown')
        closed['closed_fraction'] = 1
        apply_scope([closed, unknown], [closed, unknown])
        self.assertFalse(closed['possible_cull'])
        unknown['open_fraction'] = 1
        apply_scope([closed, unknown], [closed, unknown])
        self.assertTrue(closed['possible_cull'])

    def test_percentiles_include_full_reference_and_ties(self):
        self.assertEqual(percentile(1, [1, 1, 2, 3]), 25)
        self.assertEqual(percentile(3, [1, 1, 2, 3]), 87.5)


if __name__ == '__main__':
    unittest.main()
