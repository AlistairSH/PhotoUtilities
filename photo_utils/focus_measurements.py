"""Shared Gaussian1 regional focus measurements for review and comparison."""
from __future__ import annotations
from typing import Any
import cv2
import numpy as np
from numpy.typing import NDArray
VERSION="gaussian1-region-v1"

def focus_fields(gray: NDArray[Any]) -> tuple[NDArray[Any], NDArray[Any], NDArray[Any]]:
    image=gray.astype(np.float64)/255
    dx=cv2.Sobel(image,cv2.CV_64F,1,0,ksize=3);dy=cv2.Sobel(image,cv2.CV_64F,0,1,ksize=3)
    return image,cv2.Laplacian(image,cv2.CV_64F),dx*dx+dy*dy

def box_mask(box: list[float], shape: tuple[int, ...]) -> tuple[NDArray[Any], tuple[int, int]]:
    height,width=shape
    x,y,w,h=box
    left,top=max(0,int(x*width)),max(0,int(y*height))
    right,bottom=min(width,round((x+w)*width)),min(height,round((y+h)*height))
    mask=np.zeros(shape,np.uint8)
    mask[top:bottom,left:right]=1
    return mask,(right-left,bottom-top)


def masked_metrics(fields: tuple[NDArray[Any], NDArray[Any], NDArray[Any]], mask: NDArray[Any]) -> Any:
    # Derivatives are computed before masking; guard pixels prevent sampling
    # crop/mask boundaries as artificial edges.
    selected=cv2.erode(mask,np.ones((3,3),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=(0,)).astype(bool)
    count=int(selected.sum())
    if count<100:return None
    gray,laplacian,energy=fields
    return {'pixels':count,'laplacian_variance':float(laplacian[selected].var()),
            'tenengrad':float(energy[selected].mean()), 'gradient_energy_p90':float(np.quantile(energy[selected],.9)),
            'luminance_mean':float(gray[selected].mean()),'luminance_std':float(gray[selected].std())}


def analyze_regions(rgb: NDArray[Any], detectors: dict[str, Any], treatment: str = 'gaussian1') -> dict[str, Any]:
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    filters={'raw':lambda:gray,'gaussian1':lambda:cv2.GaussianBlur(gray,(0,0),1.),
             'gaussian2':lambda:cv2.GaussianBlur(gray,(0,0),2.),
             'bilateral':lambda:cv2.bilateralFilter(gray,5,15,2)}
    if treatment not in filters:raise ValueError('Unknown focus treatment')
    # The CLI needs only the selected Gaussian1 measurements; raw and other
    # experimental diagnostics are not recomputed during a routine batch.
    fields={'smoothed':focus_fields(filters[treatment]())}
    excluded=np.zeros(gray.shape,np.uint8)
    for kind in ('faces','people','animals'):
        for region in detectors[kind].get('regions',[]):
            mask,_=box_mask(region.get('display_box',region['box']),gray.shape)
            excluded |= mask
    global_mask=np.ones(gray.shape,np.uint8)
    global_values={t:masked_metrics(f,global_mask) for t,f in fields.items()}
    tile_values: list[float]=[]
    for ys in np.array_split(np.arange(gray.shape[0]),4):
        for xs in np.array_split(np.arange(gray.shape[1]),4):
            mask=np.zeros(gray.shape,np.uint8)
            mask[ys[0]:ys[-1]+1,xs[0]:xs[-1]+1]=1
            value=masked_metrics(fields['smoothed'],mask)
            if value:tile_values.append(value['tenengrad'])
    regions: list[dict[str, Any]]=[]
    for kind in ('faces','people','animals','objectness','attention'):
        detector=detectors[kind]
        for index,region in enumerate(detector.get('regions',[]),1):
            mask,size=box_mask(region.get('display_box',region['box']),gray.shape)
            outside=1-cv2.dilate(excluded|mask,np.ones((7,7),np.uint8))
            result={'id':f'{kind} {index}','box':region['box'],'pixels':list(size),
                    'usable':min(size)>=24,'raw':None,'smoothed':None}
            if result['usable']:
                for treatment,f in fields.items():
                    inside=masked_metrics(f,mask);background=masked_metrics(f,outside)
                    ratios={}
                    if inside and background:
                        for metric in ('laplacian_variance','tenengrad','gradient_energy_p90'):
                            ratios[metric]=inside[metric]/background[metric] if background[metric]>0 else None
                    result[treatment]={'region':inside,'outside':background,'region_to_outside':ratios}
            regions.append(result)
            region['focus']=result
    return {'version':VERSION,'treatment':treatment,'sigma':{'gaussian1':1.,'gaussian2':2.}.get(treatment),
            'bilateral_parameters':{'d':5,'sigmaColor':15,'sigmaSpace':2} if treatment=='bilateral' else None,'minimum_region_side':24,
            'outside_definition':'Outside this region and every detected face/person/animal box, with a 3px guard; may contain missed subjects.',
            'global':global_values,'tile_tenengrad':tile_values,'regions':regions}

