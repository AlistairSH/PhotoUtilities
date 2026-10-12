"""Experimental edge-profile probes; contrast proxy is not published CPBD."""
from __future__ import annotations
from typing import Any, Optional
from numpy.typing import NDArray
import cv2
import numpy as np

SETTINGS: dict[str, Any]={'sigma':1.,'stride':3,'maximum_edges':3000,'profile_radius':16,
          'minimum_contrast':10/255,'minimum_edges':50,
          'edge_width_rule':'median 10–90 width >= 4 pixels',
          'contrast_rule':'fraction width > (5px if contrast <= 50/255 else 3px) >= .60',
          'direction_rule':'opposing normal-bin medians ratio >=1.6 and larger width >=4.5px; >=25 edges each'}


def extract(gray: NDArray[Any], *, stride: int = 3, maximum_edges: int = 3000) -> dict[str, Any]:
    image=cv2.GaussianBlur(gray.astype(np.float32)/255,(0,0),1.)
    dx=cv2.Sobel(image,cv2.CV_32F,1,0,ksize=3);dy=cv2.Sobel(image,cv2.CV_32F,0,1,ksize=3)
    magnitude=cv2.magnitude(dx,dy)
    y,x=np.mgrid[18:gray.shape[0]-18:stride,18:gray.shape[1]-18:stride]
    x=x.ravel().astype(np.float32);y=y.ravel().astype(np.float32)
    if not len(x):return {'x':[],'y':[],'width':[],'contrast':[],'angle':[],'censored':[]}
    m=magnitude[y.astype(int),x.astype(int)]
    threshold=max(.002,float(np.quantile(m,.75)))
    choose=m>threshold;x=x[choose];y=y[choose];m=m[choose]
    if not len(x):return {k:[] for k in ('x','y','width','contrast','angle','censored')}
    # Keep remap dimensions bounded before any sampling (OpenCV short-index
    # limits), and sample spatially rather than choosing only the strongest edge.
    if len(x)>maximum_edges:
        take=np.random.default_rng(0).choice(len(x),maximum_edges,replace=False);x=x[take];y=y[take];m=m[take]
    nx=dx[y.astype(int),x.astype(int)]/m;ny=dy[y.astype(int),x.astype(int)]/m
    def sample(array: NDArray[Any], mx: NDArray[Any], my: NDArray[Any]) -> NDArray[Any]:return cv2.remap(array,mx.astype(np.float32),my.astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
    before=sample(magnitude,(x-nx)[:,None],(y-ny)[:,None]).ravel()
    after=sample(magnitude,(x+nx)[:,None],(y+ny)[:,None]).ravel()
    # Shift coarse-grid samples toward the local maximum instead of rejecting
    # every edge that falls between grid columns (sampling aliasing).
    shift=np.where(before>np.maximum(m,after),-1.,np.where(after>m,1.,0.))
    x=x+nx*shift;y=y+ny*shift
    if len(x)>maximum_edges:
        take=np.random.default_rng(0).choice(len(x),maximum_edges,replace=False);x=x[take];y=y[take];nx=nx[take];ny=ny[take]
    offsets=np.arange(-16,17,dtype=np.float32)
    profiles=sample(image,x[:,None]+nx[:,None]*offsets,y[:,None]+ny[:,None]*offsets)
    output: dict[str, Any]={k:[] for k in ('x','y','width','contrast','angle','censored')}
    for index,profile in enumerate(profiles):
        gradient=np.diff(profile);peak=int(np.argmax(gradient[14:18]))+14
        height=gradient[peak]
        if height<=0:continue
        left=peak;right=peak
        while left>0 and gradient[left-1]>.05*height:left-=1
        while right<len(gradient)-1 and gradient[right+1]>.05*height:right+=1
        segment=profile[left:right+2];contrast=float(segment[-1]-segment[0])
        if contrast<SETTINGS['minimum_contrast']:continue
        p10=float(np.interp(segment[0]+.1*contrast,segment,np.arange(left,right+2)))
        p90=float(np.interp(segment[0]+.9*contrast,segment,np.arange(left,right+2)))
        output['x'].append(float(x[index]));output['y'].append(float(y[index]));output['width'].append(p90-p10)
        output['contrast'].append(contrast);output['angle'].append(float(np.arctan2(ny[index],nx[index])%np.pi))
        output['censored'].append(left==0 or right==len(gradient)-1)
    return output


def summarize(edges: dict[str, Any], box: Optional[list[float]] = None, shape: Optional[tuple[int, ...]] = None) -> dict[str, Any]:
    selected=np.ones(len(edges['width']),bool)
    if box is not None:
        assert shape is not None
        height,width=shape;x,y,w,h=box
        ex=np.asarray(edges['x'])/width;ey=np.asarray(edges['y'])/height
        selected=(ex>=x)&(ex<x+w)&(ey>=y)&(ey<y+h)
    widths=np.asarray(edges['width'])[selected];contrasts=np.asarray(edges['contrast'])[selected]
    angles=np.asarray(edges['angle'])[selected];count=len(widths)
    if not count:return {'edges':0,'sufficient':False,'median_width':None,'contrast_soft_fraction':None,'direction_ratio':None}
    bins=np.floor((angles+np.pi/8)/(np.pi/4)).astype(int)%4
    medians=[float(np.median(widths[bins==i])) if sum(bins==i)>=25 else None for i in range(4)]
    directional: list[tuple[float, float]]=[]
    for i,j in [(0,2),(1,3)]:
        mi,mj=medians[i],medians[j]
        if mi is not None and mj is not None:
            high,low=max(mi,mj),min(mi,mj)
            if low>0:directional.append((high/low,high))
    best: tuple[Optional[float], Optional[float]]=max(directional) if directional else (None,None)
    return {'edges':count,'sufficient':count>=50,'median_width':float(np.median(widths)),
            'width_q25':float(np.quantile(widths,.25)), 'width_q75':float(np.quantile(widths,.75)),
            'contrast_soft_fraction':float(np.mean(widths>np.where(contrasts<=50/255,5.,3.))),
            'median_acutance':float(np.median(contrasts/np.maximum(widths,1e-6))),
            'normal_bin_medians':medians,'direction_ratio':best[0],'direction_wide_width':best[1],
            'censored_fraction':float(np.mean(np.asarray(edges['censored'])[selected]))}


def flags(summary: dict[str, Any]) -> dict[str, bool]:
    if not summary['sufficient']:return {'edge_width':False,'contrast_proxy':False,'directional':False}
    return {'edge_width':summary['median_width']>=4.,'contrast_proxy':summary['contrast_soft_fraction']>=.6,
            'directional':summary['direction_ratio'] is not None and summary['direction_ratio']>=1.6 and summary['direction_wide_width']>=4.5}
