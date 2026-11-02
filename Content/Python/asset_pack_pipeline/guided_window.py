"""Compact start screen and deterministic wizard for the existing editor window."""
import json
import uuid
from pathlib import Path
from . import guided
from .assistant_window import AssistantWindow
from .final_window import FinalWindow


class GuidedWindow(AssistantWindow, FinalWindow):
    def build_guided(self, shell):
        t, tk = self.ttk, self.tk
        self.mode = tk.StringVar(value='Быстрый старт')
        modes = t.Frame(shell, padding=(0, 8))
        modes.pack(fill='x', before=self.tabs)
        for name in ('Быстрый старт', 'Мастер', 'Профессиональный'):
            t.Radiobutton(modes, text=name, value=name, variable=self.mode,
                          command=self.switch_mode).pack(side='left', padx=(0, 24))
        from .scroll_page import ScrollPage
        self.guided_frame = ScrollPage(shell)
        body = self.guided_frame.content
        self.guided_frame.pack(fill='both', expand=True, before=self.tabs)
        self.guide_title = t.Label(body, text='', style='Hero.TLabel')
        self.guide_title.pack(anchor='w', pady=(0, 8))
        self.guide_hint = t.Label(body, text='', wraplength=950, style='Muted.TLabel')
        self.guide_hint.pack(anchor='w', pady=(0, 12))
        self.guide_groups = []
        self.guide_variants = tk.StringVar(value='LOD + MID / Nanite')
        self.guide_lod = tk.StringVar(value='0')
        self.guide_finalize = tk.BooleanVar(value=True)
        self.guide_renders = {name: tk.BooleanVar(value=name == 'overview')
                              for name in ('overview', 'MID', 'LOW', 'LODS', 'selected')}
        # Quick start: 1 and 2 stacked left, 3 on the right, 4 full width below.
        self.guide_grid = t.Frame(body)
        self.guide_grid.pack(fill='x')
        self.guide_grid.columnconfigure((0, 1), weight=1, uniform='guide')
        for title in ('1. Исходники', '2. Меши', '3. Изображения', '4. Итоговая поставка'):
            group = t.LabelFrame(self.guide_grid, text=title, padding=14)
            self.guide_groups.append(group)
        source, meshes, renders, review = self.guide_groups
        for row, (label, key) in enumerate((('Папка с FBX / GLB', 'source_root'), ('Название пака', 'pack_id'))):
            t.Label(source, text=label).grid(row=row, column=0, sticky='w', padx=(0, 18), pady=6)
            t.Entry(source, textvariable=self.variables[key]).grid(row=row, column=1, sticky='ew', pady=6)
        source.columnconfigure(1, weight=1)
        t.Button(source, text='Выбрать папку…', command=self.browse_source).grid(row=0, column=2, padx=(10, 0))
        t.Label(source, text='Предпочтительный формат').grid(row=2, column=0, sticky='w', pady=6)
        t.Combobox(source, textvariable=self.variables['source_format'], values=('FBX', 'GLB'),
                   state='readonly', width=10).grid(row=2, column=1, sticky='w')
        t.Label(meshes, text='Какие версии подготовить?').pack(side='left', padx=(0, 18))
        t.Combobox(meshes, textvariable=self.guide_variants, state='readonly', width=28,
                   values=('LOD + MID / Nanite', 'Только LOD', 'Только MID / Nanite')).pack(side='left')
        for key, label in (('overview', 'Один общий кадр'), ('MID', 'Каждый MID'), ('LOW', 'Каждый LOW (LOD0)'),
                           ('LODS', 'Каждый LOD'), ('selected', 'Один выбранный LOD у каждой модели')):
            t.Checkbutton(renders, text=label, variable=self.guide_renders[key]).pack(anchor='w', pady=3)
        line = t.Frame(renders)
        line.pack(fill='x', pady=(8, 0))
        t.Label(line, text='Номер выбранного LOD (0 — самый подробный):').pack(side='left')
        t.Spinbox(line, from_=0, to=4, width=4, textvariable=self.guide_lod).pack(side='left', padx=10)
        self.build_final_options(review)
        self.build_final_options(self.delivery_tab)
        self.guide_summary = tk.Text(review, height=4, bg='#14171d', fg='#bbc7dd', relief='flat', wrap='word',
                                     padx=12, pady=12, state='disabled')
        self.guide_summary.pack(fill='both', expand=True)
        self.guide_nav = t.Frame(self.controls_frame)
        t.Button(self.guide_nav, text='Назад', command=lambda: self.guide_move(-1)).pack(side='left')
        t.Button(self.guide_nav, text='Далее', command=lambda: self.guide_move(1)).pack(side='right')
        self.guide_actions = t.Frame(self.controls_frame)
        self.guide_actions.pack(fill='x',pady=(0,10),before=self.state_label)
        t.Button(self.guide_actions, text='Проверить исходники', command=lambda: self.guide_run(False)).pack(side='left')
        t.Button(self.guide_actions, text='Подготовить меши и сцены', style='Accent.TButton',
                 command=lambda: self.guide_run(True)).pack(side='left', padx=10)
        t.Button(self.guide_actions, text='Результаты', command=self.guide_results).pack(side='right')
        t.Button(self.guide_actions, text='Остановить', command=self.cancel).pack(side='right', padx=10)
        self.guide_step = 0
        self.build_assistant(body)
        self.switch_mode()

    def switch_mode(self):
        pro = self.mode.get() == 'Профессиональный'
        self.tabs.pack_forget()
        self.guided_frame.pack_forget()
        self.expert_actions.pack_forget()
        self.guide_actions.pack_forget()
        self.guide_nav.pack_forget()
        if pro:
            self.tabs.pack(fill='both', expand=True)
            self.expert_actions.pack(fill='x',before=self.state_label)
        else:
            self.guided_frame.pack(fill='both', expand=True)
            self.guide_actions.pack(fill='x',pady=(0,10),before=self.state_label)
            self.guide_move(0)

    def guide_move(self, delta):
        self.guide_step = max(0, min(3, self.guide_step+delta))
        wizard = self.mode.get() == 'Мастер'
        self.ai_frame.pack_forget()
        titles = ('Откуда взять модели?', 'Выберите состав пака', 'Какие изображения нужны?', 'Итоговая поставка и план')
        self.guide_title.configure(text=(f'Шаг {self.guide_step+1} из 4 · '+titles[self.guide_step]) if wizard else 'Подготовка пака')
        self.guide_hint.configure(text='Все модели из папки. Материалы и LOD настраиваются скриптами. MID, иначе HIGH — источник Nanite. '
                                  'Геометрические замечания сохраняются в отчёте; модели не исключаются.')
        quick = ((0, 0, 1, 1), (1, 0, 1, 1), (0, 1, 2, 1), (2, 0, 1, 2))  # row, column, rowspan, columnspan
        for i, group in enumerate(self.guide_groups):
            group.grid_forget()
            if wizard and i == self.guide_step:
                group.grid(row=0, column=0, columnspan=2, sticky='nsew', pady=(0, 10))
            elif not wizard:
                row, column, rowspan, columnspan = quick[i]
                group.grid(row=row, column=column, rowspan=rowspan, columnspan=columnspan, sticky='nsew',
                           padx=(0, 10) if column == 0 and columnspan == 1 else 0, pady=(0, 10))
        if wizard:
            self.guide_nav.pack(fill='x',pady=(0,10),before=self.guide_actions)
        else:
            self.guide_nav.pack_forget()
        if wizard and self.guide_step == 3:
            try:
                profiles, steps = self.guide_plan()
                content = '\n'.join([f"{len(profiles)} версии · {len(steps)} этапов", 'Все модели из выбранной папки',
                                      'Назначение: /Game/'+self.variables['pack_id'].get(), '']+
                                     [f'{v}: {op}' for v, op in steps]+['', 'После подготовки: чистый проект → проверка → ZIP.',
                                      'AI использует текущие настройки окна; запуск выполняется скриптами плагина.'])
            except Exception as error:
                content = str(error)
            self.guide_summary.configure(state='normal')
            self.guide_summary.delete('1.0', 'end')
            self.guide_summary.insert('end', content)
            self.guide_summary.configure(state='disabled')
        if wizard:
            self.ai_frame.pack(fill='both', expand=True, pady=(8, 0))

    def guide_plan(self):
        variants = {'LOD + MID / Nanite': 'both', 'Только LOD': 'LOD', 'Только MID / Nanite': 'Nanite'}
        return guided.prepare(self.base, self.variables['source_root'].get(), self.variables['pack_id'].get().strip(),
                              self.variables['source_format'].get(), variants[self.guide_variants.get()],
                              [k for k, v in self.guide_renders.items() if v.get()], int(self.guide_lod.get()),
                              self.guide_finalize.get(), self.variables['delivery_output_directory'].get().strip())

    def guide_run(self, start, raise_errors=False):
        try:
            if self.api.readiness()['active_run'] or getattr(self, 'guide_session', None) and not self.guide_session.done:
                raise RuntimeError('Дождитесь завершения текущей задачи.')
            profiles, steps = self.guide_plan()
            folder = self.saved/'UI'/'Guided'/uuid.uuid4().hex
            folder.mkdir(parents=True)
            paths = {}
            for variant, profile in profiles.items():
                path = folder/(variant+'.json')
                path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
                paths[variant] = str(path)
                plan = self.api.plan(str(path))
                if not plan['ready']:
                    raise RuntimeError(variant+': '+str(plan.get('conflicts', 'исходники не готовы')))
                self._log(f"{variant}: {len(plan['assets'])} моделей; профиль {path}")
            self.state_label.configure(text='Исходники проверены • '+str(folder))
            if start:
                self.guide_session = guided.Session(self.api, paths, steps)
            return {'status': 'started' if start else 'sources_checked', 'variants': list(profiles),
                    'steps': len(steps), 'completed': False}
        except Exception as error:
            self._callback_error(type(error), error, error.__traceback__)
            if raise_errors:
                raise

    def guide_results(self):
        self.mode.set('Профессиональный')
        self.switch_mode()
        self.tabs.select(self.results_tab)
