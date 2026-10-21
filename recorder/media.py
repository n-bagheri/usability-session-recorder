"""Saved-video decoding only. OBS remains the sole recording engine."""
import bisect
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def run(args, timeout=180):
    executable = shutil.which(args[0])
    if not executable:
        raise RuntimeError(f'{args[0]} is missing. Install FFmpeg with ffprobe and restart Recorder.')
    result = subprocess.run([executable,*args[1:]],capture_output=True,timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-1500:])
    return result.stdout


class Video:
    def __init__(self, folder):
        self.folder = Path(folder)
        meta = json.loads((self.folder/'metadata.json').read_text(encoding='utf-8'))
        filename = meta.get('video_file')
        if not filename or Path(filename).name != filename:
            raise ValueError('No finalized session video_file in metadata. Recover the OBS video first.')
        self.path = self.folder/filename
        stat = self.path.stat()
        self.signature = {'file':filename,'size':stat.st_size,'mtime_ns':stat.st_mtime_ns}
        self.cache = self.folder/'review_cache'
        self.cache.mkdir(exist_ok=True)
        cached = self.cache/'video_index.json'
        if cached.exists():
            info = json.loads(cached.read_text())
        else:
            info = {}
        if info.get('signature') != self.signature:
            data = json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
                'stream=width,height,avg_frame_rate:frame=best_effort_timestamp_time,pkt_duration_time:format=duration',
                '-show_frames','-of','json',str(self.path)]))
            stream = data['streams'][0]
            raw = [float(f['best_effort_timestamp_time']) for f in data['frames'] if 'best_effort_timestamp_time' in f]
            if not raw:
                raise ValueError('Saved video contains no timestamped frames')
            first = raw[0]
            pts = [t-first for t in raw]
            num,den = map(float,stream['avg_frame_rate'].split('/'))
            fps = num/den if den and num else 30
            info = {'signature':self.signature,'size':[stream['width'],stream['height']],
                    'first_pts_seconds':first,'pts':pts,'fps':fps,
                    'duration':max(float(data.get('format',{}).get('duration',0)),pts[-1]+1/fps),
                    'large_frame_gaps':sum(b-a > 1.5/fps for a,b in zip(pts,pts[1:])),
                    'gap_warning':'PTS gaps can be dropped frames or variable frame rate; no cause inferred'}
            cached.write_text(json.dumps(info),encoding='utf-8')
        if 'sha256' not in info:
            with self.path.open('rb') as video_file:info['sha256']=hashlib.file_digest(video_file,'sha256').hexdigest()
            cached.write_text(json.dumps(info),encoding='utf-8')
        self.info = info
        self.pts = info['pts']
        self.fingerprint = info['sha256']

    def nearest(self, seconds):
        i = bisect.bisect_left(self.pts,max(0,seconds))
        i = min(i,len(self.pts)-1)
        if i and abs(self.pts[i-1]-seconds) <= abs(self.pts[i]-seconds):
            i -= 1
        return i

    def frame(self, seconds):
        """Exact decoded frame index from actual PTS; cache never uses nominal FPS as a clock."""
        index = self.nearest(seconds)
        path = self.cache/f'{self.fingerprint}-{index:08d}.png'
        if not path.exists():
            # Select exact n, decoding from the beginning. Slower than approximate seek,
            # but deterministic for VFR, B-frames and missing frames. All work runs off Tk.
            image = run(['ffmpeg','-v','error','-i',str(self.path),'-vf',f'select=eq(n\\,{index})',
                         '-vsync','0','-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'])
            if not image:
                raise ValueError('Could not decode selected saved-video frame')
            path.write_bytes(image)
        return {'path':str(path),'index':index,'seconds':self.pts[index],
                'video_fingerprint':self.fingerprint,'size':self.info['size']}
