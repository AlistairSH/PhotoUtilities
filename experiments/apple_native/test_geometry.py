"""Coordinate and residual oracle checks; no photographic thresholds are tested."""
import numpy as np
from geometry_evaluate import diagnostics, texture


def main():
    a=texture(14)
    b=a[40:280,60:380].copy()
    # Lower-left floating->reference: x+60, y+200; top-left crop starts at (60,40).
    matrix=[[1,0,60],[0,1,200],[0,0,1]]
    evidence={'status':'ok','matrix_columns':np.asarray(matrix).T.tolist()}
    known=np.array([[1.,0,-60],[0,1,-40],[0,0,1]])
    d=diagnostics(a,b,evidence,known)
    assert d['known_transform_median_error_pixels']==0
    assert d['overlap_mae']==0
    assert abs(d['overlap_ncc']-1)<1e-12
    assert .24<d['overlap_reference_fraction']<.26
    flat=np.full((32,32,3),128,np.uint8)
    identity={'status':'ok','matrix_columns':np.eye(3).tolist()}
    d=diagnostics(flat,flat,identity,np.eye(3))
    assert d['overlap_mae']==0 and d['overlap_ncc'] is None
    assert diagnostics(a,b,{'status':'unsupported_dimensions'},None)=={}
    assert diagnostics(a,b,{'status':'ok','matrix_columns':np.zeros((3,3)).tolist()},None)=={'singular':True}
    for invalid in (np.ones((2,2)).tolist(),np.full((3,3),float('nan')).tolist()):
        try:
            diagnostics(a,b,{'status':'ok','matrix_columns':invalid},None)
        except ValueError:
            pass
        else:
            raise AssertionError('Malformed matrix accepted')
    print('Passed geometry coordinate, overlap, flat-image, singular and malformed-matrix checks')


if __name__=='__main__':
    main()
