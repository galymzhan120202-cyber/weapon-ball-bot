import math
import unittest

from battle_sim import simulate_battle, START_HP, WEAPON_POOL, build_battle_clip, build_sfx_array, INTRO_SECONDS, COLD_OPEN_SECONDS
from battle_director import evaluate_battle, select_battle, battle_manifest


class BattleTests(unittest.TestCase):
    def simulate(self, seed=42, **options):
        return simulate_battle(1080, 1920, seed, **{'fps': 30, 'max_seconds': 28, 'min_seconds': 13, **options})

    def test_seed_reproduces_full_battle(self):
        self.assertEqual(self.simulate(), self.simulate())

    def test_output_fps_does_not_change_physics(self):
        battles = [self.simulate(fps=fps) for fps in (24, 30, 50, 60)]
        outcomes = [(b['winner_name'], b['duration_seconds'], b['frames'][b['live_frames']-1]['hp']) for b in battles]
        for outcome in outcomes[1:]:
            self.assertEqual(outcome, outcomes[0])
        for battle in battles:
            self.assertLessEqual(abs(battle['live_frames']/battle['fps']-battle['duration_seconds']), 1/battle['fps'])

    def test_all_weapons_finish_with_valid_state_and_no_ghost_colliders(self):
        for i, weapon in enumerate(WEAPON_POOL):
            with self.subTest(weapon=weapon['kind']):
                battle = self.simulate(seed=100+i, weapons=[weapon['kind'], WEAPON_POOL[(i+7)%len(WEAPON_POOL)]['kind']])
                self.assertEqual(battle['diagnostics']['orphan_shapes'], 0)
                self.assertLessEqual(battle['diagnostics']['peak_speed'], battle['diagnostics']['speed_limit']+.001)
                self.assertIn(battle['winner_idx'], (0, 1))
                previous_hp = [START_HP]*2
                for frame in battle['frames'][:battle['live_frames']]:
                    for index, hp in enumerate(frame['hp']):
                        self.assertTrue(0 <= hp <= previous_hp[index])
                        self.assertEqual(frame['alive'][index], hp > 0)
                        self.assertTrue(all(math.isfinite(v) for v in frame['pos'][index]))
                    previous_hp = frame['hp']
                if battle['finish_reason'] != 'timeout':
                    self.assertEqual(max(k[0] for k in battle['real_ko_events']), battle['live_frames']-1)

    def test_replay_preserves_arena_and_finale_is_true_terminal_state(self):
        battle = self.simulate(11, n_fighters=4)
        if battle['replay_range']:
            start, end = battle['replay_range']
            self.assertTrue(all('arena' in frame for frame in battle['frames'][start:end]))
            replay_kos = [event[1] for event in battle['ko_events'] if start <= event[0] < end]
            self.assertEqual(len(replay_kos), len(set(replay_kos)), 'slow motion must not trigger the same knockout twice')
        terminal = battle['frames'][battle['live_frames']-1]
        self.assertEqual(battle['frames'][-1], terminal)
        for event_map in ('hit_frame_flags', 'projectile_hit_frames', 'muzzle_flash_frames', 'wall_hit_frames'):
            self.assertTrue(all(0 <= frame < len(battle['frames']) for frame in battle[event_map]))

    def test_director_prefers_fresh_matchup_and_records_selection(self):
        base = self.simulate(42, min_seconds=8)
        recent = [frozenset(f['name'] for f in base['fighters'])]
        battle = select_battle(seed=42, candidates=4, recent_matchups=recent, w=1080, h=1920, fps=30, max_seconds=28, min_seconds=8)
        self.assertNotIn(frozenset(f['name'] for f in battle['fighters']), recent)
        records = battle['selection']['candidates']
        self.assertEqual(len(records), 4)
        self.assertEqual(evaluate_battle(battle)['score'], max(r['score'] for r in records if not r['repeated']))
        self.assertEqual(battle_manifest(battle)['seed'],battle['seed'])

    def test_render_hook_replay_finale_and_audio_timeline(self):
        import numpy as np
        battle = self.simulate(42)
        clip = build_battle_clip(battle)
        try:
            for timestamp in (0, .45, COLD_OPEN_SECONDS+.2, COLD_OPEN_SECONDS+INTRO_SECONDS+1, clip.duration-.4):
                frame = clip.get_frame(timestamp)
                self.assertEqual(frame.shape,(1920,1080,3))
                self.assertEqual(frame.dtype,np.uint8)
            self.assertFalse(np.array_equal(clip.get_frame(.2),clip.get_frame(.6)))
            audio, rate = build_sfx_array(battle)
            self.assertEqual(audio.shape[1],2)
            self.assertTrue(np.isfinite(audio).all())
            self.assertLessEqual(np.max(np.abs(audio)),.851)
            self.assertGreaterEqual(len(audio)/rate,clip.duration)
            self.assertLessEqual(len(audio)/rate,clip.duration+1.001)
        finally:
            clip.close()

    def test_invalid_inputs_are_rejected(self):
        for options in ({'fps':0},{'fps':121},{'n_fighters':1},{'max_seconds':0},{'max_seconds':.001,'min_seconds':0},{'weapons':['sword','missing']}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.simulate(**options)


if __name__ == '__main__':
    unittest.main()
