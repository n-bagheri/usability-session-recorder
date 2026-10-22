"""Recorded-frame density layers; sample counts and partial cursor time are distinct metrics."""
import math
import numpy as np
from PIL import Image,ImageDraw
from matplotlib import colormaps


def density_layers(reference,points,opacity=.55,intensity=1.0,sigma=0,weights=None):
    if not (0<=opacity<=1 and 0<intensity<=5 and 0<=sigma<=4):raise ValueError('Heatmap opacity/intensity/spread are out of range')
    w,h=reference.size;grid=np.zeros((128,128),dtype=float)
    weights=[1.0]*len(points) if weights is None else weights
    if len(weights)!=len(points):raise ValueError('Each density point needs one weight')
    for (x,y),weight in zip(points,weights):
        if not math.isfinite(weight) or weight<0:raise ValueError('Density weights must be finite and nonnegative')
        if 0<=x<w and 0<=y<h:grid[min(int(y/h*128),127),min(int(x/w*128),127)]+=weight
    shown=grid.copy()
    if sigma>0:
        radius=max(1,math.ceil(3*sigma));kernel=np.exp(-np.arange(-radius,radius+1,dtype=float)**2/(2*sigma*sigma));kernel/=kernel.sum()
        for axis in (0,1):shown=np.apply_along_axis(lambda a:np.convolve(a,kernel,mode='same'),axis,shown)
        if shown.sum():shown*=grid.sum()/shown.sum()
    norm=np.clip(shown/shown.max()*intensity,0,1) if shown.max() else shown
    color=(colormaps['turbo'](norm)*255).astype('uint8');color[:,:,3]=np.where(shown>0,norm*opacity*255,0).astype('uint8')
    overlay=Image.fromarray(color).resize((w,h),Image.Resampling.BILINEAR if sigma else Image.Resampling.NEAREST)
    return Image.alpha_composite(reference.convert('RGBA'),overlay).convert('RGB'),overlay,grid,shown


def cursor_time_points(data,events,max_gap=.25):
    points=[];weights=[]
    for a,b in zip(events,events[1:]):
        t1,t2=data.time(a),data.time(b)
        if t1 is None or t2 is None or not 0<t2-t1<=max_gap or b['raw_line']!=a['raw_line']+1:continue
        p,q=data.predict(a),data.predict(b)
        ma,mb=data.mapping(a),data.mapping(b)
        if p is not None and q is not None and ma and mb and ma['id']==mb['id']:
            points.append(p);weights.append(t2-t1)
    return points,weights
