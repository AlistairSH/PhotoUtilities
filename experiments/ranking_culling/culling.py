"""Conservative review sampling from shared focus measurements, not deletion logic."""
import math

import numpy as np

VERSION = 'culling-review-v1'
SIGNALS = [(scale, kind) for scale in ('1024', '512')
           for kind in ('laplacian_variance', 'tenengrad', 'peak_tile_tenengrad')]


def signals(analysis):
    values = {}
    for scale, kind in SIGNALS:
        row = analysis['scales'][scale]
        value = (max(row['tile_tenengrad']) if kind == 'peak_tile_tenengrad'
                 else row['global']['smoothed'][kind])
        if not math.isfinite(value) or value < 0:
            raise ValueError('Focus measurements must be finite and nonnegative')
        values[f'{scale}/{kind}'] = value
    return values


def screen(analyses, tail_fraction=.10):
    if not 0 < tail_fraction <= .25:
        raise ValueError('Review tail fraction must be in (0, .25]')
    if not analyses:
        raise ValueError('Empty analysis batch')
    measured = [signals(a) for a in analyses]
    population = len(measured)
    reference = {key: sorted(row[key] for row in measured) for key in measured[0]}
    rules = {'version': VERSION, 'tail_fraction': tail_fraction, 'reference_images': population,
             'minimum_reference_images': 20, 'treatment': 'smoothed',
             'selection': 'All six lower-tail fractions <= tail_fraction; ties counted conservatively',
             'severe_blur_threshold': None, 'threshold_status': 'Uncalibrated review sampling only',
             'reference_quantiles': {key: float(np.quantile(values, tail_fraction))
                                     for key, values in reference.items()}}
    decisions = []
    for analysis, row in zip(analyses, measured):
        # count <= includes ties: a constant or mostly featureless batch cannot
        # automatically produce a fixed quota of "bad" photos.
        fractions = {key: sum(v <= row[key] for v in values) / population
                     for key, values in reference.items()}
        global_low = all(fractions[f'{scale}/{kind}'] <= tail_fraction
                         for scale in ('1024', '512') for kind in ('laplacian_variance', 'tenengrad'))
        peak_low = all(fractions[f'{scale}/peak_tile_tenengrad'] <= tail_fraction for scale in ('1024', '512'))
        shortlist = population >= 20 and global_low and peak_low
        if shortlist:
            reason = ('Both smoothed global focus metrics and the strongest measured tile are '
                      'in this batch’s lower detail tail at both scales. Inspect for blur or low texture.')
        elif global_low and not peak_low:
            reason = 'Low global detail but a stronger local region: possible sharp subject; not shortlisted.'
        elif population < 20:
            reason = 'Batch too small for the provisional tail sampling rule.'
        else:
            reason = 'Not selected by this review rule; this does not establish acceptable focus.'
        decisions.append({'category': 'manual_review' if shortlist else 'unassessed',
                          'review_shortlist': shortlist, 'severe_blur_candidate': False,
                          'reason': reason, 'subject': analysis['subject'], 'measurements': row,
                          'lower_tail_fractions': fractions, 'global_low': global_low,
                          'stronger_region_retained': global_low and not peak_low,
                          'limitations': ['Low texture, exposure, borders and grain can mimic or conceal blur.',
                                          'A 4×4 tile can miss a small sharp subject.',
                                          'Face detection is not required; undetected subjects remain unknown.']})
    return decisions, rules
