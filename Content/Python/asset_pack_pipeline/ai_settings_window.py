"""Modeless AI settings, owned by the pipeline window."""
import queue
import threading
from . import ai_settings, assistant


class AISettingsWindow:
    def open_ai_settings(self):
        if getattr(self, 'ai_dialog', None) and self.ai_dialog.winfo_exists():
            self.ai_dialog.lift()
            return
        t, tk = self.ttk, self.tk
        dialog = self.ai_dialog = tk.Toplevel(self.root)
        dialog.title('Настройки AI · OpenAI')
        dialog.geometry('720x490')
        dialog.minsize(680, 450)
        dialog.configure(bg='#17191e')
        dialog.transient(self.root)
        shell = t.Frame(dialog, padding=22)
        shell.pack(fill='both', expand=True)
        t.Label(shell, text='Подключение OpenAI', style='Hero.TLabel').pack(anchor='w', pady=(0, 16))
        t.Label(shell, text='API-ключ', style='Subtitle.TLabel').pack(anchor='w')
        secret = self.ai_secret = tk.StringVar()
        entry = t.Entry(shell, textvariable=secret, show='•')
        entry.pack(fill='x', pady=7)
        # Never populate a widget with an existing secret.
        t.Label(shell, text='Оставьте пустым, чтобы использовать текущий ключ или OPENAI_API_KEY.',
                style='Muted.TLabel').pack(anchor='w')
        remember = self.ai_remember = tk.BooleanVar(value=False)
        t.Checkbutton(shell, text='Запомнить ключ на этом компьютере (защита Windows DPAPI)',
                      variable=remember).pack(anchor='w', pady=10)
        t.Label(shell, text='Без отметки новый ключ действует до закрытия Unreal. В проект и ZIP ключ не попадает.',
                style='Muted.TLabel', wraplength=650).pack(anchor='w')
        t.Label(shell, text='Модель', style='Subtitle.TLabel').pack(anchor='w', pady=(18, 6))
        self.ai_settings_model = tk.StringVar(value=self.ai_model.get())
        self.ai_model_menu = t.Combobox(shell, textvariable=self.ai_settings_model, values=ai_settings.MODELS)
        self.ai_model_menu.pack(fill='x')
        t.Label(shell, text='Sol — баланс · Astra — сложные задачи · Terra — скорость · Luna — экономичный вариант.\n'
                'Каталог проверен 31.10.2026. ID можно ввести вручную. Доступ зависит от аккаунта.',
                style='Muted.TLabel', wraplength=650).pack(anchor='w', pady=8)
        self.ai_settings_status = t.Label(shell, text='Ключ подключён.' if assistant.has_key() else 'Ключ ещё не подключён.',
                                           wraplength=650, style='Muted.TLabel')
        self.ai_settings_status.pack(anchor='w', pady=8)
        row = t.Frame(shell)
        row.pack(fill='x', side='bottom', pady=(12, 0))
        self.ai_models_button = t.Button(row, text='Проверить ключ / обновить модели', command=self.ai_refresh_models)
        self.ai_models_button.pack(side='left')
        t.Button(row, text='Забыть ключ', command=self.ai_forget_key).pack(side='left', padx=8)
        t.Button(row, text='Применить', style='Accent.TButton', command=self.ai_save_settings).pack(side='right')
        self.ai_settings_queue = queue.Queue()
        dialog.protocol('WM_DELETE_WINDOW', lambda: (secret.set(''), dialog.destroy()))

    def ai_save_settings(self):
        try:
            ai_settings.save(self.ai_settings_model.get(), self.ai_secret.get(), self.ai_remember.get())
            self.ai_model.set(self.ai_settings_model.get().strip())
            self.ai_secret.set('')
            self.ai_settings_status.configure(text='Настройки применены. '+('Ключ подключён.' if assistant.has_key() else 'Введите ключ.'))
        except Exception:
            self.ai_settings_status.configure(text='Не удалось сохранить настройки. Проверьте ID модели и доступ к локальному хранилищу.')

    def ai_forget_key(self):
        try:
            ai_settings.save(self.ai_model.get(), forget=True)
            self.ai_secret.set('')
            self.ai_settings_status.configure(text='Локальный ключ удалён. OPENAI_API_KEY, если задана, остаётся доступной.')
        except Exception:
            self.ai_settings_status.configure(text='Не удалось очистить локальные настройки.')

    def ai_refresh_models(self):
        key = self.ai_secret.get().strip() or ai_settings.get_key()
        if not key:
            self.ai_settings_status.configure(text='Сначала введите API-ключ.')
            return
        output = self.ai_settings_queue
        self.ai_models_button.configure(state='disabled')
        self.ai_settings_status.configure(text='Проверка ключа и загрузка доступных моделей…')
        def work():
            try:
                output.put((True, assistant.list_models(key)))
            except Exception as error:
                output.put((False, str(error)))
        threading.Thread(target=work, daemon=True).start()

    def ai_settings_poll(self):
        if not getattr(self, 'ai_dialog', None) or not self.ai_dialog.winfo_exists():
            return
        try:
            ok, result = self.ai_settings_queue.get_nowait()
        except queue.Empty:
            return
        self.ai_models_button.configure(state='normal')
        if ok:
            self.ai_model_menu.configure(values=result)
            self.ai_settings_status.configure(text=f'API-ключ принят. Доступных моделей известных семейств: {len(result)}. '
                'Выбранная модель сохранится только после «Применить». Генерация/вызов инструментов ещё не проверялись.')
        else:
            self.ai_settings_status.configure(text=result)
