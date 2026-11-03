"""Shared delivery controls and review-before-delete for owned imported content."""
import json
import uuid


class FinalWindow:
    def scan_content(self):
        from . import dark_dialog as dd
        external = getattr(self, 'external', False)
        def fetch():
            from collections import Counter
            if self.api.readiness()['active_run']:
                raise RuntimeError('Дождитесь завершения задачи.')
            if external:
                return self.api.content_folders()
            import unreal as u
            assets = u.EditorAssetLibrary.list_assets('/Game', recursive=True, include_folder=False)
            return Counter('/'.join(str(path).split('.') [0].split('/')[:3]) for path in assets if len(str(path).split('/'))>3)
        dialog = dd.Dialog(self.root, 'Content · Выберите папку для очистки', 780, 540, minsize=(620, 420),
                           loading='Сканирование папок Content…')
        def build(counts):
            t, body = self.ttk, dialog.content
            head = self.tk.Frame(body, bg=dd.BG)
            head.pack(fill='x', padx=20, pady=(16, 0))
            t.Label(head, text='Папки текущего проекта', style='Hero.TLabel').pack(anchor='w')
            t.Label(head, text='Выбор не зависит от профиля. На следующем шаге будет список удаления.\n'
                    'Presentation защищена. Исходники на диске и поставки не удаляются.', style='Subtitle.TLabel').pack(anchor='w', pady=(4, 0))
            bar = self.tk.Frame(body, bg=dd.PANEL)
            bar.pack(fill='x', side='bottom')
            table = t.Treeview(body, columns=('folder','count'), show='headings', selectmode='browse')
            table.heading('folder', text='Content / папка'); table.heading('count', text='Ассетов')
            table.column('folder', width=540); table.column('count', width=100, anchor='e')
            table.pack(fill='both', expand=True, padx=20, pady=14)
            for root, count in sorted(counts.items()):
                table.insert('', 'end', iid=root, values=(root, count))
            if not counts:
                table.insert('', 'end', values=('В /Game нет ассетов', ''))
            def select(event=None):
                selected = table.selection()
                if selected and selected[0] in counts:
                    root = selected[0]
                    self.review_import_cleanup(root, root.rsplit('/',1)[-1], True)
            open_plan = dd.button(bar, 'Просмотреть план очистки выбранной папки…', select, accent=True)
            open_plan.pack(side='left', padx=16, pady=12)
            dd.enable(open_plan, False)
            table.bind('<<TreeviewSelect>>', lambda event: dd.enable(
                open_plan, bool(table.selection()) and table.selection()[0] in counts))
            table.bind('<Double-1>', select)
            dd.button(bar, 'Закрыть', dialog.close).pack(side='right', padx=16, pady=12)
        dialog.load(fetch, build, threaded=external)

    def build_final_options(self, parent):
        t = self.ttk
        box = t.LabelFrame(parent, text='Итоговый проект и файлы', padding=8)
        box.pack(fill='x', pady=8)
        t.Checkbutton(box, text='После подготовки: чистый проект → проверка отдельным Unreal → ZIP + готовые PNG',
                      variable=self.guide_finalize).pack(anchor='w')
        row = t.Frame(box)
        row.pack(fill='x', pady=6)
        t.Label(row, text='Каталог вывода').pack(side='left', padx=(0, 10))
        t.Entry(row, textvariable=self.variables['delivery_output_directory']).pack(side='left', fill='x', expand=True)
        t.Button(row, text='Обзор…', command=self.browse_final_output).pack(side='left', padx=6)
        t.Label(box, text='Пусто — Saved/AssetPackPipeline/Deliveries. Каждый запуск в новой папке.\n'
                'FinalProject / дата-время / ИмяПака_Project и ИмяПака_Renders. LOD и Nanite — в одном проекте.',
                style='Muted.TLabel').pack(anchor='w')
        row = t.Frame(box)
        row.pack(fill='x', pady=6)
        t.Button(row, text='Очистить импортированный пак…', command=self.review_import_cleanup).pack(side='left')
        t.Button(row, text='Запустить этап 4 для подготовленных мешей', command=self.final_only).pack(side='left', padx=8)
        if parent is getattr(self, 'delivery_tab', None):
            return  # Render-only uses the quick-start «3. Изображения» settings.
        t.Button(row, text='Рендер и вывод финальных моделей', style='Accent.TButton',
                 command=self.render_only).pack(side='left')
        t.Label(box, text='Рендер берёт настройки из «3. Изображения» для уже импортированных мешей; общая папка PNG и ZIP '
                'сохраняются в каталог вывода (пусто — Saved/AssetPackPipeline/RenderExports).',
                style='Muted.TLabel', wraplength=900).pack(anchor='w')

    def browse_final_output(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self.root, title='Каталог итогового проекта, ZIP и рендеров')
        if path:
            self.variables['delivery_output_directory'].set(path)

    def final_only(self):
        try:
            if self.api.readiness()['active_run'] or getattr(self, 'guide_session', None) and not self.guide_session.done:
                raise RuntimeError('Сначала завершите текущую задачу.')
            from . import guided
            if self.mode.get() == 'Профессиональный':
                paths = {'Current': self._snapshot()}
                other = self.variables['combined_profile_path'].get().strip()
                if other:
                    paths['Companion'] = other
            else:
                profiles, _ = self.guide_plan()
                folder = self.saved/'UI'/'Final'/uuid.uuid4().hex
                folder.mkdir(parents=True)
                paths = {}
                for name, profile in profiles.items():
                    path = folder/(name+'.json')
                    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
                    paths[name] = str(path)
            key = next(iter(paths))
            session = guided.Session(self.api, paths, [(key, op) for op in ('delivery', 'verify_delivery', 'package')])
            if self.mode.get() == 'Профессиональный':
                import re
                ids = list(dict.fromkeys(filter(None, re.split(r'[,;\s]+', self.variables['review_media_run_ids'].get().strip()))))
                for run_id in ids:
                    report = self.api.status(run_id)
                    if report.get('kind') not in ('preview_export', 'individual_previews') or report['status'] != 'passed':
                        raise ValueError('Для копирования PNG нужен завершённый запуск превью: '+run_id)
                    profile = report['manifest']['profile']
                    from .discovery import read_json
                    expected = read_json(next(iter(paths.values())))
                    if profile['pack_id'] != expected['pack_id'] or profile['destination_root'] != expected['destination_root']:
                        raise ValueError('Рендеры относятся к другому паку: '+run_id)
                    session.render_runs.append(report)
            # Existing completed captures from this window can be included without rerendering.
            previous = getattr(self, 'guide_session', None)
            if previous and set(previous.paths) == set(paths):
                from .discovery import read_json
                same = all(read_json(previous.paths[k])['destination_root'] == read_json(paths[k])['destination_root'] and
                           read_json(previous.paths[k])['pack_id'] == read_json(paths[k])['pack_id'] for k in paths)
                if same:
                    known = {r['run_id'] for r in session.render_runs}
                    session.render_runs.extend(r for r in previous.render_runs if r['run_id'] not in known)
            self.guide_session = session
        except Exception as error:
            self._callback_error(type(error), error, error.__traceback__)

    def _render_plan(self, kind):
        """Profiles from the quick-start form plus the stage-4 render-only steps."""
        from . import guided
        profiles, steps = self.guide_plan()
        folder = self.saved/'UI'/kind/uuid.uuid4().hex
        folder.mkdir(parents=True)
        paths = {}
        for name, profile in profiles.items():
            path = folder/(name+'.json')
            path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
            paths[name] = str(path)
        return paths, guided.render_steps(steps)

    def render_only(self):
        try:
            if self.api.readiness()['active_run'] or getattr(self, 'guide_session', None) and not self.guide_session.done:
                raise RuntimeError('Сначала завершите текущую задачу.')
            from . import guided
            paths, steps = self._render_plan('Renders')
            self.guide_session = guided.Session(self.api, paths, steps)
            self._log('Рендер финальных моделей: '+', '.join(v+' · '+op for v, op in steps))
        except Exception as error:
            self._callback_error(type(error), error, error.__traceback__)

    def review_import_cleanup(self, selected_root=None, selected_pack=None, folder_scope=False):
        from . import cleanup, dark_dialog as dd
        external = getattr(self, 'external', False)
        pack = selected_pack or self.variables['pack_id'].get().strip()
        root = selected_root or (self.variables['destination_root'].get().strip().rstrip('/') if self.mode.get() == 'Профессиональный' else '/Game/'+pack)
        manifest = {'profile': {'pack_id':pack, 'destination_root':root}}
        def fetch():
            if self.api.readiness()['active_run'] or getattr(self, 'guide_session', None) and not self.guide_session.done:
                raise RuntimeError('Завершите текущую задачу перед очисткой.')
            return (self.api.plan_imported_cleanup(manifest,folder_scope=folder_scope) if external
                    else cleanup.plan(manifest, imported=True, folder_scope=folder_scope))
        holder = dd.Dialog(self.root, 'План очистки импортированного пака', 940, 620, minsize=(700, 460),
                           loading='Составление плана очистки…')
        dialog = holder.window
        def build(proposal):
            body = holder.content
            summary = self.tk.Frame(body, bg=dd.BG)
            summary.pack(fill='x', padx=20, pady=(16, 8))
            self.ttk.Label(summary, text=f"{pack}  ·  {root}", style='Hero.TLabel').pack(anchor='w')
            self.ttk.Label(summary, text=f"Удалить: {proposal['delete_count']}   ·   Сохранить: {proposal['retained_count']}",
                           style='Subtitle.TLabel').pack(anchor='w', pady=(4, 0))
            if folder_scope:
                self.tk.Label(summary, text='Режим очистки папки Content: включены поддерживаемые ассеты БЕЗ меток плагина.',
                              bg=dd.BG, fg='#ffb36b', anchor='w', font=('Segoe UI', 10)).pack(anchor='w', pady=(6, 0))
            bar = self.tk.Frame(body, bg=dd.PANEL)
            bar.pack(fill='x', side='bottom')
            frame = self.tk.Frame(body, bg=dd.BG)
            frame.pack(fill='both', expand=True, padx=20, pady=(4, 14))
            text = self.tk.Text(frame, wrap='word', bg='#14171d', fg='#bbc7dd', padx=12, pady=12, relief='flat',
                                borderwidth=0, highlightthickness=0, font=('Consolas', 10), insertbackground='#bbc7dd')
            scroll = self.ttk.Scrollbar(frame, orient='vertical', command=text.yview)
            text.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right', fill='y')
            text.pack(side='left', fill='both', expand=True)
            text.tag_configure('delete', foreground='#ff9d9d')
            text.tag_configure('keep', foreground='#9cdbb2')
            text.tag_configure('muted', foreground='#8f98aa')
            text.insert('end', 'Текущая открытая карта и ассеты с внешними ссылками сохраняются. Для полной очистки сначала откройте L_Presentation.\n'
                        'Перед удалением создаётся резервная копия в Saved/AssetPackPipeline/ImportedCleanup. '
                        'Исходные FBX/GLB, поставки и PNG не затрагиваются.\n\n', 'muted')
            for row in proposal['assets']:
                text.insert('end', 'УДАЛИТЬ    ' if row['can_delete'] else 'СОХРАНИТЬ  ', 'delete' if row['can_delete'] else 'keep')
                text.insert('end', row['id']+' — '+row['reason']+'\n')
            text.configure(state='disabled')
            def apply():
                if not dd.confirm(dialog, 'Подтверждение удаления',
                                  f"Удалить {proposal['delete_count']} перечисленных ассетов из {root}?\n\n"
                                  'Перед удалением будет создана резервная копия.', ok_text='Удалить', danger=True):
                    return
                try:
                    if self.api.readiness()['active_run'] or getattr(self, 'guide_session', None) and not self.guide_session.done:
                        raise RuntimeError('Сейчас выполняется задача.')
                    folder = self.saved/'ImportedCleanup'/uuid.uuid4().hex
                    folder.mkdir(parents=True)
                    (folder/'plan.json').write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding='utf-8')
                    result = self.api.execute_imported_cleanup(manifest,str(folder/'backup'),expected=proposal['delete_packages'],folder_scope=folder_scope) if getattr(self,'external',False) else cleanup.execute(manifest, folder/'backup', imported=True, expected=proposal['delete_packages'], folder_scope=folder_scope)
                    (folder/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                    self._log('Очистка импортированного пака: '+str(folder))
                    self.state_label.configure(text=f"Удалено: {result['deleted_count']}; сохранено: {result['retained_count']}")
                    holder.close()
                except Exception as error:
                    self._callback_error(type(error), error, error.__traceback__)
            delete = dd.button(bar, 'Удалить перечисленные ассеты…', apply, danger=True)
            delete.pack(side='left', padx=16, pady=12)
            dd.enable(delete, bool(proposal['delete_count']))
            dd.button(bar, 'Закрыть', holder.close).pack(side='right', padx=16, pady=12)
        holder.load(fetch, build, threaded=external)
