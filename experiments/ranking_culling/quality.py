"""Experimental measurements only; shared by ranking and future culling."""
import cv2
import numpy as np

VERSION = 'focus-v1'
SETTINGS = {'max_dimension': 1024, 'scales': [1024, 512], 'gaussian_sigma': 1.0,
            'minimum_face_pixels': 24, 'minimum_detection_confidence': .5}


def focus_fields(gray):
    """Derivatives on full image pixels, reusable with region masks."""
    gray = gray.astype(np.float64) / 255
    dx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    dy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    return gray, cv2.Laplacian(gray, cv2.CV_64F), dx * dx + dy * dy


def metrics(gray):
    gray, laplacian, energy = focus_fields(gray)
    return {'laplacian_variance': float(laplacian.var()),
            'tenengrad': float(energy.mean()),
            'luminance_mean': float(gray.mean()), 'luminance_std': float(gray.std())}


def measure(rgb, faces):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    output = {'version': VERSION, 'settings': SETTINGS, 'scales': {}, 'subject': 'unknown'}
    for dimension in SETTINGS['scales']:
        factor = min(1, dimension / max(gray.shape))
        scaled = cv2.resize(gray, (round(gray.shape[1] * factor), round(gray.shape[0] * factor)),
                            interpolation=cv2.INTER_AREA)
        smooth = cv2.GaussianBlur(scaled, (0, 0), SETTINGS['gaussian_sigma'])
        regions = []
        for face in faces:
            x, y, w, h = face['box']
            height, width = scaled.shape
            left, top = max(0, int(x * width)), max(0, int(y * height))
            right, bottom = min(width, round((x + w) * width)), min(height, round((y + h) * height))
            valid = (min(right - left, bottom - top) >= SETTINGS['minimum_face_pixels']
                     and face['detection_confidence'] >= SETTINGS['minimum_detection_confidence'])
            regions.append({'box': face['box'], 'pixels': [right-left, bottom-top],
                            'usable': valid, 'detection_confidence': face['detection_confidence'],
                            'raw': metrics(scaled[top:bottom, left:right]) if valid else None,
                            'smoothed': metrics(smooth[top:bottom, left:right]) if valid else None})
        tiles = [metrics(tile) for row in np.array_split(smooth, 4)
                 for tile in np.array_split(row, 4, axis=1) if min(tile.shape) >= 3]
        output['scales'][str(dimension)] = {'dimensions': [scaled.shape[1], scaled.shape[0]],
            'global': {'raw': metrics(scaled), 'smoothed': metrics(smooth)}, 'faces': regions,
            'tile_tenengrad': [tile['tenengrad'] for tile in tiles]}
    if any(face['usable'] for face in output['scales']['1024']['faces']):
        output['subject'] = 'faces'
    return output
