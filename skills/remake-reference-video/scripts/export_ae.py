#!/usr/bin/env python3
"""Export a native AE text-layer builder from the same external-render plan."""
from pathlib import Path
import argparse,json,shutil
from video_pipeline import load_plan,validate,run,audio_arguments,audio_settings
from font_setup import verify_bytes

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--plan',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    p=load_plan(a.plan);validate(p);dest=Path(a.output).resolve()
    if dest.exists() and any(dest.iterdir()):raise ValueError('Use a new AE export directory')
    dest.mkdir(parents=True,exist_ok=True)
    audio_inputs,audio_options=audio_arguments(p)
    run(['ffmpeg','-hide_banner','-loglevel','error','-framerate',str(p['source']['fps']),'-i',str(Path(p['plate']['frame_dir'])/'f_%06d.png')]+audio_inputs+audio_options+['-c:v','libx264','-preset','fast','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',dest/'Reference_Motion_Plate.mp4'])
    shutil.copy2(p['font']['path'],dest/Path(p['font']['path']).name)
    try:
        verify_bytes(Path(p['font']['path']).read_bytes())
    except ValueError:
        pass  # Custom fonts keep their own licensing and provenance.
    else:
        notices=Path(__file__).resolve().parents[1]/'assets/fonts'
        for name in ['OFL.txt','FONT-NOTICE.txt']:
            shutil.copy2(notices/name,dest/name)
    data={'source':{k:p['source'][k] for k in ['width','height','fps','frames']},'output':p['output'],'font':p['font']['postscript'],'layers':p['layers'],'audio_enabled':audio_settings(p)['enabled']}
    script=r'''/* ExtendScript ES3. Generated builder; not evidence of AE execution. */
(function () {
var D=__DATA__;
var base=new File($.fileName).parent, undo=false;
function rate(value) {var s=String(value).split('/');return Number(s[0])/(s.length>1?Number(s[1]):1);}
var fps=rate(D.source.fps),duration=D.source.frames/fps;
var w=D.output.width,h=D.output.height;
var factor=Math.min(w/D.source.width,h/D.source.height);
var dx=(w-D.source.width*factor)/2,dy=(h-D.source.height*factor)/2;
function tr(layer,name) {return layer.property('ADBE Transform Group').property(name);}
function keys(property,times,values) {
    var same=true,i;
    for(i=1;i<values.length;i++){if(String(values[i])!==String(values[0])){same=false;break;}}
    if(same){property.setValue(values[0]);return;}
    property.setValuesAtTimes(times,values);
    for(i=1;i<=property.numKeys;i++){property.setInterpolationTypeAtKey(i,KeyframeInterpolationType.LINEAR,KeyframeInterpolationType.LINEAR);}
}
function log(message) {
    var f=new File(base.fsName+'/AE_build_status.txt');f.encoding='UTF-8';
    if(f.open('w')){f.write(message);f.close();}$.writeln(message);
}
try {
    var file=new File(base.fsName+'/Reference_Motion_Plate.mp4');
    if(!file.exists){throw new Error('Missing Reference_Motion_Plate.mp4; extract the entire package.');}
    if(app.fonts && typeof app.fonts.getFontsByPostScriptName==='function'){
        if(app.fonts.getFontsByPostScriptName(D.font).length===0){throw new Error('Install the bundled font, then reopen AE.');}
    }
    var project=app.project || app.newProject();
    app.beginUndoGroup('Reference video copy replacement');undo=true;
    var folder=project.items.addFolder('Reference video - editable copy');
    var comp=project.items.addComp('Text replacement',w,h,1,duration,fps);comp.parentFolder=folder;
    var bgColor=D.output.background;
    comp.bgColor=[bgColor[0]/255,bgColor[1]/255,bgColor[2]/255];
    var solid=comp.layers.addSolid(comp.bgColor,'Frame background',w,h,1,duration);solid.locked=true;
    var item=project.importFile(new ImportOptions(file));item.parentFolder=folder;
    var plate=comp.layers.add(item);plate.audioEnabled=D.audio_enabled;plate.outPoint=duration;
    tr(plate,'ADBE Position').setValue([w/2,h/2]);tr(plate,'ADBE Scale').setValue([factor*100,factor*100]);plate.locked=true;
    var i,j,l,layer,prop,doc,times,pos,scale,rot,opacity,blurs,k,hasBlur,fx;
    for(i=0;i<D.layers.length;i++){
        l=D.layers[i];layer=comp.layers.addText(l.text);layer.name=l.id+' | '+l.text;
        layer.inPoint=l['in']/fps;layer.outPoint=l.out/fps;
        prop=layer.property('ADBE Text Properties').property('ADBE Text Document');doc=prop.value;
        doc.font=D.font;doc.fontSize=l.font_size*factor;doc.tracking=l.tracking/l.font_size*1000;
        doc.justification=ParagraphJustification.CENTER_JUSTIFY;doc.applyFill=true;doc.applyStroke=false;
        doc.fillColor=[l.fill[0]/255,l.fill[1]/255,l.fill[2]/255];prop.setValue(doc);
        if(prop.value.font!==D.font){throw new Error('Font substitution detected: '+D.font);}
        tr(layer,'ADBE Anchor Point').expression='var r=sourceRectAtTime(time,false); [r.left+r.width/2,r.top+r.height/2];';
        times=[];pos=[];scale=[];rot=[];opacity=[];blurs=[];hasBlur=false;
        for(j=0;j<l.keys.length;j++){
            k=l.keys[j];times.push(k[0]/fps);pos.push([k[1]*factor+dx,k[2]*factor+dy]);
            scale.push([k[3]*100,k[4]*100]);rot.push(k[5]);opacity.push(k[6]*100);blurs.push(k[7]*factor);
            if(k[7]>.01){hasBlur=true;}
        }
        keys(tr(layer,'ADBE Position'),times,pos);keys(tr(layer,'ADBE Scale'),times,scale);
        keys(tr(layer,'ADBE Rotate Z'),times,rot);keys(tr(layer,'ADBE Opacity'),times,opacity);
        if(hasBlur && layer.property('ADBE Effect Parade').canAddProperty('ADBE Gaussian Blur 2')){
            fx=layer.property('ADBE Effect Parade').addProperty('ADBE Gaussian Blur 2');keys(fx.property('ADBE Gaussian Blur 2-0001'),times,blurs);
        }
    }
    comp.openInViewer();log('Composition built. Preview and save a new .aep. Audio follows the approved plan. This is a source plate and editable replacement text, not the original author project.');
} catch(error) {log('Build failed: '+error.toString()+'; line '+error.line);throw error;}
finally {if(undo){app.endUndoGroup();}}
})();
'''.replace('__DATA__',json.dumps(data,ensure_ascii=False,separators=(',',':')))
    (dest/'Run_in_After_Effects.jsx').write_text(script,encoding='utf-8')
    (dest/'制作状态.json').write_text(json.dumps({'native_ae_run_verified':False,'native_ae_render_verified':False,'note':'Install the bundled font and run JSX in AE; inspect and save a new project. Script generation is not AE execution.'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(str(dest))

if __name__=='__main__':main()
