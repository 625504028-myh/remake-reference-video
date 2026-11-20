#!/usr/bin/env python3
"""Plan text-only jobs from a frozen, model-inspected bilingual timeline.

This tool checks explicit mappings; it does not perform OCR, infer natural-language
assignments, remove text, or prove that the non-text visuals were preserved.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import unicodedata

LANGUAGES=('cn','en')

def require(condition,message):
    if not condition:raise ValueError(message)

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def textkey(s):return unicodedata.normalize('NFC',s).replace('\r','').replace('\n','')
def resolve(base,value):
    p=Path(value);return p.resolve() if p.is_absolute() else (base/p).resolve()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def baseline_slots(b):
    require(b.get('version')==1 and b.get('extraction_complete') is True,'Freeze the complete bilingual extraction before planning')
    src=b['source'];fps=Fraction(src['fps']);n=src['frames']
    require(type(n) is int and n>0 and fps>0,'Invalid source frames/fps')
    require(all(type(src[k]) is int and src[k]>0 for k in ('width','height')),'Invalid source dimensions')
    slots=b['slots'];require(isinstance(slots,list) and slots,'No text slots extracted')
    ids=set();last=-1
    for s in slots:
        require(isinstance(s['id'],str) and s['id'] and s['id'] not in ids,'Duplicate/empty slot id');ids.add(s['id'])
        require(type(s['start']) is int and type(s['end']) is int and 0<=s['start']<s['end']<=n,'Invalid full-animation slot interval')
        require(s['start']>=last,'Baseline slots must be in reading/timeline order');last=s['start']
        require(all(k in s and isinstance(s[k],str) for k in LANGUAGES),'Extract both cn and en explicitly; use an empty string only when absent')
        interval=s.get('edit_window',[s['start'],s['end']])
        require(isinstance(interval,list) and len(interval)==2 and all(type(x) is int for x in interval),'Invalid edit dependency window')
        require(0<=interval[0]<=s['start']<s['end']<=interval[1]<=n,'Edit window must contain the complete slot animation')
    return slots

def changed_slot(slot,values,deleted):
    require(isinstance(deleted,list) and len(set(deleted))==len(deleted) and set(deleted)<=set(LANGUAGES),'delete must list cn and/or en explicitly')
    result={'slot_id':slot['id'],'start':slot['start'],'end':slot['end'],'source_cn':slot.get('cn',''),'source_en':slot.get('en','')}
    changed=[];preserved=[]
    for lang in LANGUAGES:
        value=values.get(lang)
        require(value is None or isinstance(value,str),'Replacement copy must be text or blank')
        require(not (lang in deleted and value is not None and value.strip()),'Cannot replace and delete the same language')
        original=slot.get(lang,'')
        new='' if lang in deleted else (value if value is not None and value.strip() else original)
        if unicodedata.normalize('NFC',new)!=unicodedata.normalize('NFC',original):changed.append(lang)
        else:new=original;preserved.append(lang)
        result[lang]=new
    result['changed_languages']=changed;result['preserve_languages']=preserved
    return result if changed else None

def compute(b,r):
    slots=baseline_slots(b);byid={s['id']:s for s in slots};src=b['source'];fps=Fraction(src['fps'])
    mode=r.get('mode');require(mode in ('manual','full-script'),'Choose manual or full-script')
    audio=r.get('audio',{'mode':'preserve'})
    if isinstance(audio,str):audio={'mode':audio}
    require(isinstance(audio,dict) and audio.get('mode') in ('preserve','mute','replace','mix'),'Unknown audio mode')
    if audio['mode'] in ('replace','mix'):
        require(isinstance(audio.get('path'),str) and bool(audio['path']),'Replacement/mixed audio requires the actual prepared audio file')
        require(audio.get('start',0)==0,'Prepare replacement/mixed audio for this job starting at zero')
    font=r.get('font');font_policy='provided' if font is not None else 'source'
    require(r.get('font_policy',font_policy)==font_policy,'A provided font policy requires an explicit font file')
    if font is not None:require(isinstance(font,dict) and isinstance(font.get('path'),str) and font['path'],'Provide an explicit font path')
    output=r.get('output',{})
    require(set(output)<=set(('width','height','fps')),'Unsupported output override')
    require(Fraction(output.get('fps',str(fps)))==fps,'Normalize and re-extract the source before changing its frame rate')
    width=output.get('width',src['width']);height=output.get('height',src['height'])
    require(all(type(x) is int and x>0 and x%2==0 for x in (width,height)),'Output dimensions must be positive even integers')
    requirements={'mode':'text-replace','preserve_nontext_visuals':True,'audio':audio['mode'],'audio_config':audio,'font_policy':font_policy,'font':font,
                  'width':width,'height':height,'fps':str(fps)}
    changes=[];selected=[];windows=[]
    if mode=='manual':
        edits=r.get('edits',[]);require(isinstance(edits,list),'edits must be a list');seen=set()
        for edit in edits:
            sid=edit['slot_id'];require(sid in byid and sid not in seen,'Unknown or repeated edited slot id');seen.add(sid)
            require(set(edit)<=set(('slot_id','cn','en','delete')),'Unsupported manual edit field')
            change=changed_slot(byid[sid],edit,edit.get('delete',[]))
            if change:
                changes.append(change);selected.append(sid);windows.append(byid[sid].get('edit_window',[byid[sid]['start'],byid[sid]['end']]))
        # Merge overlapping dependency windows, never bridge untouched gaps.
        merged=[]
        for start,end in sorted(windows):
            if merged and (start<merged[-1][1] or (r.get('merge_adjacent',False) and start==merged[-1][1])):
                merged[-1][1]=max(merged[-1][1],end)
            else:merged.append([start,end])
        windows=merged
    else:
        require(r.get('copy_policy','full')=='full','Full-script mode must use the complete script; fixed-budget truncation is not allowed')
        units=r.get('units',[]);assignments=r.get('assignments',[])
        require(isinstance(units,list) and units and isinstance(assignments,list),'Provide the full script units and explicit assignments')
        uids=[u['id'] for u in units];require(len(set(uids))==len(uids),'Duplicate script unit id')
        require([a['unit_id'] for a in assignments]==uids,'Every script unit must be assigned exactly once in original order')
        usable=[s for s in slots if s.get('usable',bool(s.get('cn','').strip() or s.get('en','').strip()))]
        consumed=[]
        for unit,assignment in zip(units,assignments):
            require(all(unit.get(k) is None or isinstance(unit.get(k),str) for k in LANGUAGES),'Script copy must be strings')
            require(any(isinstance(unit.get(k),str) and unit[k].strip() for k in LANGUAGES),'Empty script unit')
            refs=assignment.get('slot_ids',[])
            require(isinstance(refs,list) and refs and all(s in byid for s in refs),'Unknown or empty full-script assignment')
            deleted=assignment.get('delete',[]);values=[{} for _ in refs]
            for lang in LANGUAGES:
                text=unit.get(lang);parts=assignment.get(lang+'_parts')
                if text is not None and text.strip():
                    require(isinstance(parts,list) and len(parts)==len(refs) and all(isinstance(p,str) and p.strip() for p in parts),'Provide one nonblank copy part per assigned slot')
                    require(textkey(''.join(parts))==textkey(text),'Assignment omits, repeats or changes script copy')
                    for value,part in zip(values,parts):value[lang]=part
                else:require(parts is None,'Cannot introduce copy absent from the full script')
            for sid,value in zip(refs,values):
                change=changed_slot(byid[sid],value,deleted)
                if change:changes.append(change)
            consumed.extend(refs)
        require(consumed==[s['id'] for s in usable[:len(consumed)]] and len(consumed)<=len(usable),'Assignments must use consecutive slots from the first usable slot; no skips, reorder, repetition or overrun')
        require(consumed,'No full-script slots assigned');selected=consumed
        end=byid[consumed[-1]]['end']
        require(len(consumed)==len(usable) or usable[len(consumed)]['start']>=end,'Next unassigned title enters before the selected animation tail ends; resolve the overlap before export')
        require(all(byid[x].get('edit_window',[byid[x]['start'],byid[x]['end']])[1]<=end for x in consumed),'Last assigned slot does not include all required animation tails; correct the timeline instead of silently extending the output')
        windows=[[0,end]]
    changes.sort(key=lambda c:(c['start'],slots.index(byid[c['slot_id']])))
    jobs=[]
    for index,(start,end) in enumerate(windows,1):
        included=[c for c in changes if start<=c['start'] and c['end']<=end]
        jobs.append({'id':f'job-{index:03d}','source_start':start,'source_end':end,'frames':end-start,
            'start_seconds':float(Fraction(start,1)/fps),'duration_seconds':float(Fraction(end-start,1)/fps),
            'selected_slot_ids':[sid for sid in selected if start<=byid[sid]['start'] and byid[sid]['end']<=end],
            'replacements':included,'requirements':requirements})
    return {'mode':mode,'source':src,'jobs':jobs,'changed_slots':len(changes),'note':'Mechanical selection only. Preserve and inspect every non-text visual and unchanged language.'}

def plan_jobs(baseline,request):
    baseline=Path(baseline).resolve();request=Path(request).resolve();b=read(baseline);r=read(request)
    require(r.get('baseline_sha256')==digest(baseline),'Baseline changed or request does not reference the frozen extraction SHA256')
    source=resolve(baseline.parent,b['source']['path']);require(source.is_file(),'Reference source file is unavailable')
    if b['source'].get('sha256'):require(digest(source)==b['source']['sha256'],'Reference source file changed')
    result=compute(b,r)
    config=r.get('audio',{})
    if isinstance(config,dict) and config.get('mode') in ('replace','mix'):require(resolve(request.parent,config['path']).is_file(),'Prepared replacement/mixed audio file is unavailable')
    if r.get('font'):require(resolve(request.parent,r['font']['path']).is_file(),'Provided font file is unavailable')
    result.update(version=1,baseline=str(baseline),baseline_sha256=digest(baseline),request=str(request),request_sha256=digest(request))
    return result

def check_replacement(path,plan):
    path=Path(path).resolve();c=read(path);require(c.get('version')==1,'Unsupported replacement contract version')
    jobs_path=resolve(path.parent,c['jobs_file']);saved=read(jobs_path)
    require(digest(saved['baseline'])==saved['baseline_sha256'] and digest(saved['request'])==saved['request_sha256'],'Frozen baseline/request changed after selection')
    fresh=plan_jobs(saved['baseline'],saved['request']);require(saved==fresh,'Selected jobs were modified; regenerate from the frozen inputs')
    matches=[j for j in saved['jobs'] if j['id']==c['job_id']];require(len(matches)==1,'Unknown selected job')
    job=matches[0];src=saved['source'];media=read(resolve(path.parent,c['reference_media']));window=media.get('window',{})
    baseline=Path(saved['baseline']);source=resolve(baseline.parent,src['path'])
    require(Path(media['path']).resolve()==source,'Prepared source is not the original reference')
    require(window.get('start_frame')==job['source_start'] and window.get('end_frame')==job['source_end'],'Prepared window includes unselected source frames or omits required animation')
    require(media['frames']==job['frames'] and plan['source']['frames']==job['frames'],'Render frame count differs from selected job')
    require(Path(plan['source']['frame_dir']).resolve()==Path(media['frame_dir']).resolve(),'Render frames differ from the inspected job')
    require(Fraction(media['fps'])==Fraction(src['fps'])==Fraction(plan['source']['fps'])==Fraction(plan['output']['fps']),'Text-only replacement must preserve source frame rate')
    require(all(plan['source'][k]==src[k] and media[k]==src[k] and plan['output'][k]==job['requirements'][k] for k in ('width','height')),'Output dimensions differ from source or explicit user override')
    req=job['requirements'];production=plan.get('production',{})
    require(production.get('mode')=='text-replace' and production.get('preserve_nontext_visuals') is True,'Only text replacement is authorized by this contract')
    require(production.get('font_policy')==req['font_policy'],'Font policy differs from user selection')
    audio=plan.get('audio',{})
    require(audio.get('mode')==req['audio'],'Audio policy differs from user selection')
    if req['audio']=='preserve':
        require(Path(audio.get('path','')).resolve()==source,'Preserved audio must come from the original reference')
        require(abs(float(audio.get('start',0))-job['source_start']/float(Fraction(src['fps'])))<1e-8,'Preserved audio starts at the wrong source window')
    elif req['audio'] in ('replace','mix'):
        audio_path=resolve(Path(saved['request']).parent,req['audio_config']['path'])
        require(Path(audio.get('path','')).resolve()==audio_path and audio.get('start',0)==0,'Custom audio differs from the prepared audio selection')
    if req['font_policy']=='provided':require(Path(plan['font']['path']).resolve()==resolve(Path(saved['request']).parent,req['font']['path']),'Render font differs from the provided font')
    motion_path=plan.get('motion_manifest')
    require(motion_path and Path(motion_path).is_file(),'Every replacement export requires a motion inventory')
    require(read(motion_path).get('mode')=='text-replace','Replacement contract forbids scene-remake production mode')
    expected={x['slot_id']:x for x in job['replacements']};actual=plan['replacements']
    require(len({s['id'] for s in actual})==len(actual) and {s['id'] for s in actual}==set(expected),'Render contains extra, missing, or unchanged text slots')
    for slot in actual:
        e=expected[slot['id']]
        require(slot['start']==e['start']-job['source_start'] and slot['end']==e['end']-job['source_start'],'Replacement slot timing differs from selected source interval')
        require(not slot.get('preserve'),'Changed slots cannot be marked wholly preserved')
        require(set(slot.get('preserve_languages',[]))==set(e['preserve_languages']),'Unchanged language preservation differs from baseline')
        for lang in LANGUAGES:
            equal=unicodedata.normalize('NFC',slot.get(lang,''))==unicodedata.normalize('NFC',e[lang]) if saved['mode']=='manual' else textkey(slot.get(lang,''))==textkey(e[lang])
            require(equal,'Replacement text differs from selected edit: '+slot['id']+' '+lang)
    for layer in plan['layers']:
        require(layer['slot'] in expected,'Unselected text layer')
        lang={'zh':'cn','en':'en'}.get(layer['language'])
        require(lang in expected[layer['slot']]['changed_languages'],'Do not redraw unchanged language layers')
    return {'status':'passed','mode':saved['mode'],'job_id':job['id'],'source_start':job['source_start'],'source_end':job['source_end'],
        'changed_slots':len(expected),'mechanical_checks_only':True,'visual_preservation_verified':False}

def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    q=sub.add_parser('digest');q.add_argument('--baseline',required=True)
    q=sub.add_parser('plan');q.add_argument('--baseline',required=True);q.add_argument('--request',required=True);q.add_argument('--output',required=True)
    q=sub.add_parser('check');q.add_argument('--contract',required=True);q.add_argument('--plan',required=True);q.add_argument('--report')
    a=ap.parse_args()
    if a.command=='digest':print(digest(a.baseline))
    elif a.command=='plan':
        require(not Path(a.output).exists(),'Use a new jobs filename; do not overwrite approved selection')
        result=plan_jobs(a.baseline,a.request);write(a.output,result);print(json.dumps({'jobs':len(result['jobs']),'changed_slots':result['changed_slots']},ensure_ascii=False))
    else:
        from video_pipeline import load_plan,validate
        render_plan=load_plan(a.plan)
        require(render_plan.get('replacement_contract')==str(Path(a.contract).resolve()),'Plan does not attach the selected replacement contract')
        validate(render_plan)
        result=check_replacement(a.contract,render_plan)
        if a.report:write(a.report,result)
        print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
