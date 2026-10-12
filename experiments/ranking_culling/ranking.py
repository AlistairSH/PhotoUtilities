"""Group-relative hypotheses; no absolute blur verdict or quality probability."""
import numpy as np


def value(analysis, dimension, treatment, metric, use_faces, weight=.6):
    row = analysis['scales'][str(dimension)]
    if not use_faces:
        return row['global'][treatment][metric]
    faces = [face[treatment][metric] for face in row['faces'] if face['usable']]
    return float(weight * np.mean(faces) + (1 - weight) * min(faces))


def rank_group(members, analyses, near_tie=.10):
    # Use the same measurement scope for every member; partial detections cannot
    # silently give one image a face score and another an unrelated global score.
    counts = [[sum(f['usable'] for f in analyses[i]['scales'][str(scale)]['faces'])
               for i in members] for scale in (1024, 512)]
    use_faces = all(min(c) > 0 and len(set(c)) == 1 for c in counts)
    variants = {}
    scores = []
    for dimension in (1024, 512):
        for treatment in ('raw', 'smoothed'):
            for metric in ('laplacian_variance', 'tenengrad'):
                key = f'{dimension}/{treatment}/{metric}'
                values = [value(analyses[i], dimension, treatment, metric, use_faces) for i in members]
                maximum = max(values)
                normalized = [v / maximum if maximum > 0 else 0 for v in values]
                variants[key] = {'values': values, 'order': sorted(members, key=lambda i: -values[members.index(i)])}
                if treatment == 'smoothed':
                    scores.append(normalized)
    combined = np.mean(scores, axis=0)
    order = sorted(members, key=lambda i: -combined[members.index(i)])
    gap = float(combined[members.index(order[0])] - combined[members.index(order[1])])
    winners = {v['order'][0] for v in variants.values()}
    reasons = []
    if not use_faces:
        reasons.append('Global fallback: comparable usable face detections are unavailable; subject focus is uncertain.')
    if len(winners) > 1:
        reasons.append('Raw/smoothed metrics or analysis scales select different winners; grain/texture sensitivity requires review.')
    if gap <= near_tie:
        reasons.append('Near tie under the provisional 10% group-relative score-gap rule.')
    if use_faces and len(set(counts[0] + counts[1])) > 1:
        reasons.append('Usable face count changes with scale; inspect small faces.')
    return {'members': order, 'suggested': order[0], 'uncertain': bool(reasons), 'near_tie': gap <= near_tie,
            'score_gap': gap, 'basis': 'faces' if use_faces else 'global',
            'explanation': reasons or ['Consistent face-focus winner across both metrics, treatments and scales.'],
            'scores': {str(i): float(combined[members.index(i)]) for i in members},
            'variants': variants,
            'face_weight_alternatives': {str(weight): sorted(members, key=lambda i: -value(
                analyses[i], 1024, 'smoothed', 'tenengrad', use_faces, weight)) for weight in (0., .6, 1.)}}
