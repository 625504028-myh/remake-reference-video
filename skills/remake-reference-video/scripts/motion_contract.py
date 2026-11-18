#!/usr/bin/env python3
"""Check a model-authored shot contract against actual render inputs.

Checks timing, ordered copy selection and evidence references. It cannot judge
whether the observed inventory is complete or the rendered motion looks correct.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import unicodedata

CATEGORIES=('text','camera','scene','elements','transition')

def require(condition,message):
    if not condition:raise ValueError(message)

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def textkey(value):
    return unicodedata.normalize('NFC',value).replace('\n','').replace('\r','')

def check_manifest(path,plan):
    path=Path(path).resolve();base=path.parent;m=read(path)
    def resolve(value):
        p=Path(value);return p.resolve() if p.is_absolute() else (base/p).resolve()
    def nonempty(value):return isinstance(value,str) and bool(value.strip())
    require(m.get('version')==1,'Unsupported motion manifest version')
    require(m.get('mode') in ('motion-remake','text-replace'),'Unknown production mode')
    n=plan['source']['frames'];fps=Fraction(plan['source']['fps'])
    media=read(resolve(m['reference_media']));window=media.get('window',{})
    require(window,'Run prepare with the current version to record the reference window')
    require(media['frames']==n and Fraction(media['fps'])==fps,'Reference window does not match render timing')
    require(Fraction(plan['output']['fps'])==fps,'Output frame rate differs from reference')
    require(Path(media['frame_dir']).resolve()==Path(plan['source']['frame_dir']).resolve(),'Render source is not the inspected reference window')
    requested=m['requested_window']
    require(requested['start']==window['requested_start'] and requested.get('duration')==window['requested_duration'],'Requested window differs from inspected reference window')
    require(m['frames']==n and Fraction(m['fps'])==fps,'Contract and render duration differ')
    slots={s['id']:s for s in plan['replacements']};layers={l['id']:l for l in plan['layers']}
    units=m['copy_units'];require(bool(units),'Copy inventory is empty')
    copy_policy=m.get('copy_policy','full')
    require(copy_policy in ('full','prefix'),'Unknown copy policy')
    used_ids=set();all_ids=set();unit_slots={};mapped=[];first_starts=[];deferred=False
    for unit in units:
        uid=unit['id'];require(uid not in all_ids,'Duplicate copy unit id');all_ids.add(uid)
        require(unit['status'] in ('used','deferred'),'Unknown copy status')
        require(nonempty(unit.get('cn')) or nonempty(unit.get('en')),'Empty copy unit')
        if unit['status']=='deferred':
            require(copy_policy=='prefix','Deferred copy requires explicit copy_policy=prefix permission')
            deferred=True;require(not unit.get('slot_ids') and not unit.get('slot_occurrences'),'Deferred copy must not occupy slots');continue
        require(not deferred,'Used copy must be an ordered prefix; do not skip earlier sentences')
        used_ids.add(uid)
        require(not ('slot_ids' in unit and 'slot_occurrences' in unit),'Use slot_ids or slot_occurrences, not both')
        occurrences=unit.get('slot_occurrences',[unit.get('slot_ids',[])])
        require(isinstance(occurrences,list) and occurrences,'Used copy has no occurrences')
        refs=[];starts=[]
        for occurrence in occurrences:
            require(isinstance(occurrence,list) and occurrence and all(s in slots for s in occurrence),'Used copy references missing render slots')
            require(occurrence==sorted(occurrence,key=lambda s:slots[s]['start']),'Copy slots are out of order')
            starts.append(slots[occurrence[0]]['start'])
            for language in ('cn','en'):
                if language in unit:
                    actual=''.join(slots[s].get(language,'') for s in occurrence)
                    require(textkey(actual)==textkey(unit[language]),'Selected copy differs from render plan: '+uid+' '+language)
            refs.extend(occurrence)
        require(starts==sorted(starts),'Repeated occurrences are out of order')
        first_starts.append(starts[0]);unit_slots[uid]=refs
        mapped.extend(refs)
    require(used_ids,'No script content selected')
    require(len(mapped)==len(set(mapped)),'Render slot assigned to multiple copy units')
    require(first_starts==sorted(first_starts),'Selected script first-appearance order differs from timeline')
    required_slots={s for s in slots if not slots[s].get('preserve')}
    require(set(mapped)==required_slots,'Unmapped or unexpected render copy slots')
    artifacts={}
    for item in m.get('artifacts',[]):
        aid=item['id'];require(aid not in artifacts,'Duplicate artifact id')
        ap=resolve(item['path'])
        require(ap.is_file() and ap.stat().st_size>0,'Missing/empty production artifact: '+aid)
        require(item.get('kind') in ('scene_asset','build_source','project','review'),'Unknown artifact kind')
        require(nonempty(item.get('description')),'Describe the role of each artifact')
        artifacts[aid]=item
    plate=resolve(m['plate']['frame_dir'])
    require(plate==Path(plan['plate']['frame_dir']).resolve(),'Contract plate is not the actual render plate')
    expected=[f'f_{i+1:06d}.png' for i in range(n)]
    require(sorted(x.name for x in plate.glob('f_*.png'))==expected,'Incomplete precomposed plate frames')
    builder=m['plate'].get('builder_artifact')
    shots=m['shots'];require(bool(shots),'No shots inspected')
    cursor=0;shot_ids=set();effect_count=0;rebuilt=0;seen_units=set()
    for shot in shots:
        sid=shot['id'];require(sid not in shot_ids,'Duplicate shot id');shot_ids.add(sid)
        require(type(shot['in']) is int and type(shot['out']) is int,'Shot boundaries must use integer frames')
        require(shot['in']==cursor and cursor<shot['out']<=n,'Shots must cover the complete window without gaps/overlaps')
        cursor=shot['out'];refs=shot.get('copy_ids',[])
        require(all(x in used_ids for x in refs),'Shot references unused or unknown copy')
        require(all(any(slots[x]['start']<shot['out'] and slots[x]['end']>shot['in'] for x in unit_slots[u]) for u in refs),'Copy unit does not occur in its declared shot')
        seen_units.update(refs)
        effects=shot['effects'];require(set(effects)==set(CATEGORIES),'Inspect all five effect categories in every shot')
        for category in CATEGORIES:
            items=effects[category]
            require(isinstance(items,list),'Effect category must be a list')
            if not items:require(nonempty(shot.get('absent',{}).get(category)),'Explain absent category: '+sid+' '+category)
            for effect in items:
                effect_count+=1
                require(nonempty(effect.get('observed')) and nonempty(effect.get('implementation')),'Describe observed motion and implementation')
                lids=effect.get('layer_ids',[]);aids=effect.get('artifact_ids',[])
                require(lids or aids,'Effect has no concrete implementation evidence')
                if category!='text':require(bool(aids),'Non-text motion must reference a scene artifact or composition, not just text layers')
                require(all(x in layers for x in lids),'Effect refers to unknown render layer')
                require(all(layers[x]['in']<shot['out'] and layers[x]['out']>shot['in'] for x in lids),'Effect layer is outside its shot')
                require(all(x in artifacts for x in aids),'Effect refers to missing production artifact')
        mode=shot['scene_treatment']
        require(mode in ('rebuilt','generated','preserved-abstract'),'Unknown scene treatment')
        if mode in ('rebuilt','generated'):
            rebuilt+=1
            require(nonempty(shot.get('semantic_match')),'Describe how replacement visuals express the new script')
            scene_ids=[x for e in effects['scene'] for x in e.get('artifact_ids',[])]
            require(any(artifacts[x]['kind']=='scene_asset' for x in scene_ids),'Rebuilt scene needs a real scene asset')
        else:require(nonempty(shot.get('preserve_reason')),'Explain why the abstract scene can be preserved')
    require(cursor==n,'Shot inventory ends before the rendered video')
    require(seen_units==used_ids,'Selected copy is missing from shot inventory')
    if m['mode']=='motion-remake' and rebuilt:
        require(builder in artifacts and artifacts[builder]['kind'] in ('build_source','project'),'Rebuilt scenes require a real scene build script or project')
        require(plate!=Path(plan['source']['frame_dir']).resolve(),'Rebuilt scenes cannot reuse source frames as their entire plate')
        source=Path(plan['source']['frame_dir'])
        def digest(p):return hashlib.sha256(p.read_bytes()).digest()
        require(any(digest(plate/name)!=digest(source/name) for name in expected),'Motion-remake plate is an unchanged copy of the reference')
    return {'status':'passed','mode':m['mode'],'frames':n,'fps':str(fps),'shots':len(shots),
        'effects_declared':effect_count,'rebuilt_scenes':rebuilt,'copy_policy':copy_policy,'copy_units_used':len(used_ids),'copy_units_deferred':len(units)-len(used_ids),
        'mechanical_checks_only':True,'visual_fidelity_verified':False,
        'note':'Artifact existence and declarations do not prove use, complete effect detection, visual fidelity or readability. Inspect rendered footage.'}

def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    q=sub.add_parser('check');q.add_argument('--manifest',required=True);q.add_argument('--plan',required=True);q.add_argument('--report')
    a=ap.parse_args()
    from video_pipeline import load_plan
    report=check_manifest(a.manifest,load_plan(a.plan))
    if a.report:Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
