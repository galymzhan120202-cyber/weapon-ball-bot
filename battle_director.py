"""Choose an engaging real simulation before spending time rendering a Short.

These are editing heuristics, not a prediction of views. No HP, winners or
physics are changed here. The manifest makes each selection reproducible.
"""
from battle_sim import simulate_battle, START_HP


def evaluate_battle(battle):
    fps = battle["fps"]
    live_end = battle.get("live_frames") or (battle.get("replay_range") or (battle["finale_start"],))[0]
    frames = battle["frames"][:live_end]
    duration = battle.get("duration_seconds", live_end / fps)
    hits = sorted({i for i, event in battle["hit_frame_flags"].items()
                   if i < live_end and event[5] != "block"}
                  | {i for i in battle["projectile_hit_frames"] if i < live_end})
    times = [i / fps for i in hits]
    gaps = [b - a for a, b in zip([0.0] + times, times + [duration])]
    first_hit = times[0] if times else duration
    longest_gap = max(gaps, default=duration)
    winner_hp = max(0.0, frames[-1]["hp"][battle["winner_idx"]])
    lead_changes, leader = 0, None
    for frame in frames[::max(1, fps // 4)]:
        order = sorted(range(battle["n_fighters"]), key=lambda i: frame["hp"][i], reverse=True)
        if frame["hp"][order[0]] - frame["hp"][order[1]] < START_HP * .08:
            continue
        if leader is not None and leader != order[0]:
            lead_changes += 1
        leader = order[0]
    finish = battle.get("finish_reason", "ko")
    score = 100.0
    score -= max(0, first_hit - 1.0) * 12
    score -= max(0, longest_gap - 2.0) * 7
    score -= abs(duration - 17) * 1.2
    score -= max(0, battle.get("min_seconds_target", 8) - duration) * 8
    score += min(12, len(hits) / max(1, duration) * 5)
    score += min(3, lead_changes) * 3
    score += max(0, 1 - winner_hp / START_HP) * 8
    score -= 22 if finish == "timeout" else 9 if finish == "double_ko" else 0
    if not hits:
        score -= 80
    return {
        "score": round(score, 3), "duration": round(duration, 3),
        "first_impact": round(first_hit, 3), "longest_quiet_gap": round(longest_gap, 3),
        "impact_count": len(hits), "lead_changes": lead_changes,
        "winner_hp": round(winner_hp, 2), "finish": finish,
    }


def select_battle(*, seed, candidates=6, recent_matchups=(), **simulation_options):
    """Choose the highest scoring fresh matchup from a bounded deterministic batch."""
    if not isinstance(candidates, int) or not 1 <= candidates <= 24:
        raise ValueError("candidates must be between 1 and 24")
    best = None
    best_rank = None
    records = []
    recent = {frozenset(matchup) for matchup in recent_matchups}
    for i in range(candidates):
        candidate_seed = (int(seed) + i * 104729) % (2**31 - 1)
        battle = simulate_battle(seed=candidate_seed, **simulation_options)
        metrics = evaluate_battle(battle)
        repeated = frozenset(f["name"] for f in battle["fighters"]) in recent
        records.append({"seed": candidate_seed, "repeated": repeated, **metrics})
        rank = (not repeated, metrics["score"])
        if best is None or rank > best_rank:
            best, best_rank = battle, rank
            best_metrics = metrics
    best["selection"] = {"base_seed": seed, "candidates": records, "chosen": best_metrics}
    return best


def battle_manifest(battle):
    """A compact, credential-free record to compare with Studio retention later."""
    return {
        "seed": battle["seed"], "fighters": [f["name"] for f in battle["fighters"]],
        "winner": None if battle.get("is_double_ko") else battle["winner_name"], "fps": battle["fps"],
        "metrics": evaluate_battle(battle), "selection": battle.get("selection"),
        "diagnostics": battle.get("diagnostics", {}),
    }
