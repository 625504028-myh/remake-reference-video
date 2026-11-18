#!/usr/bin/env python3
"""Exercise selected-window rendering and rejection of misleading remake plans.

Usage: python tests/motion_contract_smoke.py [skill directory]
"""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from PIL import Image, ImageDraw

skill=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]/'skills/remake-reference-video'
sys.path.insert(0,str(skill/'scripts'))
import video_pipeline as vp
import motion_contract as mc


def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def expect_failure(fn,label):
    try:fn()
    except (ValueError,KeyError) as exc:
        print('rejected:',label, str(exc));return
    raise AssertionError('Did not reject '+label)

with tempfile.TemporaryDirectory(prefix='motion-contract-smoke-') as temp:
    job=Path(temp);reference=job/'reference.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=s=96x160:r=10:d=3','-an','-c:v','libx264','-pix_fmt','yuv420p',str(reference)],check=True)
    def prepare(name,start=0,duration=None,fps=None):
        return vp.prepare(SimpleNamespace(video=str(reference),job=str(job/name),start=start,duration=duration,fps=fps,step=.5))
    prepare('full')
    prepare('analysis',1,1)
    media=vp.read_json(job/'analysis/media.json')
    assert media['frames']==10 and media['window']['start_frame']==10 and media['window']['actual_duration']==1
    assert (job/'analysis/frames/f_000001.png').read_bytes()==(job/'full/frames/f_000011.png').read_bytes()
    prepare('fractional',.1,.5,'30000/1001')
    fraction=vp.read_json(job/'fractional/media.json')
    assert fraction['frames']==15 and abs(fraction['duration']-.5005)<1e-8
    expect_failure(lambda:prepare('too-long',2.5,1),'window outside reference')
    expect_failure(lambda:prepare('negative',-1,1),'negative window')
    plate=job/'rebuilt_frames';plate.mkdir()
    for i in range(10):
        im=Image.new('RGB',(96,160),(13,17,30));d=ImageDraw.Draw(im)
        x=12+i*4;d.rounded_rectangle((x,35,min(x+35,94),100),radius=5,fill=(80,210,200))
        im.save(plate/f'f_{i+1:06d}.png')
    shutil.copy2(plate/'f_000005.png',job/'scene.png')
    shutil.copy2(__file__,job/'build_scene.py')
    plan={'version':1,'source':{k:media[k] for k in ('frame_dir','width','height','fps','frames')},
        'plate':{'frame_dir':str(plate)},'output':{'width':96,'height':160,'fps':'10/1','background':[0,0,0]},
        'replacements':[{'id':'s1','start':0,'end':10,'cn':'新片','en':''}],
        'layers':[{'id':'s1_cn','slot':'s1','language':'zh','role':'primary','text':'新片','font_size':22,'fill':[255,255,255],'in':0,'out':10,'keys':[[0,48,115,.3,.3,0,1,0],[3,48,115,1,1,0,1,0]]}],
        'motion_manifest':'shot_manifest.json'}
    dump(job/'plan.json',plan)
    manifest={'version':1,'mode':'motion-remake','reference_media':'analysis/media.json',
        'requested_window':{'start':1,'duration':1},'fps':'10/1','frames':10,'copy_policy':'prefix',
        'copy_units':[{'id':'u1','cn':'新片','en':'','status':'used','slot_ids':['s1']},{'id':'u2','cn':'下一段','status':'deferred','slot_ids':[]}],
        'artifacts':[{'id':'scene','path':'scene.png','kind':'scene_asset','description':'Moving product card'},
                     {'id':'builder','path':'build_scene.py','kind':'build_source','description':'Scene producer'}],
        'plate':{'frame_dir':'rebuilt_frames','builder_artifact':'builder'},
        'shots':[{'id':'a','in':0,'out':10,'copy_ids':['u1'],'scene_treatment':'rebuilt','semantic_match':'New product card for new film',
            'effects':{'text':[{'observed':'scale in','implementation':'text keys','layer_ids':['s1_cn']}],
                       'camera':[],'scene':[{'observed':'moving card','implementation':'precomposed plate','artifact_ids':['scene','builder']}],
                       'elements':[],'transition':[]},
            'absent':{'camera':'locked camera','elements':'none in fixture','transition':'one stable shot'}}]}
    dump(job/'shot_manifest.json',manifest)
    loaded=vp.load_plan(job/'plan.json')
    assert vp.validate(loaded)['motion_contract']['status']=='passed'
    vp.render(SimpleNamespace(plan=str(job/'plan.json'),output=str(job/'final.mp4'),overwrite=False,crf=25,workers=1))
    assert vp.verify_file(job/'final.mp4',loaded)['frames']==10
    def reject_mutation(change,label):
        changed=copy.deepcopy(manifest);change(changed);dump(job/'shot_manifest.json',changed)
        expect_failure(lambda:vp.validate(loaded),label)
        dump(job/'shot_manifest.json',manifest)
    reject_mutation(lambda m:m.update(frames=30),'full clip instead of requested window')
    reject_mutation(lambda m:m['requested_window'].update(start=0),'wrong source interval')
    reject_mutation(lambda m:m['shots'][0].update(out=9),'uncovered frame')
    reject_mutation(lambda m:m['copy_units'].reverse(),'skipped script prefix')
    reject_mutation(lambda m:m['copy_units'][0].update(cn='错误'),'changed selected copy')
    reject_mutation(lambda m:m['shots'][0]['effects'].pop('camera'),'uninspected effect category')
    reject_mutation(lambda m:m['shots'][0]['effects']['text'][0].update(layer_ids=['missing']),'missing text effect layer')
    reject_mutation(lambda m:m['artifacts'][0].update(path='missing.png'),'missing scene artifact')
    reject_mutation(lambda m:m['shots'][0]['effects'].update(camera=[{'observed':'camera zoom','implementation':'title scale only','layer_ids':['s1_cn']}]),'text scale used as camera reconstruction')
    reject_mutation(lambda m:m['shots'][0].update(scene_treatment='preserved-abstract'),'abstract preservation without rationale')
    reject_mutation(lambda m:m.pop('copy_policy'),'deferred copy without explicit prefix permission')
    copied=job/'copied_frames';shutil.copytree(job/'analysis/frames',copied)
    badplan=copy.deepcopy(loaded);badplan['plate']['frame_dir']=str(copied)
    badmanifest=copy.deepcopy(manifest);badmanifest['plate']['frame_dir']=str(copied);dump(job/'shot_manifest.json',badmanifest)
    expect_failure(lambda:vp.validate(badplan),'unchanged copied reference plate')
    dump(job/'shot_manifest.json',manifest)
    # Legitimate abstract references can retain their plate without fake rebuilds.
    abstract=copy.deepcopy(manifest);abstract['plate']={'frame_dir':str(job/'analysis/frames')}
    abstract['artifacts']=[];abstract['shots'][0]['scene_treatment']='preserved-abstract'
    abstract['shots'][0]['preserve_reason']='Reference contains only abstract graphics independent of the script'
    abstract['shots'][0]['effects']['scene']=[];abstract['shots'][0]['absent']['scene']='No business-specific scene'
    abstract_plan=copy.deepcopy(loaded);abstract_plan['plate']['frame_dir']=str(job/'analysis/frames')
    dump(job/'shot_manifest.json',abstract)
    assert vp.validate(abstract_plan)['motion_contract']['rebuilt_scenes']==0
    # One logical sentence can appear repeatedly across separate flash slots.
    repeated=copy.deepcopy(loaded);repeated['replacements'][0]['end']=5
    repeated['replacements'].append({'id':'s2','start':5,'end':10,'cn':'新片','en':''})
    repeated['layers'][0]['out']=5
    second=copy.deepcopy(repeated['layers'][0]);second.update(id='s2_cn',slot='s2',**{'in':5,'out':10})
    for key in second['keys']:key[0]+=5
    repeated['layers'].append(second)
    repeat_manifest=copy.deepcopy(manifest)
    repeat_manifest['copy_units'][0].pop('slot_ids')
    repeat_manifest['copy_units'][0]['slot_occurrences']=[['s1'],['s2']]
    repeat_manifest['shots'][0]['effects']['text'][0]['layer_ids'].append('s2_cn')
    dump(job/'shot_manifest.json',repeat_manifest)
    assert vp.validate(repeated)['motion_contract']['copy_units_used']==1
    mismatched=copy.deepcopy(repeated);mismatched['replacements'][1]['cn']='不同'
    expect_failure(lambda:mc.check_manifest(job/'shot_manifest.json',mismatched),'repeated occurrence differs from logical copy')
    dump(job/'shot_manifest.json',manifest)
    # Full-copy policy accepts complete copy and rejects hidden omission by default.
    full_manifest=copy.deepcopy(manifest);full_manifest.pop('copy_policy');full_manifest['copy_units'].pop()
    dump(job/'shot_manifest.json',full_manifest)
    assert vp.validate(loaded)['motion_contract']['copy_policy']=='full'
    dump(job/'shot_manifest.json',manifest)
    # Existing text replacement plans remain valid without a motion manifest.
    old=copy.deepcopy(loaded);old.pop('motion_manifest')
    assert vp.validate(old)['copy']=='passed'
print('Passed: selected-window render, rational fps, old-plan compatibility abstract preservation, repeated flash copy, copy policies and 15 rejection cases.')
