import argparse
import json
import subprocess
from pathlib import Path


def sh(cmd):
    print(' '.join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--video', required=True)
    p.add_argument('--manifest', required=True)
    p.add_argument('--voice-dir', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--srt')
    args = p.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    segments = manifest['segments']
    voice_dir = Path(args.voice_dir)

    cmd = ['ffmpeg', '-y', '-i', args.video]
    for seg in segments:
        cmd += ['-i', str(voice_dir / f"{seg['id']}.mp3")]

    srt_input_index = None
    if args.srt:
        srt_input_index = 1 + len(segments)
        cmd += ['-i', args.srt]

    filters = []
    narration_labels = []
    for idx, seg in enumerate(segments, start=1):
        delay = max(0, int(round(float(seg['start']) * 1000)))
        label = f'n{idx}'
        filters.append(f'[{idx}:a]aresample=48000,asetpts=PTS-STARTPTS,adelay={delay}|{delay}[{label}]')
        narration_labels.append(f'[{label}]')

    if len(narration_labels) == 1:
        filters.append(f'{narration_labels[0]}anull[narr]')
    else:
        filters.append(''.join(narration_labels) + f'amix=inputs={len(narration_labels)}:normalize=0:duration=longest[narr]')

    # Pad narration with silence so sidechain processing follows the full source-video duration.
    # Keep source speech audible quietly under Russian narration and restore it smoothly in gaps.
    filters += [
        '[narr]apad[narrpad]',
        '[0:a:0]aresample=48000,asetpts=PTS-STARTPTS[orig]',
        '[orig][narrpad]sidechaincompress=threshold=0.018:ratio=12:attack=80:release=380:makeup=1[ducked]',
        '[ducked][narrpad]amix=inputs=2:normalize=0:duration=first:weights=0.80 1.00[mixpre]',
        '[mixpre]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[ru]'
    ]

    cmd += ['-filter_complex', ';'.join(filters)]
    cmd += ['-map', '0:v:0', '-map', '[ru]', '-map', '0:a:0']
    if srt_input_index is not None:
        cmd += ['-map', f'{srt_input_index}:s:0']

    cmd += [
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k',
        '-metadata:s:a:0', 'language=rus', '-metadata:s:a:0', 'title=Русская озвучка',
        '-metadata:s:a:1', 'language=eng', '-metadata:s:a:1', 'title=English Original',
        '-disposition:a:0', 'default', '-disposition:a:1', '0'
    ]
    if srt_input_index is not None:
        cmd += ['-c:s', 'mov_text', '-metadata:s:s:0', 'language=rus', '-metadata:s:s:0', 'title=Русские субтитры']

    cmd += ['-movflags', '+faststart', '-shortest', args.output]
    sh(cmd)


if __name__ == '__main__':
    main()
