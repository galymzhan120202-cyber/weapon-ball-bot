import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs

from battle_sim import simulate_battle


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Unit tests never load account credentials from a developer's .env.
        with patch('dotenv.load_dotenv'):
            cls.video = importlib.import_module('video_gen')

    def test_metadata_keeps_outcome_unspoiled_and_links_the_matchup(self):
        with patch.object(self.video, 'PLAY_URL', 'https://example.test/arena/'), patch.object(self.video, 'FUND_URL', ''):
            title, description, tags = self.video.build_title_and_description(['War Axe', 'Dual Daggers'], 'War Axe')
        self.assertLessEqual(len(title), 95)
        self.assertNotIn('Winner:', description)
        self.assertNotIn('copyright risk', description)
        url = next(line.split(': ', 1)[1] for line in description.splitlines() if 'Try this matchup' in line)
        self.assertEqual(parse_qs(urlparse(url).query), {'weapons':['war_axe,dual_daggers'],'n':['2']})
        self.assertIn('physics simulation', tags)
        self.assertEqual(self.video._weapon_set_from_title('War Axe vs Dual Daggers'),frozenset(['War Axe','Dual Daggers']))

    def test_offline_failure_never_contacts_accounts_or_sends_notifications(self):
        battle=simulate_battle(1080,1920,8,fps=30,max_seconds=28,min_seconds=8,n_fighters=2)
        battle['selection']={'chosen':{'score':90}}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(self.video,'base_dir',directory), \
             patch.object(self.video,'ensure_directories_exist'), \
             patch.object(self.video,'cleanup_temp_files'), \
             patch.object(self.video,'select_battle',return_value=battle), \
             patch.object(self.video,'generate_thumbnail'), \
             patch.object(self.video,'build_battle_clip',side_effect=RuntimeError('test render failure')), \
             patch.object(self.video,'get_recent_matchups') as history, \
             patch.object(self.video,'fetch_openverse_music') as music, \
             patch.object(self.video,'send_telegram') as telegram, \
             patch.object(self.video,'upload_to_youtube') as upload:
            with self.assertRaisesRegex(RuntimeError,'test render failure'):
                self.video.generate_video(skip_upload=True,offline=True,seed=8)
            for network in (history,music,telegram,upload):
                network.assert_not_called()
            manifest=json.loads(Path(directory,'battle_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['seed'],8)
            self.assertIn('metrics',manifest)

    def test_offline_upload_is_rejected(self):
        with self.assertRaises(ValueError):
            self.video.generate_video(offline=True)


if __name__ == '__main__':
    unittest.main()
