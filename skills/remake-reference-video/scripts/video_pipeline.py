#!/usr/bin/env python3
"""Deterministic helpers for a model-authored reference-video replacement plan.

These tools do not infer scripts or universally detect text. The agent inspects
the video, creates the mapping/masks, and checks the resulting pictures.
"""
from pathlib import Path
from fractions import Fraction
from concurrent.futures import ThreadPoolExecutor
import argparse, json, math, os, shutil, subprocess, tempfile, unicodedata, uuid
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy import ndimage as nd
from fontTools.ttLib import TTFont
from font_setup import ensure_font

ROOT=Path(__file__).resolve().parents[1]
def default_font():
    """Prefer a locally supplied authorized font; otherwise fetch the OFL font."""
    for path in [ROOT/'assets/fonts/private/SanJiXingKaiJianTi-Cu-2.ttf',
                 ROOT/'assets/fonts/SanJiXingKaiJianTi-Cu-2.ttf']:
        if path.is_file():return path
    return ensure_font()

def run(args):
    subprocess.run([str(x) for x in args],check=True)

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))

def files(directory):
    return sorted(Path(directory).glob('f_*.png'),key=lambda p:int(p.stem.split('_')[-1]))

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def rgb(value):
    value=value.lstrip('#')
    if len(value)!=6:raise ValueError('Use an RGB hex color, e.g. F1EAC2')
    return tuple(int(value[i:i+2],16) for i in (0,2,4))

def contact(frame_files,indices,out,fps,columns=6):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    for page in range((len(indices)+35)//36):
        batch=indices[page*36:(page+1)*36]
        canvas=Image.new('RGB',(columns*200,math.ceil(len(batch)/columns)*382),(246,246,244))
        draw=ImageDraw.Draw(canvas)
        for j,i in enumerate(batch):
            with Image.open(frame_files[i]) as raw:
                im=raw.convert('RGB');im.thumbnail((192,350))
            x=j%columns*200;y=j//columns*382
            canvas.paste(im,(x+(200-im.width)//2,y+25))
            draw.text((x+6,y+6),f'f{i} | {i/fps:.3f}s',fill='black')
        canvas.save(out/f'contact_{page+1:03d}.jpg',quality=90)

def prepare(a):
    job=Path(a.job).resolve();job.mkdir(parents=True,exist_ok=True)
    frames=job/'frames'
    if frames.exists() and any(frames.iterdir()):raise ValueError('Use a new analysis directory; frames already exist')
    frames.mkdir(exist_ok=True)
    metadata=probe(a.video);v=next(x for x in metadata['streams'] if x['codec_type']=='video')
    rate=a.fps or v.get('avg_frame_rate') or v.get('r_frame_rate')
    if not rate or rate=='0/0':rate='30/1'
    fr=Fraction(rate)
    if not 0<float(fr)<=240:raise ValueError('Unusual frame rate; inspect the source and specify --fps')
    run(['ffmpeg','-hide_banner','-loglevel','error','-i',a.video,'-vf',f'scale=trunc(iw*sar/2)*2:trunc(ih/2)*2,setsar=1,fps={fr.numerator}/{fr.denominator}','-an','-start_number','1',frames/'f_%06d.png'])
    ff=files(frames)
    if not ff:raise ValueError('No frames decoded')
    with Image.open(ff[0]) as im:w,h=im.size
    media={'path':str(Path(a.video).resolve()),'frame_dir':str(frames),'width':w,'height':h,'fps':str(fr), 'frames':len(ff),'duration':len(ff)/float(fr),'original_probe':metadata,'note':'Decoded CFR sampling; inspect original_probe for rotation/VFR differences.'}
    write_json(job/'media.json',media)
    step=max(1,round(a.step*float(fr)))
    indices=sorted(set(range(0,len(ff),step))|{len(ff)-1})
    contact(ff,indices,job/'contacts',float(fr))
    print(json.dumps({k:media[k] for k in ['frame_dir','width','height','fps','frames','duration']},ensure_ascii=False))

def mask_color(a):
    src=files(a.frames);dest=Path(a.masks);dest.mkdir(parents=True,exist_ok=True)
    if not src:raise ValueError('No source frames')
    end=len(src) if a.end is None else a.end
    if not 0<=a.start<end<=len(src):raise ValueError('Invalid frame interval')
    target=np.array(rgb(a.color),dtype='float32')
    for i in range(a.start,end):
        im=np.asarray(Image.open(src[i]).convert('RGB'));h,w=im.shape[:2]
        region=np.ones((h,w),bool)
        if a.roi:
            x,y,rw,rh=map(int,a.roi.split(','))
            if x<0 or y<0 or rw<=0 or rh<=0 or x+rw>w or y+rh>h:raise ValueError('ROI outside image')
            region[:]=False;region[y:y+rh,x:x+rw]=True
        mask=(np.linalg.norm(im.astype('float32')-target,axis=2)<=a.tolerance)&region
        if a.min_area>1:
            labels,_=nd.label(mask);sizes=np.bincount(labels.ravel());keep=sizes>=a.min_area;keep[0]=False;mask=keep[labels]
        if a.grow:mask=nd.binary_dilation(mask,iterations=a.grow)
        path=dest/src[i].name
        if path.exists():mask|=np.asarray(Image.open(path).convert('L'))>0
        if a.protect and (Path(a.protect)/src[i].name).exists():mask&=np.asarray(Image.open(Path(a.protect)/src[i].name).convert('L'))==0
        Image.fromarray(mask.astype('uint8')*255).save(path)
    print(f'Masks updated for [{a.start}, {end}); inspect them before cleaning.')

def clean(a):
    src=files(a.frames);dest=Path(a.output)
    if not src:raise ValueError('No source frames')
    if dest.exists() and any(dest.iterdir()):raise ValueError('Use a new clean-frame directory')
    dest.mkdir(parents=True,exist_ok=True)
    if a.color:
        first=np.asarray(Image.open(src[0]).convert('RGB'));base=np.empty_like(first);base[:]=rgb(a.color)
    else:
        if not a.samples:raise ValueError('Provide inspected clean samples or a solid --color')
        indices=[int(i) for i in a.samples.split(',')]
        if any(i<0 or i>=len(src) for i in indices):raise ValueError('Sample frame outside source')
        base=np.median(np.stack([np.asarray(Image.open(src[i]).convert('RGB')) for i in indices]),axis=0).astype('uint8')
    count=0
    for path in src:
        mp=Path(a.masks)/path.name
        if not mp.exists():shutil.copy2(path,dest/path.name);continue
        raw=np.asarray(Image.open(path).convert('RGB'))
        mask=np.asarray(Image.open(mp).convert('L'),dtype='float32')/255
        if mask.shape!=raw.shape[:2]:raise ValueError('Mask dimensions do not match source')
        protection=np.zeros_like(mask)
        if a.protect and (Path(a.protect)/path.name).exists():protection=np.asarray(Image.open(Path(a.protect)/path.name).convert('L'))/255
        alpha=nd.gaussian_filter(mask,a.feather) if a.feather else mask.copy()
        alpha=np.maximum(alpha,mask)*(1-protection)
        out=raw*(1-alpha[:,:,None])+base*alpha[:,:,None]
        Image.fromarray(np.clip(out,0,255).astype('uint8')).save(dest/path.name);count+=1
    if not count:raise ValueError('No matching masks; no text was removed')
    print(f'Clean plate: {len(src)} frames; {count} frames had masks. Inspect visually.')

def load_plan(path):
    p=read_json(path);base=Path(path).resolve().parent
    def resolve(value):
        f=Path(value);return str(f if f.is_absolute() else (base/f).resolve())
    p['source']['frame_dir']=resolve(p['source']['frame_dir'])
    p.setdefault('plate',{})
    p['plate']['frame_dir']=resolve(p['plate'].get('frame_dir',p['source']['frame_dir']))
    p.setdefault('font',{})
    p['font']['path']=resolve(p['font']['path']) if p['font'].get('path') else str(default_font())
    with TTFont(p['font']['path']) as font:
        postscript=font['name'].getDebugName(6)
    if not postscript:raise ValueError('Font has no PostScript name')
    if p['font'].get('postscript',postscript)!=postscript:
        raise ValueError('Configured PostScript name differs from the selected font')
    p['font']['postscript']=postscript
    p.setdefault('output',{})
    for k,v in [('width',1080),('height',1920),('fps',p['source']['fps']),('background',[0,0,0])]:p['output'].setdefault(k,v)
    for layer in p['layers']:
        layer.setdefault('tracking',0);layer.setdefault('fill',[241,234,194]);layer.setdefault('role','primary')
    return p

def text_key(text):return unicodedata.normalize('NFC',text).replace('\n','').replace('\r','')

def validate(p):
    if p.get('version')!=1:raise ValueError('Unsupported plan version')
    src=p['source'];out=p['output'];n=int(src['frames'])
    if n<=0 or min(src['width'],src['height'],out['width'],out['height'])<=0:raise ValueError('Invalid media dimensions/count')
    if out['width']%2 or out['height']%2:raise ValueError('yuv420p requires even output dimensions')
    if Fraction(src['fps'])!=Fraction(out['fps']):raise ValueError('Normalize source with prepare --fps first; do not silently change timing')
    frames=files(p['plate']['frame_dir'])
    if len(frames)!=n:raise ValueError('Plate frame count differs from plan')
    if [f.name for f in frames]!=[f'f_{i+1:06d}.png' for i in range(n)]:raise ValueError('Frames must be contiguous f_000001.png ...')
    with Image.open(frames[0]) as im:
        if im.size!=(src['width'],src['height']):raise ValueError('Plate dimensions differ from source coordinates')
    cmap=TTFont(p['font']['path']).getBestCmap();missing=set()
    ids=set();slots={x['id']:x for x in p['replacements']}
    if len(slots)!=len(p['replacements']):raise ValueError('Duplicate replacement id')
    for slot in slots.values():
        if not 0<=slot['start']<slot['end']<=n:raise ValueError('Replacement outside source')
    for l in p['layers']:
        if l['id'] in ids:raise ValueError('Duplicate layer id')
        ids.add(l['id'])
        if l['slot'] not in slots:raise ValueError('Layer has unknown slot')
        if not 0<=l['in']<l['out']<=n or l['font_size']<=0:raise ValueError('Invalid layer timing/size')
        if '\n' in l['text']:raise ValueError('Use one layer per line')
        if l['language'] not in ['zh','en'] or l['role'] not in ['primary','echo']:raise ValueError('Unknown language/role')
        if len(l['fill'])!=3 or any(c<0 or c>255 for c in l['fill']):raise ValueError('Fill uses 0..255 RGB')
        missing|={c for c in l['text'] if ord(c) not in cmap and not c.isspace()}
        keys=l['keys']
        if not keys or keys[0][0]!=l['in']:raise ValueError('First key must be at layer in frame')
        previous=-1
        for k in keys:
            if len(k)!=8 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in k):raise ValueError('Key requires 8 finite numbers')
            if not l['in']<=k[0]<l['out'] or k[0]<=previous:raise ValueError('Unsorted/out-of-range keys')
            if min(k[3],k[4],k[7])<0 or not 0<=k[6]<=1:raise ValueError('Invalid scale/opacity/blur')
            previous=k[0]
    if missing:raise ValueError('Missing font glyphs: '+''.join(sorted(missing)))
    for slot in slots.values():
        if slot.get('preserve'):continue
        for lang,key in [('zh','cn'),('en','en')]:
            actual=''.join(l['text'] for l in p['layers'] if l['slot']==slot['id'] and l['language']==lang and l['role']=='primary')
            expected=slot.get(key,'')
            if text_key(actual)!=text_key(expected):raise ValueError(f'Copy mismatch: {slot["id"]} {lang}: {actual!r} != {expected!r}')
    return {'slots':len(slots),'layers':len(p['layers']),'frames':n,'font_glyphs':'passed','copy':'passed','note':'Plan checks do not prove visual fidelity or OCR correctness.'}

def at(keys,frame):
    if frame<=keys[0][0]:return keys[0][1:]
    for a,b in zip(keys,keys[1:]):
        if frame<=b[0]:
            t=(frame-a[0])/(b[0]-a[0]);return [x+(y-x)*t for x,y in zip(a[1:],b[1:])]
    return keys[-1][1:]

def sprite(layer,font_path,factor):
    size=max(1,round(layer['font_size']*factor*2));font=ImageFont.truetype(font_path,size)
    text=layer['text'];spacing=layer['tracking']*factor*2;lengths=[font.getlength(c) for c in text]
    w=math.ceil(sum(lengths)+max(0,len(text)-1)*spacing+size)
    if w<=0:raise ValueError('Invalid negative tracking')
    im=Image.new('RGBA',(w,size*3));draw=ImageDraw.Draw(im);x=size/2
    for c,advance in zip(text,lengths):
        draw.text((x,0),c,font=font,fill=tuple(layer['fill'])+(255,));x+=advance+spacing
    box=im.getbbox()
    if not box:return Image.new('RGBA',(1,1))
    im=im.crop(box);return im.resize((max(1,round(im.width/2)),max(1,round(im.height/2))),Image.Resampling.LANCZOS)

def render(a):
    p=load_plan(a.plan);validate(p);src=p['source'];out=p['output'];frame_files=files(p['plate']['frame_dir'])
    w,h=out['width'],out['height'];factor=min(w/src['width'],h/src['height'])
    bw,bh=round(src['width']*factor),round(src['height']*factor);dx,dy=(w-bw)/2,(h-bh)/2
    sprites=[sprite(l,p['font']['path'],factor) for l in p['layers']]
    def frame_bytes(i):
        with Image.open(frame_files[i]) as raw:plate=raw.convert('RGB').resize((bw,bh),Image.Resampling.LANCZOS)
        im=Image.new('RGBA',(w,h),tuple(out['background'])+(255,));im.paste(plate,(round(dx),round(dy)))
        for l,sp in zip(p['layers'],sprites):
            if not l['in']<=i<l['out']:continue
            x,y,sx,sy,angle,opacity,blur=at(l['keys'],i)
            if min(sx,sy)<.001 or opacity<=0:continue
            x=x*factor+dx;y=y*factor+dy;r=math.radians(angle);co=math.cos(r);si=math.sin(r)
            aa,bb=co/sx,si/sx;dd,ee=-si/sy,co/sy
            coeff=(aa,bb,sp.width/2-aa*x-bb*y,dd,ee,sp.height/2-dd*x-ee*y)
            fg=sp.transform((w,h),Image.Transform.AFFINE,coeff,Image.Resampling.BICUBIC)
            if blur>.1:fg=fg.filter(ImageFilter.GaussianBlur(blur*factor))
            if opacity<.999:fg.putalpha(fg.getchannel('A').point(lambda v:v*opacity))
            im=Image.alpha_composite(im,fg)
        return im.convert('RGB').tobytes()
    dest=Path(a.output).resolve();dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and not a.overwrite:raise ValueError('Output exists; use another filename or --overwrite')
    lock=dest.with_name(dest.name+'.lock');fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    tmp=dest.with_name(dest.stem+'.'+uuid.uuid4().hex+'.tmp.mp4');proc=None
    try:
        proc=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{w}x{h}','-framerate',str(out['fps']),'-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf',str(a.crf),'-pix_fmt','yuv420p','-movflags','+faststart',str(tmp)],stdin=subprocess.PIPE)
        n=src['frames'];queue_size=max(1,a.workers*2)
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            pending={i:pool.submit(frame_bytes,i) for i in range(min(n,queue_size))}
            for i in range(n):
                proc.stdin.write(pending.pop(i).result())
                if i+queue_size<n:pending[i+queue_size]=pool.submit(frame_bytes,i+queue_size)
                if i%120==0:print(f'{i}/{n}',flush=True)
        proc.stdin.close()
        if proc.wait()!=0:raise RuntimeError('Video encoding failed')
        verify_file(tmp,p)
        os.replace(tmp,dest)
    finally:
        if proc and proc.poll() is None:
            proc.terminate();proc.wait()
        if tmp.exists():tmp.unlink()
        lock.unlink(missing_ok=True)
    print(str(dest))

def verify_file(video,p):
    result=probe(video);streams=result['streams'];v=next(x for x in streams if x['codec_type']=='video');out=p['output'];n=p['source']['frames'];fps=Fraction(out['fps'])
    if any(x['codec_type']=='audio' for x in streams):raise ValueError('Expected no audio stream')
    if (v['width'],v['height'])!=(out['width'],out['height']):raise ValueError('Wrong output dimensions')
    if Fraction(v['r_frame_rate'])!=fps:raise ValueError('Wrong frame rate')
    if int(v.get('nb_frames',-1))!=n:raise ValueError('Wrong frame count')
    if abs(float(result['format']['duration'])-n/float(fps))>1/float(fps):raise ValueError('Wrong duration')
    run(['ffmpeg','-hide_banner','-loglevel','error','-i',video,'-f','null','-'])
    return {'video':str(video),'width':v['width'],'height':v['height'],'frames':n,'fps':str(fps),'duration':n/float(fps),'audio_streams':0,'decode':'passed','native_ae_render_verified':False,'pixel_exact_match_claimed':False}

def verify(a):
    p=load_plan(a.plan);report={'plan':validate(p),'media':verify_file(a.video,p)}
    if a.report:write_json(a.report,report)
    print(json.dumps(report,ensure_ascii=False))

def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    q=sub.add_parser('prepare');q.add_argument('--video',required=True);q.add_argument('--job',required=True);q.add_argument('--step',type=float,default=.1);q.add_argument('--fps');q.set_defaults(fn=prepare)
    q=sub.add_parser('mask-color');q.add_argument('--frames',required=True);q.add_argument('--masks',required=True);q.add_argument('--start',type=int,default=0);q.add_argument('--end',type=int);q.add_argument('--roi');q.add_argument('--color',required=True);q.add_argument('--tolerance',type=float,default=45);q.add_argument('--min-area',type=int,default=1);q.add_argument('--grow',type=int,default=3);q.add_argument('--protect');q.set_defaults(fn=mask_color)
    q=sub.add_parser('clean');q.add_argument('--frames',required=True);q.add_argument('--masks',required=True);q.add_argument('--samples');q.add_argument('--color');q.add_argument('--output',required=True);q.add_argument('--feather',type=float,default=1);q.add_argument('--protect');q.set_defaults(fn=clean)
    q=sub.add_parser('check-plan');q.add_argument('--plan',required=True);q.set_defaults(fn=lambda a:print(json.dumps(validate(load_plan(a.plan)),ensure_ascii=False)))
    q=sub.add_parser('render');q.add_argument('--plan',required=True);q.add_argument('--output',required=True);q.add_argument('--crf',type=int,default=18);q.add_argument('--workers',type=int,default=2);q.add_argument('--overwrite',action='store_true');q.set_defaults(fn=render)
    q=sub.add_parser('verify');q.add_argument('--video',required=True);q.add_argument('--plan',required=True);q.add_argument('--report');q.set_defaults(fn=verify)
    a=ap.parse_args()
    if hasattr(a,'workers') and a.workers<1:ap.error('--workers must be positive')
    if hasattr(a,'step') and a.step<=0:ap.error('--step must be positive')
    a.fn(a)

if __name__=='__main__':main()
