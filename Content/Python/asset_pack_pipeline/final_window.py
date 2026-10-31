"""Shared delivery controls and review-before-delete for owned imported content."""
import json
import uuid


class FinalWindow:
    def scan_content(self):
        try:
            from collections import Counter
            if self.api.readiness()['active_run']:
                raise RuntimeError('Дождитесь завершения задачи.')
            if getattr(self,'external',False):
                counts=self.api.content_folders()
            else:
                import unreal as u
                assets = u.EditorAssetLibrary.list_assets('/Game', recursive=True, include_folder=False)
                counts = Counter('/'.join(str(path).split('.') [0].split('/')[:3]) for path in assets if len(str(path).split('/'))>3)
            dialog = self.tk.Toplevel(self.root)
            dialog.title('Content · Выберите папку для очистки')
            dialog.geometry('760x520')
            dialog.configure(bg='#20232b')
            dialog.transient(self.root)
            self.ttk.Label(dialog, text='Папки текущего проекта', style='Hero.TLabel').pack(anchor='w', padx=18, pady=18)
            self.ttk.Label(dialog, text='Выбор не зависит от профиля. На следующем шаге будет список удаления.\n'
                'Presentation защищена. Исходники на диске и поставки не удаляются.', style='Muted.TLabel').pack(anchor='w', padx=18)
            table = self.ttk.Treeview(dialog, columns=('folder','count'), show='headings', selectmode='browse')
            table.heading('folder', text='Content / папка'); table.heading('count', text='Ассетов')
            table.column('folder', width=520); table.column('count', width=100)
            table.pack(fill='both', expand=True, padx=18, pady=12)
            for root, count in sorted(counts.items()):
                table.insert('', 'end', iid=root, values=(root, count))
            def select():
                selected = table.selection()
                if selected:
                    root = selected[0]
                    self.review_import_cleanup(root, root.rsplit('/',1)[-1], True)
            self.ttk.Button(dialog, text='Просмотреть план очистки выбранной папки…', command=select).pack(anchor='w', padx=18, pady=12)
        except Exception as error:
            self._callback_error(type(error), error, error.__traceback__)

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
                'LOD и Nanite входят в один проект; PNG и Renders.zip сохраняются рядом с ZIP проекта.',
                style='Muted.TLabel').pack(anchor='w')
        row = t.Frame(box)
        row.pack(fill='x', pady=6)
        t.Button(row, text='Очистить импортированный пак…', command=self.review_import_cleanup).pack(side='left')
        t.Button(row, text='Запустить этап 4 для подготовленных мешей', command=self.final_only).pack(side='left', padx=8)

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

    def review_import_cleanup(self, selected_root=None, selected_pack=None, folder_scope=False):
        try:
            if self.api.readiness()['active_run'] or getattr(self, 'guide_session', None) and not self.guide_session.done:
                raise RuntimeError('Завершите текущую задачу перед очисткой.')
            from . import cleanup
            pack = selected_pack or self.variables['pack_id'].get().strip()
            root = selected_root or (self.variables['destination_root'].get().strip().rstrip('/') if self.mode.get() == 'Профессиональный' else '/Game/'+pack)
            manifest = {'profile': {'pack_id':pack, 'destination_root':root}}
            proposal = self.api.plan_imported_cleanup(manifest,folder_scope=folder_scope) if getattr(self,'external',False) else cleanup.plan(manifest, imported=True, folder_scope=folder_scope)
            dialog = self.tk.Toplevel(self.root)
            dialog.title('План очистки импортированного пака')
            dialog.geometry('900x580')
            dialog.transient(self.root)
            text = self.tk.Text(dialog, wrap='word', bg='#14171d', fg='#bbc7dd', padx=12, pady=12)
            text.pack(fill='both', expand=True)
            text.insert('end', f"Пак: {pack}\nКаталог: {root}\nУдалить: {proposal['delete_count']}; сохранить: {proposal['retained_count']}\n\n"
                + ('ВНИМАНИЕ: выбран режим очистки папки Content. Включены поддерживаемые ассеты БЕЗ меток плагина.\n\n' if folder_scope else '') +
                'Текущая открытая карта и ассеты с внешними ссылками сохраняются. Для полной очистки сначала откройте L_Presentation.\n'
                'Перед удалением создаётся резервная копия в Saved/AssetPackPipeline/ImportedCleanup. Исходные FBX/GLB, поставки и PNG не затрагиваются.\n\n'+
                '\n'.join(('УДАЛИТЬ  ' if row['can_delete'] else 'СОХРАНИТЬ  ')+row['id']+' — '+row['reason'] for row in proposal['assets']))
            text.configure(state='disabled')
            def apply():
                from tkinter import messagebox
                if not messagebox.askyesno('Подтверждение удаления', f"Удалить {proposal['delete_count']} перечисленных ассетов из {root}?", parent=dialog):
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
                    dialog.destroy()
                except Exception as error:
                    self._callback_error(type(error), error, error.__traceback__)
            self.ttk.Button(dialog, text='Удалить перечисленные ассеты…', command=apply,
                            state='normal' if proposal['delete_count'] else 'disabled').pack(side='left', padx=12, pady=12)
            self.ttk.Button(dialog, text='Закрыть', command=dialog.destroy).pack(side='right', padx=12, pady=12)
        except Exception as error:
            self._callback_error(type(error), error, error.__traceback__)
