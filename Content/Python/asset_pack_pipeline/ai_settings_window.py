"""Modeless AI settings, owned by the pipeline window."""
import queue
import threading
from . import ai_settings, assistant


class AISettingsWindow:
    def open_ai_settings(self):
        if getattr(self, 'ai_dialog', None) and self.ai_dialog.winfo_exists():
            self.ai_dialog.deiconify()
            self.ai_dialog.lift()
            self.ai_dialog.focus_force()
            return
        from . import dark_dialog as dd
        holder = dd.Dialog(self.root, 'Настройки AI · OpenAI', 740, 560, minsize=(680, 500),
                           loading='Чтение настроек OpenAI…')
        self.ai_dialog = holder.window
        holder.load(assistant.has_key, lambda connected: self._build_ai_settings(holder, connected), threaded=True)

    def _build_ai_settings(self, holder, connected):
        from . import dark_dialog as dd
        t, tk = self.ttk, self.tk
        bar = tk.Frame(holder.content, bg=dd.PANEL)
        bar.pack(fill='x', side='bottom')
        shell = t.Frame(holder.content, padding=22, style='Shell.TFrame')
        shell.pack(fill='both', expand=True)
        t.Label(shell, text='Подключение OpenAI', style='Hero.TLabel').pack(anchor='w', pady=(0, 16))
        t.Label(shell, text='API-ключ', style='Subtitle.TLabel').pack(anchor='w')
        secret = self.ai_secret = tk.StringVar()
        entry = t.Entry(shell, textvariable=secret, show='•')
        entry.pack(fill='x', pady=7)
        # Never populate a widget with an existing secret.
        t.Label(shell, text='Оставьте пустым, чтобы использовать текущий ключ или OPENAI_API_KEY.',
                style='DialogMuted.TLabel').pack(anchor='w')
        remember = self.ai_remember = tk.BooleanVar(value=False)
        t.Checkbutton(shell, text='Запомнить ключ на этом компьютере (защита Windows DPAPI)',
                      variable=remember, style='Dialog.TCheckbutton').pack(anchor='w', pady=10)
        t.Label(shell, text='Без отметки новый ключ действует до закрытия Unreal. В проект и ZIP ключ не попадает.',
                style='DialogMuted.TLabel', wraplength=650).pack(anchor='w')
        t.Label(shell, text='Модель', style='Subtitle.TLabel').pack(anchor='w', pady=(18, 6))
        self.ai_settings_model = tk.StringVar(value=self.ai_model.get())
        self.ai_model_menu = t.Combobox(shell, textvariable=self.ai_settings_model, values=ai_settings.MODELS)
        self.ai_model_menu.pack(fill='x')
        t.Label(shell, text='Sol — баланс · Astra — сложные задачи · Terra — скорость · Luna — экономичный вариант.\n'
                'Каталог проверен 31.10.2026. ID можно ввести вручную. Доступ зависит от аккаунта.',
                style='DialogMuted.TLabel', wraplength=650).pack(anchor='w', pady=8)
        self.ai_settings_status = t.Label(shell, text='Ключ подключён.' if connected else 'Ключ ещё не подключён.',
                                           wraplength=650, style='DialogMuted.TLabel')
        self.ai_settings_status.pack(anchor='w', pady=8)
        self.ai_models_button = dd.button(bar, 'Проверить ключ / обновить модели', self.ai_refresh_models)
        self.ai_models_button.pack(side='left', padx=(16, 0), pady=12)
        dd.button(bar, 'Забыть ключ', self.ai_forget_key).pack(side='left', padx=8, pady=12)
        dd.button(bar, 'Закрыть', holder.close).pack(side='right', padx=(8, 16), pady=12)
        dd.button(bar, 'Применить', self.ai_save_settings, accent=True).pack(side='right', pady=12)
        self.ai_settings_queue = queue.Queue()
        # Never keep a typed secret after the window closes.
        holder.on_close = lambda: secret.set('')
        entry.focus_set()

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
        from . import dark_dialog as dd
        dd.enable(self.ai_models_button, False)
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
        if not getattr(self, 'ai_settings_queue', None):
            return  # still loading
        try:
            ok, result = self.ai_settings_queue.get_nowait()
        except queue.Empty:
            return
        from . import dark_dialog as dd
        dd.enable(self.ai_models_button, True)
        if ok:
            self.ai_model_menu.configure(values=result)
            self.ai_settings_status.configure(text=f'API-ключ принят. Доступных моделей известных семейств: {len(result)}. '
                'Выбранная модель сохранится только после «Применить». Генерация/вызов инструментов ещё не проверялись.')
        else:
            self.ai_settings_status.configure(text=result)
