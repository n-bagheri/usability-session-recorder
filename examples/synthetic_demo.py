"""Generate an explicitly synthetic saved-video session and per-state exports.

Run from repository root: python -m examples.synthetic_demo
Requires FFmpeg/ffprobe. Nothing here accesses MapGen or captures a real screen.
"""
import json
import shutil
from pathlib import Path
from PIL import Image,ImageDraw
from recorder.media import run
from recorder.obs_geometry import compute_mapping
from recorder.research import ResearchSession
from recorder.review import save_json,write_review
from recorder.targeting import title_digest


def create(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    frames=folder/'synthetic_frames';frames.mkdir(exist_ok=True)
    identity={'hwnd':42,'pid':7,'process_started':123,'class_name':'Chrome_WidgetWin_1','executable':'chrome.exe'}
    t={'sourceWidth':320,'sourceHeight':240,'positionX':40,'positionY':30,'scaleX':1,'scaleY':1,'alignment':5,'boundsType':'OBS_BOUNDS_NONE'}
    mapping=compute_mapping([0,0,320,240],[0,20,320,220],t,[400,300],[400,300])
    clicks=[(.6,50,60),(1.2,260,170),(2.6,80,120),(3.2,250,80)]
    for n in range(20):
        image=Image.new('RGB',(400,300),'black');draw=ImageDraw.Draw(image)
        draw.rectangle((40,30,359,269),fill='#eeeeee');draw.rectangle((40,30,359,49),fill='#555555')
        draw.text((50,33),'SYNTHETIC Chrome / no real data',fill='white')
        state='HOME' if n<10 else 'EDITOR'
        draw.text((55,60),'SYNTHETIC '+state,fill='black')
        if n<10:
            draw.rectangle((55,85,125,250),fill='#4589bd');draw.rectangle((145,100,330,230),fill='#abd8a5')
        else:
            draw.rectangle((55,85,105,250),fill='#a94646');draw.polygon([(130,230),(170,100),(320,140),(280,245)],fill='#76b6a1')
        for seconds,x,y in clicks:
            if int(seconds*5)==n:draw.ellipse((40+x-4,50+y-4,40+x+4,50+y+4),fill='yellow')
        image.save(frames/f'{n:03d}.png')
    run(['ffmpeg','-y','-v','error','-framerate','5','-i',str(frames/'%03d.png'),'-c:v','ffv1',str(folder/'video.mkv')])
    c={'identity':identity,'method':'automatic_uia_obs','dpi':96,'insets':[0,20,0,0],'reference_size':[320,220],'maximized':False,'title_digest':title_digest('SYNTHETIC')}
    save_json(folder/'metadata.json',{'synthetic':True,'video_file':'video.mkv','target_calibration':c,'capture_rect':[0,0,320,240]})
    save_json(folder/'sync.json',{'origin_ns':1_000_000_000,'manual_correction_ms':0,'samples':[{'origin_ns':1_000_000_000,'half_rtt_ns':0}],
                                'note':'SYNTHETIC known clock, not an OBS or Windows accuracy measurement'})
    events=[]
    for seconds,x,y in clicks:
        for kind,pressed,delta in [('move',None,-.03),('click',True,0),('click',False,.05)]:
            s={'identity':identity,'client_rect':[0,0,320,240],'dpi':96,'stable':True,'visible':True,'minimized':False,'cloaked':False,
               'maximized':False,'hit_root':42,'capture_root':0,'possible_occluders':[],'foreground_root':42,
               'viewport':{'rect':[0,20,320,220]},'capture_mapping':mapping,'title_digest':title_digest('SYNTHETIC')}
            e={'event_id':str(len(events)+1),'type':kind,'x':x,'y':y+20,'monotonic_ns':round((1+seconds+delta)*1e9),'target_observation':s,'button':'left'}
            if pressed is not None:e['pressed']=pressed
            events.append(e)
    with (folder/'events.jsonl').open('w',encoding='utf-8') as f:
        for e in events:f.write(json.dumps(e)+'\n')
    data=ResearchSession(folder)
    data.review['segments']=[{'id':'home','view':'Home','state':'stable home','start':0,'end':2,'stable':True,'reference_seconds':.4},
                             {'id':'editor','view':'Editor','state':'stable editor','start':2,'end':4,'stable':True,'reference_seconds':2.4}]
    write_review(folder,data.review,4)
    report=data.export(smoothed=True)
    shutil.rmtree(frames)
    return report


if __name__=='__main__':
    result=create(Path('sessions')/'synthetic-demo')
    print('SYNTHETIC ONLY: outputs in sessions/synthetic-demo/research_analysis')
    print('Output base:',result['output_base'])
    for s in result['segments']:print(s['view'],s['outputs'])
