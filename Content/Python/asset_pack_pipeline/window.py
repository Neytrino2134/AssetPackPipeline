"""Modeless profile editor, pumped by Slate on the editor thread.

Uses Tk shipped with Epic's Windows Python runtime. No pip dependencies or
background UObject calls. Closing this window never cancels a running job.
"""
import copy
import json
import math
import os
import re
import sys
import time
import uuid
from pathlib import Path

_window = None


def profile_from_fields(base, values):
    """Merge editable settings without discarding future/unknown profile keys."""
    profile = copy.deepcopy(base)
    profile.update(schema_version=1, pack_id=values['pack_id'].strip(),
                   source_root=values['source_root'].strip(),
                   source_format=values['source_format'],
                   destination_root=values['destination_root'].strip().rstrip('/'),
                   mesh_info=values['mesh_info'].strip(),
                   texture_directory=values['texture_directory'].strip(),
                   collision=values['collision'],
                   remove_degenerates=bool(values['remove_degenerates']))
    sizes = [float(x) for x in re.split(r'[,;\s]+', values['lod_screen_sizes'].strip()) if x]
    if not sizes or any(not math.isfinite(x) or not 0 < x <= 1 for x in sizes):
        raise ValueError('Пороги LOD должны быть числами в диапазоне (0; 1].')
    if any(a <= b for a, b in zip(sizes, sizes[1:])):
        raise ValueError('Пороги LOD должны строго убывать.')
    roughness = float(values['roughness'])
    if not math.isfinite(roughness) or not 0 <= roughness <= 1:
        raise ValueError('Roughness должен быть в диапазоне 0–1.')
    if not profile['source_root']:
        raise ValueError('Выберите папку с экспортами.')
    profile.update(lod_screen_sizes=sizes, roughness=roughness)
    if 'convex_hull_count' in values:
        profile['convex_collision']={'hull_count':int(values['convex_hull_count']),
            'max_hull_verts':int(values['convex_max_hull_verts']),'precision':int(values['convex_precision'])}
    for key in ('nanite_enabled', 'nanite_source'):
        if key in values:
            profile[key] = values[key]
    if 'incremental' in values:
        profile['incremental'] = bool(values['incremental'])
    if 'validation_policy' in values:
        profile['validation_policy'] = values['validation_policy']
    if 'mesh_subdirectory' in values:
        profile['mesh_subdirectory'] = values['mesh_subdirectory'].strip()
    for key in ('metallic', 'normal_strength', 'uv_scale'):
        if key in values:
            profile[key] = float(values[key])
    if 'orm_texture' in values:
        profile['orm_texture'] = values['orm_texture'].strip()
    from . import profiles
    profiles.validate_settings(profile)
    ids = [x for x in re.split(r'[,;\s]+', values['asset_ids'].strip()) if x]
    if ids:
        profile['asset_ids'] = ids
    else:
        profile.pop('asset_ids', None)
    # Unsupported settings are never silently reset on loading a future profile.
    profile.setdefault('high_policy', 'exclude')
    profile.setdefault('nanite_enabled', False)
    if 'overview_columns' in values:
        overview = dict(profile.get('overview', {}))
        overview.update(columns=int(values['overview_columns']), spacing=float(values['overview_spacing']),
                        label_size=float(values['overview_label_size']),
                        require_valid_assets=bool(values['overview_require_valid']))
        profile['overview'] = overview
        from .overview import settings
        settings(profile)
    if 'preview_width' in values:
        config = dict(profile.get('previews', {}))
        for key in ('width', 'height', 'mode', 'camera', 'output_directory', 'warmup_seconds'):
            value = values['preview_'+key]
            config[key] = int(value) if key in ('width', 'height') else float(value) if key == 'warmup_seconds' else value.strip()
        profile['previews'] = config
        from .previews import settings
        settings(profile)
    if 'delivery_maps' in values:
        config = dict(profile.get('delivery', {}))
        config.update(maps=values['delivery_maps'], output_directory=values['delivery_output_directory'].strip())
        profile['delivery'] = config
        from .delivery import settings
        settings(profile)
    if 'media_yaw_angles' in values:
        config=dict(profile.get('media',{}))
        config['yaw_angles']=[float(x) for x in re.split(r'[,;\s]+',values['media_yaw_angles'].strip()) if x]
        for key in ('pitch','fov','exposure_bias','key_intensity','sky_intensity','margin'):
            config[key]=float(values['media_'+key])
        config['include_invalid']=bool(values['media_include_invalid'])
        config['lod_index']=int(values['media_lod_index'])
        indices=values.get('media_lod_indices','').strip()
        if indices:config['lod_indices']=[int(x) for x in re.split(r'[,;\s]+',indices) if x]
        else:config.pop('lod_indices',None)
        profile['media']=config
        from .media import settings
        settings(profile)
    if 'flythrough_seconds' in values:
        config=dict(profile.get('flythrough',{}))
        for key in ('seconds','fps','width','height','yaw_start','yaw_end','pitch','fov'):
            config[key]=int(values['flythrough_'+key]) if key in ('fps','width','height') else float(values['flythrough_'+key])
        profile['flythrough']=config
        from .flythrough import settings
        settings(profile)
    return profile


def open_window():
    # Legacy direct callers must not recreate Tk inside the editor process.
    import unreal
    if hasattr(unreal, 'AssetPackPipelineNative'):
        return unreal.AssetPackPipelineNative.open_window()
    raise RuntimeError('Legacy Tk UI disabled. Build/install the native Slate module.')


from .guided_window import GuidedWindow


class PipelineWindow(GuidedWindow):
    def __init__(self, parent_to_unreal=True, pump=True, api_adapter=None, saved_directory=None):
        # Tk's default location derives from the interpreter executable. In an
        # embedded Unreal runtime use its bundled Tcl/Tk installation instead.
        for env, directory in [('TCL_LIBRARY', 'tcl8.6'), ('TK_LIBRARY', 'tk8.6')]:
            candidate = Path(sys.base_prefix) / 'tcl' / directory
            if candidate.is_dir():
                os.environ.setdefault(env, str(candidate))
        import tkinter as tk
        from tkinter import ttk
        from . import api, __version__
        self.external = api_adapter is not None
        self.tk, self.ttk, self.api = tk, ttk, api_adapter if self.external else api
        self.root = tk.Tk(className='AssetPackPipeline')
        self.root.title(f'MESHFLOW Asset Pack Pipeline v{__version__}')
        self.root.geometry('1200x860')
        self.root.minsize(1100, 800)
        self.root.configure(bg='#17191e')
        self.icon = tk.PhotoImage(width=32, height=32)
        self.icon.put('#17191e', to=(0, 0, 32, 32))
        self.icon.put('#3975da', to=(6, 6, 26, 26))
        self.icon.put('#8ebaff', to=(9, 9, 23, 12))
        self.icon.put('#8ebaff', to=(9, 15, 15, 23))
        self.root.iconphoto(True, self.icon)
        self.closed = False
        self.in_action = False
        self.tick_handle = None
        self.run_id = None
        self.scene_lod_review = False
        self.last_poll = 0.0
        self.report_path = None
        self.profile_path = None
        self.base = {}
        self.loading = False
        self.dirty = False
        self.variables = {}
        self.session_path = None
        self._style()
        self._build()
        self.root.bind_all('<Control-KeyPress>', self._layout_shortcut, add='+')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.report_callback_exception = self._callback_error
        if self.external:
            self.saved=Path(saved_directory).resolve()
        else:
            import unreal
            self.saved = Path(unreal.Paths.project_saved_dir()).resolve() / 'AssetPackPipeline'
        active = self.saved / 'active_profile.json'
        template = Path(__file__).resolve().parents[2] / 'Profiles' / 'profile.example.json'
        self.load_profile(active if active.is_file() else template)
        if not active.is_file():
            self.variables['source_root'].set('')
            self.profile_path = active
        self._log('Настройте профиль, выполните проверку, затем запускайте импорт.')
        self.root.update_idletasks()
        if sys.platform == 'win32':
            import ctypes
            dark = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.root.wm_frame(), 0), 20, ctypes.byref(dark), ctypes.sizeof(dark))
        if parent_to_unreal:
            unreal.parent_external_window_to_slate(int(self.root.wm_frame(), 0))
        if pump:
            self.tick_handle = unreal.register_slate_post_tick_callback(self._tick)

    # Windows virtual-key codes -> Tk virtual events. Tk matches <Control-a> by
    # keysym, which is Cyrillic in the Russian layout, so Ctrl+A/C/V/X/Z/Y did nothing.
    _SHORTCUTS = {65: '<<SelectAll>>', 67: '<<Copy>>', 86: '<<Paste>>', 88: '<<Cut>>', 90: '<<Undo>>', 89: '<<Redo>>'}

    def _layout_shortcut(self, event):
        virtual = self._SHORTCUTS.get(event.keycode)
        if not virtual or (len(event.keysym) == 1 and event.keysym.isascii()):
            return None  # Latin layout: Tk's own bindings already handle it.
        if virtual == '<<SelectAll>>' and isinstance(event.widget, self.tk.Text):
            event.widget.tag_add('sel', '1.0', 'end-1c')
        else:
            event.widget.event_generate(virtual)
        return 'break'

    def _style(self):
        s = self.ttk.Style(self.root)
        s.theme_use('clam')
        s.configure('.', background='#20232b', foreground='#e5e8ef', font=('Segoe UI', 10))
        s.configure('TFrame', background='#20232b')
        s.configure('Shell.TFrame', background='#17191e')
        s.configure('TLabel', background='#20232b', foreground='#e5e8ef')
        s.configure('Muted.TLabel', foreground='#a1a9ba')
        s.configure('Hero.TLabel', font=('Segoe UI Semibold', 21), background='#17191e')
        s.configure('Subtitle.TLabel', foreground='#a1a9ba', background='#17191e')
        s.configure('TLabelframe', background='#20232b', bordercolor='#363b47',
                    lightcolor='#363b47', darkcolor='#363b47', relief='solid')
        s.configure('TLabelframe.Label', foreground='#a9bded', background='#20232b', font=('Segoe UI Semibold', 10))
        s.configure('TEntry', fieldbackground='#15181f', foreground='#eef0f5', insertcolor='#eef0f5', padding=6,
                    bordercolor='#41495a', lightcolor='#41495a', darkcolor='#41495a')
        # clam otherwise inherits bright system borders on readonly controls.
        s.configure('TCombobox', fieldbackground='#15181f', background='#282e3b',
                    foreground='#eef0f5', arrowcolor='#a9bded', arrowsize=13,
                    bordercolor='#363b47', lightcolor='#363b47', darkcolor='#363b47',
                    borderwidth=1, relief='flat', padding=(9, 6))
        s.map('TCombobox', fieldbackground=[('disabled', '#20232b'), ('readonly', '#15181f')],
              foreground=[('disabled', '#758094'), ('readonly', '#eef0f5')],
              background=[('active', '#343f52'), ('!active', '#282e3b')],
              bordercolor=[('focus', '#598de0'), ('active', '#53627c'), ('!focus', '#363b47')],
              lightcolor=[('focus', '#598de0'), ('!focus', '#363b47')],
              darkcolor=[('focus', '#598de0'), ('!focus', '#363b47')],
              arrowcolor=[('disabled', '#596174'), ('!disabled', '#a9bded')])
        s.configure('TButton', background='#343b4b', foreground='#eef0f5', padding=(12, 7), borderwidth=0)
        s.map('TButton', background=[('active', '#465269')], foreground=[('disabled', '#758094')])
        s.configure('Accent.TButton', background='#3975da', font=('Segoe UI Semibold', 10))
        s.map('Accent.TButton', background=[('active', '#4b87ef'), ('disabled', '#303a4d')])
        s.configure('TCheckbutton', background='#20232b', indicatorbackground='#15181f',
                    indicatorforeground='#eef0f5', bordercolor='#53627c',
                    lightcolor='#363b47', darkcolor='#363b47', focuscolor='#20232b', padding=(0, 3))
        s.map('TCheckbutton', background=[('active', '#20232b')],
              indicatorbackground=[('selected', '#3975da'), ('!selected', '#15181f')],
              foreground=[('disabled', '#758094'), ('!disabled', '#e5e8ef')])
        s.configure('TNotebook', background='#17191e', borderwidth=0,
                    lightcolor='#363b47', darkcolor='#363b47', bordercolor='#363b47')
        s.configure('TNotebook.Tab', padding=(12, 10), background='#17191e',
                    foreground='#a1a9ba', borderwidth=0, focuscolor='#20232b',
                    bordercolor='#17191e', lightcolor='#17191e', darkcolor='#17191e')
        # Remove clam's raised tab bevel and dotted focus ring. Keyboard focus
        # stays visible via the label color; arrow/Ctrl-Tab navigation is retained.
        s.layout('TNotebook.Tab', [('Notebook.tab', {'sticky': 'nswe', 'children': [
            ('Notebook.padding', {'side': 'top', 'sticky': 'nswe', 'children': [
                ('Notebook.label', {'side': 'top', 'sticky': ''})]})]})])
        s.map('TNotebook.Tab', background=[('selected', '#20232b'), ('active', '#282e3b')],
              foreground=[('focus', '#8ebaff'), ('selected', '#eef0f5'), ('active', '#cbd8ee')],
              bordercolor=[('selected', '#20232b'), ('!selected', '#17191e')],
              lightcolor=[('selected', '#20232b'), ('!selected', '#17191e')],
              darkcolor=[('selected', '#20232b'), ('!selected', '#17191e')])
        s.map('TEntry', bordercolor=[('focus', '#598de0'), ('!focus', '#363b47')],
              lightcolor=[('focus', '#598de0'), ('!focus', '#363b47')],
              darkcolor=[('focus', '#598de0'), ('!focus', '#363b47')])
        s.configure('Vertical.TScrollbar', background='#343b4b', troughcolor='#20232b',
                    bordercolor='#20232b', lightcolor='#343b4b', darkcolor='#343b4b', arrowcolor='#a1a9ba')
        s.configure('Treeview', background='#191d25', fieldbackground='#191d25', foreground='#e5e8ef',
                    rowheight=27, borderwidth=0)
        s.configure('Treeview.Heading', background='#303747', foreground='#b9c9e7', padding=6)
        s.map('Treeview', background=[('selected', '#304e79')])
        s.configure('Horizontal.TProgressbar', background='#4e8cf2', troughcolor='#15181f', borderwidth=0)
        self.root.option_add('*TCombobox*Listbox.background', '#20232b')
        self.root.option_add('*TCombobox*Listbox.foreground', '#e5e8ef')
        self.root.option_add('*TCombobox*Listbox.selectBackground', '#304e79')
        self.root.option_add('*TCombobox*Listbox.selectForeground', '#eef0f5')
        self.root.option_add('*TCombobox*Listbox.highlightThickness', 0)
        self.root.option_add('*TCombobox*Listbox.relief', 'flat')
        from .dark_controls import apply
        apply(self, s)

    def _field(self, frame, row, key, label, default='', choices=None, browse=None):
        self.ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', padx=(12, 14), pady=5)
        var = self.tk.StringVar(value=default)
        self.variables[key] = var
        if choices:
            widget = self.ttk.Combobox(frame, textvariable=var, values=choices, state='readonly')
        else:
            widget = self.ttk.Entry(frame, textvariable=var)
        widget.grid(row=row, column=1, sticky='ew', pady=5, padx=(0, 10))
        if browse:
            self.ttk.Button(frame, text='Обзор…', command=browse).grid(row=row, column=2, padx=(0, 12), pady=5)
        frame.columnconfigure(1, weight=1)
        var.trace_add('write', self._changed)
        return widget

    def _build(self):
        t = self.ttk
        shell = t.Frame(self.root, style='Shell.TFrame', padding=18)
        shell.pack(fill='both', expand=True)
        # The custom title bar (custom_host) already carries brand and steps.
        if not hasattr(self, 'chrome'):
            from .custom_chrome import TITLE, SUBTITLE
            t.Label(shell, text=TITLE, style='Hero.TLabel').pack(anchor='w')
            t.Label(shell, text=SUBTITLE, style='Subtitle.TLabel').pack(anchor='w', pady=(2, 14))
        bar = t.Frame(shell, padding=9)
        bar.pack(fill='x', pady=(0, 10))
        self.profile_label = t.Label(bar, text='Профиль', style='Muted.TLabel')
        self.profile_label.pack(side='left', fill='x', expand=True)
        self.update_button=t.Button(bar, text='Обновления…', command=self.open_updates)
        self.update_button.pack(side='left',padx=6)
        t.Button(bar, text='Настройки AI…', command=self.open_ai_settings).pack(side='left', padx=6)
        t.Button(bar, text='Сканировать Content…', command=self.scan_content).pack(side='left', padx=6)
        for title, callback in [('Загрузить…', self.browse_profile), ('Сохранить', self.save_profile),
                                ('Сохранить как…', lambda: self.save_profile(save_as=True))]:
            t.Button(bar, text=title, command=callback).pack(side='left', padx=(6, 0))
        self.tabs = t.Notebook(shell)
        self.tabs.pack(fill='both', expand=True)
        from .scroll_page import ScrollPage, route_wheel, route_focus
        self.root.bind('<MouseWheel>', route_wheel, add='+')
        self.root.bind('<FocusIn>', route_focus, add='+')
        self.scroll_pages = {}
        def form(title):
            page = ScrollPage(self.tabs)
            self.tabs.add(page, text=title)
            self.scroll_pages[title] = page
            return page.content
        setup = form('Импорт и LOD')
        materials = form('Материалы и меши')
        overview = form('Обзорная сцена')
        diagnostics = form('Диагностика')
        previews = form('Превью')
        overrides = form('По моделям')
        queue = t.Frame(self.tabs, padding=10)
        delivery = form('Поставка')
        self.delivery_tab = delivery
        media = form('Предметы')
        results = t.Frame(self.tabs, padding=10)
        self.tabs.add(queue, text='Очередь')
        self.tabs.add(results, text='Результаты и журнал')
        for index, title in enumerate(('Импорт и LOD', 'Материалы и меши', 'По моделям', 'Обзорная сцена',
                                       'Диагностика', 'Превью', 'Предметы', 'Очередь', 'Поставка', 'Результаты и журнал')):
            page = queue if title == 'Очередь' else results if title == 'Результаты и журнал' else self.scroll_pages[title]
            self.tabs.insert(index, page)
        self.results_tab = results
        source = t.LabelFrame(setup, text='  Источники  ')
        source.pack(fill='x', pady=(0, 10))
        self._field(source, 0, 'source_root', 'Папка экспорта', browse=self.browse_source)
        self._field(source, 1, 'source_format', 'Формат', 'FBX', ['FBX', 'GLB'])
        self._field(source, 2, 'mesh_info', 'Каталог моделей', 'MeshInfo.json')
        self._field(source, 3, 'asset_ids', 'Модели', '')
        self.variables['incremental'] = self.tk.BooleanVar(value=True)
        self.variables['incremental'].trace_add('write', self._changed)
        t.Checkbutton(source, text='Пропускать неизменённые модели после проверки ассетов',
                      variable=self.variables['incremental']).grid(row=5, column=0, columnspan=3, sticky='w', padx=12, pady=5)
        self._field(source, 6, 'validation_policy', 'Проблемы геометрии: warn — продолжать со всеми моделями', 'warn', ['warn','strict'])
        t.Label(source, text='ID через запятую; пустое поле — все модели. MID/HIGH используются только с Nanite.',
                style='Muted.TLabel').grid(row=4, column=0, columnspan=3, sticky='w', padx=12, pady=(0, 8))
        destination = t.LabelFrame(setup, text='  Назначение и уровни детализации  ')
        destination.pack(fill='x')
        self._field(destination, 0, 'pack_id', 'Имя пака', 'GraveStones02')
        self._field(destination, 1, 'destination_root', 'Папка в Content', '/Game/GraveStones02')
        self._field(destination, 2, 'lod_screen_sizes', 'Screen sizes LOD0…', '1, 0.5, 0.25, 0.125, 0.0625')
        self.variables['nanite_enabled'] = self.tk.BooleanVar(value=False)
        self.variables['nanite_enabled'].trace_add('write', self._changed)
        t.Checkbutton(destination, text='Nanite ON — один MID/HIGH вместо цепочки LOD',
                      variable=self.variables['nanite_enabled']).grid(row=3, column=0, columnspan=3, sticky='w', padx=12, pady=5)
        self._field(destination, 4, 'nanite_source', 'Источник Nanite', 'AUTO', ['AUTO', 'MID', 'HIGH'])
        t.Label(destination, text='AUTO: MID, иначе HIGH из MeshInfo. Без Nanite используются LOD0…LOD4.',
                style='Muted.TLabel').grid(row=5, column=0, columnspan=3, sticky='w', padx=12, pady=(0, 8))
        self._field(destination, 6, 'mesh_subdirectory', 'Подпапка мешей в едином проекте', '', ['', 'LOD', 'Nanite'])
        maps = t.LabelFrame(materials, text='  Master material и instances  ')
        maps.pack(fill='x', pady=(0, 12))
        self._field(maps, 0, 'texture_directory', 'Текстуры от папки экспорта', 'FBX/Textures')
        self._field(maps, 1, 'roughness', 'Roughness', '0.85')
        self._field(maps, 2, 'metallic', 'Metallic', '0')
        self._field(maps, 3, 'normal_strength', 'Normal Strength (0…4)', '1')
        self._field(maps, 4, 'uv_scale', 'UV Scale (0.01…100)', '1')
        self._field(maps, 5, 'orm_texture', 'ORM от папки экспорта (необязательно)', '')
        t.Label(maps, text='ORM: R=AO, G=Roughness, B=Metallic. Можно использовать {asset_id} в пути.\n'
                           'С ORM Roughness умножает канал G; Metallic берётся из B.',
                style='Muted.TLabel').grid(row=6, column=0, columnspan=3, sticky='w', padx=12, pady=5)
        self.settings_button = t.Button(maps, text='Обновить материалы и настройки без импорта мешей',
                                       command=lambda: self.execute('settings'))
        self.settings_button.grid(row=7, column=0, columnspan=3, sticky='w', padx=12, pady=8)
        meshes = t.LabelFrame(materials, text='  Настройки меша  ')
        meshes.pack(fill='x')
        self._field(meshes, 0, 'collision', 'Простая коллизия', 'convex', ['convex', 'box', 'none'])
        self.variables['remove_degenerates'] = self.tk.BooleanVar(value=True)
        self.variables['remove_degenerates'].trace_add('write', self._changed)
        t.Checkbutton(meshes, text='Удалять вырожденные полигоны при импорте FBX',
                      variable=self.variables['remove_degenerates']).grid(row=1, column=0, columnspan=3, sticky='w', padx=12, pady=10)
        t.Label(meshes, text='Режим Nanite и источник MID/HIGH задаются на вкладке настройки.',
                style='Muted.TLabel').grid(row=2, column=0, columnspan=3, sticky='w', padx=12, pady=(0, 12))
        self._field(meshes,3,'convex_hull_count','Convex: максимум оболочек',8)
        self._field(meshes,4,'convex_max_hull_verts','Convex: вершин на оболочку',16)
        self._field(meshes,5,'convex_precision','Convex: точность',100000)
        model = t.LabelFrame(overrides, text='  Переопределения для одной модели  ')
        model.pack(fill='x', pady=8)
        self._field(model, 0, 'override_asset', 'ID модели', '')
        self._field(model, 1, 'override_lod_screen_sizes', 'Screen sizes (пусто = общие)', '')
        self._field(model, 2, 'override_collision', 'Коллизия', 'inherit', ['inherit', 'convex', 'none', 'box'])
        self._field(model, 3, 'override_remove_degenerates', 'Remove Degenerates', 'inherit', ['inherit', 'true', 'false'])
        for row, key, label in [(4, 'roughness', 'Roughness'), (5, 'metallic', 'Metallic'),
                                (6, 'normal_strength', 'Normal Strength'), (7, 'uv_scale', 'UV Scale'),
                                (8, 'orm_texture', 'ORM: пусто = общий путь, - = отключить')]:
            self._field(model, row, 'override_'+key, label, '')
        self._field(model, 9, 'override_nanite_source', 'Источник Nanite', 'inherit', ['inherit', 'AUTO', 'MID', 'HIGH'])
        actions = t.Frame(overrides)
        actions.pack(fill='x', pady=8)
        for text, action in [('Загрузить значения', 'load'), ('Записать в профиль', 'store'), ('Удалить переопределения', 'delete')]:
            t.Button(actions, text=text, command=lambda a=action: self.edit_override(a)).pack(side='left', padx=(0, 8))
        self.override_summary = t.Label(overrides, text='', style='Muted.TLabel')
        self.override_summary.pack(anchor='w', pady=8)
        t.Label(overrides, text='Пустые значения наследуются из общих настроек. Число LOD менять нельзя.\n'
                              'После редактирования нажмите «Записать в профиль», затем сохраните профиль.\n'
                              'Настройки применяются к моделям, выбранным на вкладке импорта.\n'
                              'Обновление материалов/настроек не импортирует геометрию заново.',
                style='Muted.TLabel', justify='left').pack(anchor='w', pady=8)
        scene = t.LabelFrame(overview, text='  Автоматическая обзорная карта  ')
        scene.pack(fill='x', pady=(0, 12))
        self._field(scene, 0, 'overview_columns', 'Столбцов в сетке', '4')
        self._field(scene, 1, 'overview_spacing', 'Отступ между мешами, см', '100')
        self._field(scene, 2, 'overview_label_size', 'Размер подписи, см', '5')
        self.variables['overview_require_valid'] = self.tk.BooleanVar(value=True)
        self.variables['overview_require_valid'].trace_add('write', self._changed)
        t.Checkbutton(scene, text='Требовать успешную проверку всех мешей',
                      variable=self.variables['overview_require_valid']).grid(row=3, column=0, columnspan=3, sticky='w', padx=12, pady=10)
        t.Label(scene, text='Снятый флажок разрешает диагностическую сцену с проблемными моделями.\n'
                           'Она не считается готовой поставкой.', style='Muted.TLabel').grid(
                               row=4, column=0, columnspan=3, sticky='w', padx=12, pady=(0, 12))
        t.Label(overview, text='Обзор: все выбранные меши, подписи, фон, свет и две камеры.\n'
                               'Сравнение LOD: отдельная карта с принудительным показом каждого уровня.\n\n'
                               'Повторный запуск обновляет помеченные объекты. Перед изменением карты\n'
                               'создаётся резервная копия. Несохранённые карты блокируют переключение.',
                style='Muted.TLabel', justify='left').pack(anchor='w', pady=10)
        scene_actions = t.Frame(overview)
        scene_actions.pack(fill='x', pady=10)
        self.scene_buttons = []
        for label, action in [('Создать / обновить обзор', 'overview'), ('Сравнение LOD', 'lod_review'),
                              ('Открыть обзор', 'open_overview'), ('Проверить сцену', 'validate_overview')]:
            button = t.Button(scene_actions, text=label, command=lambda a=action: self.execute(a))
            button.pack(side='left', padx=(0, 7))
            self.scene_buttons.append(button)
        t.Label(diagnostics, text='Геометрия экспорта или обработка импорта?', font=('Segoe UI Semibold', 15)).pack(anchor='w', pady=(6, 16))
        t.Label(diagnostics, text='Анализ экспортов читает FBX и GLB напрямую: число треугольников,\n'
                                 'нулевая и почти нулевая площадь, вырожденные UV, индексы проблемных полигонов.\n\n'
                                 'Сравнение импорта создаёт отдельные тестовые меши для каждого формата\n'
                                 'с Remove Degenerates включённым и выключенным. Nanite отключается,\n'
                                 'чтобы не сравнивать fallback-геометрию с оригиналом.\n\n'
                                 'Проверяются модели, выбранные на вкладке «Импорт и LOD».\n'
                                 'Исходные экспорты не изменяются; SHA-256 проверяются после диагностики.\n'
                                 'Тестовые ассеты находятся в отдельной папке AssetPackPipeline_Diagnostics.',
                style='Muted.TLabel', justify='left').pack(anchor='w')
        diag_actions = t.Frame(diagnostics)
        diag_actions.pack(fill='x', pady=20)
        self.diagnostic_buttons = []
        for label, action in [('Анализ экспортов', 'source_diagnostics'), ('Сравнить импорт FBX / GLB', 'import_diagnostics')]:
            button = t.Button(diag_actions, text=label, command=lambda a=action: self.execute(a))
            button.pack(side='left', padx=(0, 10))
            self.diagnostic_buttons.append(button)
        t.Label(diagnostics, text='Завершённая диагностика не означает, что геометрия исправна.\n'
                                 'Итоговый отчёт различает дефекты исходного экспорта и влияние настроек UE.',
                style='Muted.TLabel', justify='left').pack(anchor='w')
        export = t.LabelFrame(previews, text='  PNG из сохранённых обзорных карт  ')
        export.pack(fill='x', pady=10)
        self._field(export, 0, 'preview_width', 'Ширина, px', '1920')
        self._field(export, 1, 'preview_height', 'Высота, px', '1080')
        self._field(export, 2, 'preview_mode', 'Сцены', 'overview', ['overview', 'lod_review', 'both'])
        self._field(export, 3, 'preview_camera', 'Камера', 'overview', ['overview', 'detail'])
        self._field(export, 4, 'preview_warmup_seconds', 'Прогрев сцены, секунд', '5')
        self._field(export, 5, 'preview_output_directory', 'Папка вывода (необязательно)', '')
        t.Label(previews, text='Сначала создайте и сохраните нужные карты на вкладке «Обзорная сцена».\n'
                              'Пустая папка: Saved/AssetPackPipeline/Previews. Каждый запуск — отдельная папка.\n'
                              'Экспорт оставляет последнюю карту открытой. Несохранённые карты блокируют запуск.\n'
                              'Остановка дождётся текущего кадра; готовые PNG сохраняются.\n'
                              'Камера берётся из сцены; её положение можно изменить и сохранить в Unreal.',
                style='Muted.TLabel', justify='left').pack(anchor='w', pady=12)
        self.preview_buttons = [t.Button(previews, text='Экспортировать PNG', command=lambda: self.execute('previews'))]
        self.preview_buttons[0].pack(anchor='w')
        studio=t.LabelFrame(media,text='  Автоматические предметные кадры  ')
        studio.pack(fill='x',pady=8)
        for row,key,label,default in [(0,'yaw_angles','Ракурсы, градусы','90, 120'),(1,'pitch','Наклон камеры, градусы','15'),
            (2,'fov','Поле зрения, градусы','40'),(3,'margin','Запас кадрирования','1.18'),
            (4,'exposure_bias','Экспокоррекция, EV','-0.75'),(5,'key_intensity','Основной свет','3'),
            (6,'sky_intensity','Заполняющий свет','0.6'),(7,'lod_index','Принудительный LOD','0'),
            (8,'lod_indices','Серия LOD (пусто = один LOD)','')]:
            self._field(studio,row,'media_'+key,label,default)
        self.variables['media_include_invalid']=self.tk.BooleanVar(value=False)
        self.variables['media_include_invalid'].trace_add('write',self._changed)
        t.Checkbutton(studio,text='Разрешить диагностические кадры моделей с ошибками',
            variable=self.variables['media_include_invalid']).grid(row=9,column=0,columnspan=3,sticky='w',padx=12,pady=8)
        t.Label(media,text='Камера автоматически подстраивается под размер каждой выбранной модели.\n'
            'Разрешение, прогрев и папка вывода задаются на вкладке «Превью».\n'
            'Серия 0,1,2,3,4 создаёт сравнение LOD с одинаковой камерой. Рядом с PNG — review.html.\n'
            'Студия создаётся отдельно; кадры проблемных моделей получают отметку diagnostic.\n'
            'Остановка выполняется после текущего кадра. Готовые PNG остаются в папке запуска.',
            style='Muted.TLabel',justify='left').pack(anchor='w',pady=8)
        self.media_button=t.Button(media,text='Создать предметные PNG',command=lambda:self.execute('media'))
        self.media_button.pack(anchor='w')
        self.auto_lod_button=t.Button(media,text='Проверить автоматические LOD',command=lambda:self.execute('auto_lod'))
        self.auto_lod_button.pack(anchor='w',pady=6)
        t.Label(media,text='Авто LOD: первый ракурс, FOV 90°, 1280×720; фактические LOD/triangles из draw-command CSV.',
                style='Muted.TLabel').pack(anchor='w')
        flight=t.LabelFrame(media,text='  Непрерывный пролёт камеры (Movie Render Queue)  ')
        flight.pack(fill='x',pady=8)
        for row,key,label,default in [(0,'seconds','Длительность, секунд','8'),(1,'fps','Частота кадров','24'),
            (2,'width','Ширина, px','1280'),(3,'height','Высота, px','720'),
            (4,'yaw_start','Начальный ракурс, градусы','65'),(5,'yaw_end','Конечный ракурс, градусы','115'),
            (6,'pitch','Высота ракурса, градусы','25'),(7,'fov','Поле зрения, градусы','50')]:
            self._field(flight,row,'flythrough_'+key,label,default)
        self._field(flight,8,'flight_run_id','Run ID сохранённого пролёта','')
        self.flythrough_open_button=t.Button(flight,text='Открыть карту и Level Sequence',command=lambda:self.execute('open_flythrough'))
        self.flythrough_open_button.grid(row=9,column=0,columnspan=3,sticky='w',padx=12,pady=6)
        self.flythrough_button=t.Button(media,text='Создать и отрендерить пролёт',command=lambda:self.execute('flythrough'))
        self.flythrough_button.pack(anchor='w',pady=6)
        output = t.LabelFrame(delivery, text='  Очистка staging и чистый проект  ')
        output.pack(fill='x', pady=8)
        self._field(output, 0, 'cleanup_run_id', 'Staging Run ID (пусто = весь пак)', '')
        self._field(output, 1, 'delivery_maps', 'Карты в поставке', 'overview', ['none', 'overview', 'both'])
        self._field(output, 2, 'delivery_output_directory', 'Папка поставок (необязательно)', '')
        self._field(output, 3, 'delivery_run_id', 'Run ID созданной поставки', '')
        self._field(output, 4, 'review_media_run_ids', 'Run ID предметных кадров через запятую', '')
        self._field(output, 5, 'combined_profile_path', 'Профиль второго типа LOD / Nanite (JSON)', '')
        t.Label(delivery, text='1. Проверьте план очистки. Чужие и используемые ассеты сохраняются.\n'
                              '2. Создайте чистый проект из прошедших проверку моделей и сохранённых карт.\n'
                              '3. Запустите проверку отдельным Unreal, затем соберите ZIP.\n\n'
                              'Перед очисткой и копированием сохраните все карты и ассеты.\n'
                              'Поставка требует успешной проверки каждой выбранной модели.\n'
                              'Отдельный проект создаётся в новой папке; готовность Fab требует визуальной приёмки.',
                style='Muted.TLabel', justify='left').pack(anchor='w', pady=10)
        buttons = t.Frame(delivery)
        buttons.pack(fill='x', pady=8)
        self.delivery_buttons = []
        for index, (text, action) in enumerate([('План очистки', 'cleanup_plan'), ('Очистить staging', 'cleanup'),
                ('Подготовить все модели к просмотру', 'candidate'),
                ('План поставки', 'delivery_plan'), ('Один проект LOD + Nanite', 'combined_delivery'),
                ('Один тип (служебная поставка)', 'delivery'),
                ('Проверить отдельным Unreal', 'delivery_verify'), ('Собрать ZIP', 'delivery_package'),
                ('Windows cooking','delivery_cook'), ('Общий просмотр LOD / Nanite','review_bundle')]):
            button = t.Button(buttons, text=text, command=lambda a=action:self.execute(a))
            button.grid(row=index//3, column=index%3, padx=(0,8), pady=5, sticky='ew')
            self.delivery_buttons.append(button)
        t.Label(queue, text='Сохранённые запуски импорта и обновления настроек',
                font=('Segoe UI Semibold', 15)).pack(anchor='w', pady=(4, 12))
        self.queue_table = t.Treeview(queue, columns=('run', 'kind', 'status', 'time'), show='headings', height=10)
        for key, title, width in [('run', 'Run ID', 290), ('kind', 'Тип', 130), ('status', 'Статус', 140),
                                  ('time', 'Время', 180)]:
            self.queue_table.heading(key, text=title)
            self.queue_table.column(key, width=width)
        self.queue_table.pack(fill='both', expand=True)
        queue_actions = t.Frame(queue)
        queue_actions.pack(fill='x', pady=12)
        t.Button(queue_actions, text='Обновить список', command=self.refresh_queue).pack(side='left', padx=(0, 8))
        self.resume_button = t.Button(queue_actions, text='Продолжить выбранный запуск', command=self.resume_selected)
        self.resume_button.pack(side='left')
        t.Label(queue, text='Возобновление использует сохранённый профиль прошлого запуска.\n'
                            'Изменённые исходники или другая версия Unreal/плагина блокируют продолжение.\n'
                            'Новая задача получает новый Run ID; завершённые модели перепроверяются.',
                style='Muted.TLabel', justify='left').pack(anchor='w')
        self.summary = t.Label(results, text='Сначала выполните проверку исходников.', style='Muted.TLabel')
        self.summary.pack(anchor='w', pady=(0, 8))
        table_frame = t.Frame(results)
        table_frame.pack(fill='both', expand=True)
        self.table = t.Treeview(table_frame, columns=('model', 'status', 'lods', 'triangles'), show='headings', height=7)
        for key, title, width in [('model', 'Модель', 240), ('status', 'Состояние', 140),
                                   ('lods', 'LOD', 55), ('triangles', 'Треугольники по уровням', 390)]:
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=40, stretch=key in ('model', 'triangles'))
        self.table.pack(side='left', fill='both', expand=True)
        scroll = t.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        scroll.pack(side='right', fill='y')
        self.table.configure(yscrollcommand=scroll.set)
        self.table.tag_configure('passed', foreground='#9cdbb2')
        self.table.tag_configure('failed', foreground='#ff9d9d')
        self.table.bind('<<TreeviewSelect>>', self._select_asset)
        self.asset_details = {}
        t.Label(results, text='Журнал / подробности выбранной модели', style='Muted.TLabel').pack(anchor='w', pady=(10, 5))
        log_frame = t.Frame(results)
        log_frame.pack(fill='both', expand=True)
        self.log = self.tk.Text(log_frame, height=8, bg='#14171d', fg='#bbc7dd', insertbackground='white',
                                font=('Consolas', 10), wrap='word', relief='flat', padx=10, pady=8, state='disabled')
        self.log.pack(side='left', fill='both', expand=True)
        log_scroll = t.Scrollbar(log_frame, orient='vertical', command=self.log.yview)
        log_scroll.pack(side='right', fill='y')
        self.log.configure(yscrollcommand=log_scroll.set)
        controls = t.Frame(shell, padding=(10, 8))
        self.controls_frame = controls
        controls.pack(side='bottom',fill='x',pady=(10,0),before=self.tabs)
        self.state_label = t.Label(controls, text='Готово к настройке', style='Muted.TLabel')
        self.state_label.pack(anchor='w', pady=(0, 5))
        self.progress = t.Progressbar(controls, mode='determinate', maximum=100)
        self.progress.pack(fill='x', pady=(0, 8))
        actions = t.Frame(controls)
        self.expert_actions = actions
        actions.pack(fill='x',before=self.state_label)
        self.action_buttons = []
        for label, action, style in [('Проверить исходники', 'plan', 'TButton'),
                                      ('Запустить импорт', 'start', 'Accent.TButton'),
                                      ('Проверить ассеты', 'validate', 'TButton')]:
            button = t.Button(actions, text=label, style=style, command=lambda a=action: self.execute(a))
            button.pack(side='left', padx=(0, 7))
            self.action_buttons.append(button)
        self.cancel_button = t.Button(actions, text='Остановить', command=self.cancel, state='disabled')
        self.cancel_button.pack(side='left')
        t.Button(actions, text='Открыть отчёты', command=self.open_reports).pack(side='right')
        self.build_guided(shell)

    def _changed(self, *_):
        if not self.loading:
            self.dirty = True
            self._profile_title()

    def _profile_title(self):
        if self.profile_path:
            self.profile_label.configure(text=f'{self.profile_path.name}' + ('  • изменён' if self.dirty else ''))

    def _log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', time.strftime('%H:%M:%S') + '  ' + text + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def _callback_error(self, kind, value, tb):
        self._log('Ошибка: ' + str(value))
        self.state_label.configure(text='Ошибка — подробности в журнале')
        self.tabs.select(self.results_tab)
        if self.external:
            print(f'AssetPackPipeline Custom UI: {value}',file=sys.stderr)
        else:
            import unreal
            unreal.log_error(f'AssetPackPipeline UI: {value}')

    def load_profile(self, path):
        from .discovery import read_json
        profile = read_json(path)
        # Normalize only the old shipped presets, including existing active profiles.
        if profile.get('media', {}).get('yaw_angles') in ([-60], [-60, 120]):
            profile['media']['yaw_angles'] = [90] if len(profile['media']['yaw_angles']) == 1 else [90, 120]
        if profile.get('flythrough', {}).get('yaw_start') == -115 and profile['flythrough'].get('yaw_end') == -65:
            profile['flythrough'].update(yaw_start=65, yaw_end=115)
        if profile.get('schema_version') != 1:
            raise ValueError('Поддерживается schema_version = 1.')
        self.loading = True
        try:
            self.base = profile
            for key, var in self.variables.items():
                from . import profiles
                value = profile.get(key, profiles.DEFAULTS.get(key, var.get()))
                if key.startswith('convex_'):
                    value=profiles.convex_settings(profile)[key[len('convex_'):]]
                if key.startswith('override_'):
                    value = 'inherit' if key in ('override_collision', 'override_remove_degenerates') else ''
                if key == 'incremental':
                    value = profile.get('incremental', True)
                if key == 'validation_policy':
                    value = profile.get(key, 'warn')
                if key.startswith('flythrough_'):
                    defaults={'seconds':8,'fps':24,'width':1280,'height':720,'yaw_start':65,'yaw_end':115,'pitch':25,'fov':50}
                    name=key[len('flythrough_'):];value=profile.get('flythrough',{}).get(name,defaults[name])
                if key in ('delivery_maps', 'delivery_output_directory'):
                    name = key[len('delivery_'):]
                    value = profile.get('delivery', {}).get(name, 'overview' if name=='maps' else '')
                if key in ('cleanup_run_id', 'delivery_run_id'):
                    value = ''
                if key.startswith('media_'):
                    defaults={'yaw_angles':[90,120],'pitch':15,'fov':40,'margin':1.18,'exposure_bias':-.75,
                              'key_intensity':3,'sky_intensity':.6,'lod_index':0,'lod_indices':[],'include_invalid':False}
                    name=key[len('media_'):];value=profile.get('media',{}).get(name,defaults[name])
                    if name in ('yaw_angles','lod_indices'):value=', '.join(map(str,value))
                overview_defaults = {'overview_columns': ('columns', 4), 'overview_spacing': ('spacing', 100),
                                     'overview_label_size': ('label_size', 5),
                                     'overview_require_valid': ('require_valid_assets', True)}
                if key in overview_defaults:
                    name, default = overview_defaults[key]
                    value = profile.get('overview', {}).get(name, default)
                if key.startswith('preview_'):
                    defaults = {'width': 1920, 'height': 1080, 'mode': 'overview', 'camera': 'overview',
                                'warmup_seconds': 5, 'output_directory': ''}
                    name = key[len('preview_'):]
                    value = profile.get('previews', {}).get(name, defaults[name])
                if key == 'asset_ids':
                    value = ', '.join(profile.get(key, []))
                elif key == 'lod_screen_sizes':
                    value = ', '.join(str(x) for x in profile.get(key, [1, 0.5, 0.25, 0.125, 0.0625]))
                if key == 'nanite_enabled': value = profile.get(key, False)
                elif key == 'nanite_source': value = profile.get(key, 'AUTO')
                var.set(value)
            self.profile_path = Path(path)
            self.override_summary.configure(text='В профиле: '+(', '.join(sorted(profile.get('asset_overrides', {}))) or 'нет переопределений'))
            self.dirty = False
            self._profile_title()
        finally:
            self.loading = False

    def collect(self):
        return profile_from_fields(self.base, {key: value.get() for key, value in self.variables.items()})

    def edit_override(self, action):
        try:
            from . import profiles
            asset = self.variables['override_asset'].get().strip()
            if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*', asset):
                raise ValueError('Введите ID модели из MeshInfo, например GraveStones_02_01')
            overrides = copy.deepcopy(self.base.get('asset_overrides', {}))
            if action == 'load':
                values = overrides.get(asset, {})
                for key in profiles.OVERRIDE_KEYS:
                    value = values.get(key, 'inherit' if key in ('collision', 'remove_degenerates') else '')
                    if key == 'lod_screen_sizes' and value != '':
                        value = ', '.join(map(str, value))
                    elif key == 'remove_degenerates' and isinstance(value, bool):
                        value = str(value).lower()
                    elif key == 'orm_texture' and key in values and not value:
                        value = '-'
                    self.variables['override_'+key].set(value)
                return
            if action == 'delete':
                overrides.pop(asset, None)
            else:
                values = {}
                for key in profiles.OVERRIDE_KEYS:
                    value = self.variables['override_'+key].get().strip()
                    if not value or value == 'inherit':
                        continue
                    if key == 'lod_screen_sizes':
                        value = [float(x) for x in re.split(r'[,;\s]+', value) if x]
                    elif key == 'remove_degenerates':
                        value = value == 'true'
                    elif key in ('roughness', 'metallic', 'normal_strength', 'uv_scale'):
                        value = float(value)
                    elif key == 'orm_texture' and value == '-':
                        value = ''
                    values[key] = value
                candidate = self.collect()
                candidate['asset_overrides'] = {asset: values}
                effective = profiles.effective(candidate, asset)
                if not candidate.get('nanite_enabled', False) and len(effective['lod_screen_sizes']) != len(candidate['lod_screen_sizes']):
                    raise ValueError('Переопределение не может менять число LOD')
                if values:
                    overrides[asset] = values
                else:
                    overrides.pop(asset, None)
            self.base['asset_overrides'] = overrides
            self.dirty = True
            self._profile_title()
            self.override_summary.configure(text='В профиле: '+(', '.join(sorted(overrides)) or 'нет переопределений'))
        except Exception as error:
            self._callback_error(type(error), error, error.__traceback__)

    def _snapshot(self):
        folder = self.saved / 'UI'
        folder.mkdir(parents=True, exist_ok=True)
        if self.session_path is None:
            self.session_path = folder / (uuid.uuid4().hex + '.json')
        self.session_path.write_text(json.dumps(self.collect(), ensure_ascii=False, indent=2), encoding='utf-8')
        return str(self.session_path)

    def browse_source(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self.root, title='Папка с MeshInfo.json и экспортами')
        if path:
            self.variables['source_root'].set(path)

    def browse_profile(self):
        from tkinter import filedialog, messagebox
        if self.dirty and not messagebox.askyesno('Профиль изменён', 'Загрузить другой профиль и отбросить несохранённые настройки?', parent=self.root):
            return
        path = filedialog.askopenfilename(parent=self.root, title='Загрузить профиль', filetypes=[('JSON profile', '*.json')])
        if path:
            self.load_profile(path)
            self._log(f'Загружен профиль: {path}')

    def save_profile(self, save_as=False):
        from tkinter import filedialog
        path = self.profile_path
        if save_as:
            selected = filedialog.asksaveasfilename(parent=self.root, title='Сохранить профиль',
                                                   defaultextension='.json', initialfile='profile.json', filetypes=[('JSON', '*.json')])
            if not selected:
                return
            path = Path(selected)
        data = self.collect()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        self.base = data
        self.profile_path = path
        self.dirty = False
        self._profile_title()
        self._log(f'Профиль сохранён: {path}')

    def _rows(self, assets):
        self.table.delete(*self.table.get_children())
        self.asset_details = {}
        for index, asset in enumerate(assets):
            state = asset.get('status', ('passed' if asset['passed'] else 'failed') if 'passed' in asset else 'pending')
            state_text = {'passed': 'Готово', 'failed': 'Ошибка', 'running': 'Обработка',
                          'pending': 'Ожидает', 'cancelled': 'Остановлено', 'skipped': 'Пропущено'}.get(state, state)
            if asset.get('diagnostic') and asset.get('source_quality_passed') is False:
                state_text, state = 'Есть замечания', 'failed'
            if asset.get('warnings') and asset.get('passed'):
                state_text = 'Готово с замечаниями'
            triangles = asset.get('triangles', [lod['triangles'] for lod in asset.get('lods', [])])
            triangle_text = ' / '.join(map(str, triangles))
            if asset.get('nanite'):
                triangle_text = f"Nanite {asset['nanite_triangles']}; fallback {triangle_text}"
            lod_count = asset.get('lod_count', len(asset.get('lods', [])))
            self.table.insert('', 'end', iid=str(index), values=(asset['id'], state_text, lod_count,
                                                                triangle_text), tags=(state,))
            self.asset_details[str(index)] = asset

    def _select_asset(self, event=None):
        selected = self.table.selection()
        if selected:
            self._log(json.dumps(self.asset_details[selected[0]], ensure_ascii=False, indent=2))

    def execute(self, action):
        if self.in_action:
            return
        self.in_action = True
        self._buttons(True)
        try:
            self.state_label.configure(text='Проверка и подготовка…')
            self.root.update_idletasks()
            snapshot = self._snapshot()
            if action in ('cleanup_plan', 'cleanup'):
                stage = self.variables['cleanup_run_id'].get().strip()
                report = self.api.plan_cleanup(snapshot, stage) if action=='cleanup_plan' else self.api.cleanup_staging(snapshot, stage)
                self._rows(report['assets'])
                self.summary.configure(text=f"Staging: удалить {report['delete_count']}, сохранить {report['retained_count']}")
                self._log(json.dumps(report, ensure_ascii=False, indent=2))
                if action=='cleanup':
                    self.run_id = report['run_id']
            elif action == 'review_bundle':
                report = self.api.create_review_bundle(self.variables['review_media_run_ids'].get())
                self.run_id = report['run_id']
                self.state_label.configure(text=f"Просмотр: {report['model_count']} моделей, {report['frame_count']} кадров")
                self._log(json.dumps(report, ensure_ascii=False, indent=2))
            elif action == 'candidate':
                selected = self.queue_table.selection()
                report = self.api.create_review_candidate(selected[0] if selected else self.run_id)
                self.load_profile(report['profile_path'])
                self.run_id = report['run_id']
                self.state_label.configure(text=f"Все модели: {len(report['accepted_ids'])}; с замечаниями {len(report['issues'])}; не импортированы {len(report['blocking_ids'])}")
                self._log(json.dumps(report, ensure_ascii=False, indent=2))
            elif action == 'delivery_plan':
                report = self.api.plan_delivery(snapshot)
                self._log(json.dumps(report, ensure_ascii=False, indent=2))
                self.state_label.configure(text='План поставки готов' if report['ready'] else 'Поставка заблокирована: см. отчёт')
            elif action in ('delivery', 'combined_delivery'):
                if action == 'combined_delivery':
                    companion = self.variables['combined_profile_path'].get().strip()
                    if not companion:
                        raise ValueError('Укажите JSON-профиль второго типа с тем же корнем Content.')
                    report = self.api.create_combined_delivery([snapshot, companion])
                else:
                    report = self.api.create_delivery(snapshot)
                self.run_id = report['run_id']
                if report['status']=='passed':
                    self.variables['delivery_run_id'].set(report['run_id'])
                self._log(json.dumps(report, ensure_ascii=False, indent=2))
            elif action == 'delivery_verify':
                self.run_id = self.api.start_delivery_verification(self.variables['delivery_run_id'].get().strip())
                self._log('Запущен отдельный Unreal для проверки чистого проекта: '+self.run_id)
            elif action == 'delivery_cook':
                self.run_id=self.api.start_cook(self.variables['delivery_run_id'].get().strip())
                self._log('Запущена проверка cooking для Windows: '+self.run_id)
            elif action == 'delivery_package':
                report = self.api.package_delivery(self.variables['delivery_run_id'].get().strip())
                self._log(json.dumps(report, ensure_ascii=False, indent=2))
                self.state_label.configure(text='ZIP создан: '+report['zip_path'])
            elif action == 'plan':
                self.progress['value'] = 0
                result = self.api.plan(snapshot)
                self._rows(result['assets'])
                expected = result['expected']
                self.summary.configure(text=f"План: {expected['meshes']} мешей × {expected['lods_per_mesh']} LOD • "
                                            f"{expected['instances']} MI • {expected['textures']} текстур • "
                                            f"пропуск {result['incremental_summary']['skip']}, обработка {result['incremental_summary']['process']}")
                self._log('Проверка исходников: ' + ('готово к импорту.' if result['ready'] else 'конфликт назначения.'))
                if result.get('excluded_sources'):
                    self._log('Исключены до импорта: '+json.dumps(result['excluded_sources'], ensure_ascii=False))
                if result['conflicts']:
                    self._log('\n'.join(result['conflicts']))
                self.state_label.configure(text='Исходники проверены' if result['ready'] else 'Импорт заблокирован: конфликт ассетов')
            elif action == 'start':
                self.run_id = self.api.start(snapshot)
                self._log(f'Запущен импорт: {self.run_id}')
                self._poll(force=True)
            elif action == 'settings':
                self.run_id = self.api.start_settings(snapshot)
                self._log(f'Обновление материалов и настроек: {self.run_id}')
                self.tabs.select(self.results_tab)
            elif action == 'open_flythrough':
                report=self.api.open_flythrough(self.variables['flight_run_id'].get().strip())
                self._log(json.dumps(report,ensure_ascii=False))
            elif action == 'flythrough':
                self.run_id=self.api.start_flythrough(snapshot)
                self.variables['flight_run_id'].set(self.run_id)
                self._log('Непрерывный MRQ-пролёт: '+self.run_id)
            elif action == 'media':
                self.run_id=self.api.start_media(snapshot)
                self._log('Предметные кадры: '+self.run_id)
            elif action == 'auto_lod':
                self.run_id=self.api.start_media(snapshot,automatic_lod=True)
                self._log('Автоматический выбор LOD: '+self.run_id)
            elif action == 'previews':
                self.run_id = self.api.start_previews(snapshot)
                self._log(f'Экспорт превью: {self.run_id}')
                self.tabs.select(self.results_tab)
            elif action == 'source_diagnostics':
                report = self.api.analyze_sources(snapshot)
                self.run_id = report['run_id']
                self._poll(force=True)
                self._log('Анализ исходных экспортов завершён. Выберите модель или откройте Markdown-отчёт.')
            elif action == 'import_diagnostics':
                self.run_id = self.api.start_diagnostics(snapshot)
                self._log('Запущено сравнение импорта в отдельной диагностической папке.')
                self._poll(force=True)
            elif action in ('overview', 'lod_review'):
                report = self.api.create_overview(snapshot, action == 'lod_review')
                if report['status'] == 'passed':
                    self.scene_lod_review = action == 'lod_review'
                self.run_id = report['run_id']
                self._poll(force=True)
                self._log('Карта: ' + report.get('map_path', report.get('error', 'создание не завершено')))
                if report.get('diagnostic'):
                    self._log('Диагностическая сцена: у части мешей есть ошибки. Публикация не разрешена.')
            elif action == 'open_overview':
                result = self.api.open_overview(snapshot)
                self.scene_lod_review = False
                self.state_label.configure(text='Открыта карта: ' + result['map_path'])
                self._log('Камера обзора активирована.')
            elif action == 'validate_overview':
                result = self.api.validate_overview(snapshot, self.scene_lod_review)
                self._rows(result['assets'])
                self.summary.configure(text=f"Сцена: {result['owned_actor_count']}/{result['expected_actor_count']} объектов")
                self.state_label.configure(text='Структура сцены проверена' if result['passed'] else 'Ошибка проверки сцены')
                self._log(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                result = self.api.validate(snapshot)
                self._rows(result['assets'])
                self._log('Проверка ассетов: ' + ('пройдена.' if result['passed'] else 'есть ошибки — выберите модель.'))
                self.state_label.configure(text='Проверка пройдена • визуальный просмотр требуется' if result['passed'] else 'Проверка выявила ошибки')
            self.tabs.select(self.results_tab)
        except Exception as error:
            self._callback_error(type(error), error, error.__traceback__)
        finally:
            self.in_action = False
            self._buttons(bool(self.api.readiness()['active_run']))

    def open_updates(self):
        from . import ui
        ui.open_updates()

    def _buttons(self, running):
        for button in self.action_buttons + self.scene_buttons + self.diagnostic_buttons + self.preview_buttons + self.delivery_buttons + [self.settings_button,self.media_button,self.auto_lod_button,self.flythrough_button,self.flythrough_open_button]:
            button.configure(state='disabled' if running else 'normal')
        self.cancel_button.configure(state='normal' if running else 'disabled')
        self.resume_button.configure(state='disabled' if running else 'normal')

    def refresh_queue(self):
        from datetime import datetime
        for row in self.queue_table.get_children():
            self.queue_table.delete(row)
        for report in self.api.list_runs(30):
            started = report.get('started_at')
            when = datetime.fromtimestamp(started).strftime('%Y-%m-%d %H:%M') if started else ''
            self.queue_table.insert('', 'end', iid=report['run_id'], values=(report['run_id'],
                                 report['kind'], report['status'], when))

    def resume_selected(self):
        selected = self.queue_table.selection()
        if not selected:
            self._log('Выберите запуск в таблице.')
            return
        try:
            self.run_id = self.api.resume(selected[0])
            self.tabs.select(self.results_tab)
            self._log(f'Продолжение {selected[0]} → {self.run_id}')
            self._poll(force=True)
        except Exception as error:
            self._callback_error(type(error), error, error.__traceback__)

    def cancel(self):
        self.ai_cancel()
        session = getattr(self, 'guide_session', None)
        if session and not session.done:
            session.cancel()
        active = self.api.readiness()['active_run']
        if active:
            self.api.cancel(active)
            self.state_label.configure(text='Остановка после текущей модели…')
            self._log('Запрошена остановка. Завершённые ассеты сохраняются.')

    def _poll(self, force=False):
        now = time.monotonic()
        if not force and now - self.last_poll < 0.5:
            return
        self.last_poll = now
        active = self.api.readiness()['active_run']
        self._buttons(bool(active) or self.in_action)
        if active:
            self.run_id = active
        if not self.run_id:
            return
        if not active and self.run_id == getattr(self, '_logged_run', None):
            return
        report = self.api.status(self.run_id)
        self._display_report(report)

    def _display_report(self, report):
        """Apply an already fetched report; safe for a cached external snapshot."""
        assets = report['assets']
        finished = sum(a['status'] in ('passed', 'failed', 'cancelled', 'skipped') for a in assets)
        self.progress['value'] = 100 * finished / max(1, len(assets))
        self.report_path = Path(report['report_path'])
        summary = f"{report['status']} • {finished}/{len(assets)} моделей • " + self.run_id[:8]
        if report.get('kind') in ('source_diagnostics', 'import_diagnostics'):
            issues = sum(not a['source_quality_passed'] for a in report['source_analysis']['assets'])
            summary = f"Диагностика {report['status']} • {finished}/{len(assets)} проверок • моделей с замечаниями: {issues}"
        self.state_label.configure(text=summary)
        # Rebuild rows only when their state/values changed, preserving selection
        # otherwise so details can be read while polling.
        signature = json.dumps(assets, sort_keys=True)
        if signature != getattr(self, '_last_assets', None):
            self._rows(assets)
            self.summary.configure(text=summary + ' • выберите модель для подробностей')
            self._last_assets = signature
        if report['status'] != 'running' and self.run_id != getattr(self, '_logged_run', None):
            self._log(f"Задача {report['status']}. Отчёт: {self.report_path}")
            self._logged_run = self.run_id

    def open_reports(self):
        folder = self.report_path.parent if self.report_path else self.saved / 'Runs'
        folder.mkdir(parents=True, exist_ok=True)
        import unreal
        unreal.SystemLibrary.launch_url(folder.as_uri())

    def _tick(self, delta):
        if self.closed or self.in_action or getattr(self, '_pumping', False):
            return
        self._pumping = True
        try:
            self.root.update_idletasks()
            self.root.update()
            if not self.closed:
                self.ai_settings_poll()
                self.ai_poll()
                self._poll()
                session = getattr(self, 'guide_session', None)
                if session and not session.done:
                    session.tick()
                    self.state_label.configure(text=session.label)
        except self.tk.TclError:
            self.close(prompt=False)
        except Exception as error:
            self._callback_error(type(error), error, error.__traceback__)
        finally:
            self._pumping = False

    def close(self, prompt=True):
        if self.closed:
            return
        if prompt and self.dirty:
            from tkinter import messagebox
            if not messagebox.askyesno('Несохранённый профиль', 'Закрыть окно без сохранения настроек? Текущий импорт продолжится.', parent=self.root):
                return
        self.closed = True
        if self.tick_handle is not None:
            import unreal
            unreal.unregister_slate_post_tick_callback(self.tick_handle)
            self.tick_handle = None
        self.root.destroy()
