#!/usr/bin/env python3
"""Check the delivered MP4 using FFprobe and FFmpeg."""

import json
from pathlib import Path
import subprocess

from build_video import ROOT, ffmpeg_binary


def main():
    path = ROOT / 'artifacts/video.mp4'
    probe = subprocess.check_output([
        str(ffmpeg_binary('ffprobe')), '-v', 'error', '-show_entries',
        'format=duration,size:stream=codec_name,codec_type,pix_fmt,width,height,avg_frame_rate,sample_rate,channels,nb_frames',
        '-of', 'json', str(path)], text=True)
    info = json.loads(probe)
    video = next(item for item in info['streams'] if item['codec_type'] == 'video')
    audio = next(item for item in info['streams'] if item['codec_type'] == 'audio')
    assert video['codec_name'] == 'h264'
    assert video['pix_fmt'] == 'yuv420p'
    assert (video['width'], video['height'], video['avg_frame_rate']) == (960, 540, '30/1')
    assert int(video['nb_frames']) == 900
    assert audio['codec_name'] == 'aac'
    assert (audio['sample_rate'], audio['channels']) == ('22050', 1)
    assert abs(float(info['format']['duration']) - 30) < .01
    assert path.stat().st_size < 64 * 1024 * 1024
    raw = path.read_bytes()
    assert 0 < raw.find(b'moov') < raw.find(b'mdat')
    subprocess.run([str(ffmpeg_binary('ffmpeg')), '-v', 'error', '-i', str(path),
                    '-f', 'null', '-'], check=True)
    print(json.dumps({'duration': info['format']['duration'],
                      'dimensions': '960x540', 'frames': video['nb_frames'],
                      'video': f"{video['codec_name']} {video['pix_fmt']}",
                      'audio': f"{audio['codec_name']} mono {audio['sample_rate']}Hz",
                      'bytes': path.stat().st_size, 'front_moov': True}, indent=2))


if __name__ == '__main__':
    main()
