"""Run equal-exposure weapon duels and save an offline balance report."""
import argparse
import json
import random
import statistics
from pathlib import Path

from battle_sim import WEAPON_POOL, simulate_battle


def analyze(rounds=24, seed=2026):
    if not 1 <= rounds <= 1000:
        raise ValueError('rounds must be between 1 and 1000')
    rng = random.Random(seed)
    kinds = [w['kind'] for w in WEAPON_POOL]
    stats = {kind: {'matches': 0, 'wins': 0, 'draws': 0} for kind in kinds}
    durations = []
    timeouts = 0
    for _ in range(rounds):
        order = rng.sample(kinds, len(kinds))
        for index in range(0, len(order), 2):
            pair = order[index:index+2]
            battle = simulate_battle(1080,1920,rng.randrange(2**31),fps=24,max_seconds=28,min_seconds=8,weapons=pair)
            durations.append(battle['duration_seconds'])
            timeouts += battle['finish_reason'] == 'timeout'
            for kind in pair:
                stats[kind]['matches'] += 1
                if battle['is_double_ko']:
                    stats[kind]['draws'] += 1
            if not battle['is_double_ko']:
                stats[pair[battle['winner_idx']]]['wins'] += 1
    for values in stats.values():
        values['score_rate'] = round((values['wins']+.5*values['draws'])/values['matches'],3)
    return {'seed': seed, 'rounds': rounds, 'duels': len(durations),
            'median_seconds': round(statistics.median(durations),3), 'timeouts': timeouts,
            'weapons': dict(sorted(stats.items(),key=lambda item:item[1]['score_rate'],reverse=True)),
            'note': 'Small samples are diagnostic, not proof of equal win rates. Draws count as half a point.'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds',type=int,default=24)
    parser.add_argument('--seed',type=int,default=2026)
    parser.add_argument('--output',type=Path,default=Path('balance_report.json'))
    args=parser.parse_args()
    report=analyze(args.rounds,args.seed)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
