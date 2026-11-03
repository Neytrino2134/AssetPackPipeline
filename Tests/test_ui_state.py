import types
import unittest
from pathlib import Path

from asset_pack_pipeline import ui_state


class Var:
    def __init__(self, value):
        self.value, self.writes = value, 0

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        self.writes += 1


class Tabs:
    def __init__(self):
        self.current = 0

    def index(self, what):
        return 5 if what == 'end' else self.current

    def select(self, index):
        self.current = index


def window(profile='C:/p/active_profile.json'):
    w = types.SimpleNamespace(
        mode=Var('Быстрый старт'), guide_step=0, guide_variants=Var('LOD + MID / Nanite'),
        guide_lod=Var('0'), guide_finalize=Var(True),
        guide_renders={'overview': Var(True), 'MID': Var(False)}, guide_view_modes={'wireframe': Var(False)},
        profile_path=Path(profile), variables={'source_root': Var('D:/A'), 'pack_id': Var('Pack')},
        tabs=Tabs(), switched=0)
    w.switch_mode = lambda: setattr(w, 'switched', w.switched+1)
    return w


class UiStateTest(unittest.TestCase):
    def state(self, **form):
        return {'schema': 1, 'mode': 'Мастер', 'guide_step': 2, 'tab': 3,
                'guide': {'lod': '2', 'renders': {'MID': True, 'unknown': True}},
                'profile_path': str(Path('C:/p/active_profile.json')), 'form': form}

    def test_restores_mode_step_tab_and_guide(self):
        w = window()
        ui_state.restore(w, self.state())
        self.assertEqual((w.mode.get(), w.guide_step, w.tabs.current, w.switched), ('Мастер', 2, 3, 1))
        self.assertEqual((w.guide_lod.get(), w.guide_renders['MID'].get()), ('2', True))

    def test_unchanged_form_values_are_not_rewritten(self):
        w = window()
        ui_state.restore(w, self.state(source_root='D:/A', pack_id='Other'))
        self.assertEqual(w.variables['source_root'].writes, 0)
        self.assertEqual(w.variables['pack_id'].get(), 'Other')

    def test_form_draft_ignored_for_another_profile(self):
        w = window('C:/p/other.json')
        ui_state.restore(w, self.state(pack_id='Other'))
        self.assertEqual(w.variables['pack_id'].get(), 'Pack')

    def test_invalid_mode_and_tab_ignored(self):
        w = window()
        state = dict(self.state(), mode='Hacker', tab=99, guide_step=9)
        ui_state.restore(w, state)
        self.assertEqual((w.mode.get(), w.tabs.current, w.guide_step), ('Быстрый старт', 0, 0))


if __name__ == '__main__':
    unittest.main()
