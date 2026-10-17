"""Render a local review clip. No accounts, network, uploads or notifications."""
import argparse
import json
from pathlib import Path

from moviepy import AudioArrayClip
from battle_sim import build_battle_clip, build_sfx_array
from battle_director import select_battle, battle_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--candidates', type=int, default=6)
    parser.add_argument('--fighters', type=int, choices=[2, 3, 4], default=2)
    parser.add_argument('--fps', type=int, default=30)
    parser.add_argument('--output', type=Path, default=Path('preview.mp4'))
    args = parser.parse_args()
    battle = select_battle(seed=args.seed, candidates=args.candidates, w=1080, h=1920,
                           fps=args.fps, max_seconds=28, min_seconds=8, n_fighters=args.fighters)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix('.json').write_text(json.dumps(battle_manifest(battle), indent=2), encoding='utf-8')
    clip = build_battle_clip(battle)
    samples, rate = build_sfx_array(battle)
    audio = AudioArrayClip(samples, fps=rate).subclipped(0, clip.duration)
    final = clip.with_audio(audio).resized(width=540)
    try:
        final.write_videofile(str(args.output), fps=args.fps, codec='libx264', audio_codec='aac',
                              preset='ultrafast', threads=2, logger=None)
    finally:
        final.close(); audio.close(); clip.close()
    print(json.dumps({'output': str(args.output), **battle_manifest(battle)['metrics']}, indent=2))


if __name__ == '__main__':
    main()
