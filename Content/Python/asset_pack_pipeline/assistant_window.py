"""Chat requests off-thread; every widget and pipeline operation on the UI thread."""
import json
import queue
import threading
from . import assistant
from . import ai_settings
from .ai_settings_window import AISettingsWindow


class AssistantWindow(AISettingsWindow):
    def build_assistant(self, parent):
        t, tk = self.ttk, self.tk
        self.ai_frame = t.LabelFrame(parent, text='Помощник OpenAI', padding=12)
        row = t.Frame(self.ai_frame)
        row.pack(fill='x')
        self.ai_model = tk.StringVar(value=ai_settings.load().get('model', 'gpt-6.1-sol'))
        self.ai_permission = tk.StringVar(value='Только советы')
        t.Label(row, text='Модель API').pack(side='left')
        t.Combobox(row, textvariable=self.ai_model, values=ai_settings.MODELS, width=20).pack(side='left', padx=8)
        t.Combobox(row, state='readonly', textvariable=self.ai_permission, width=25,
                   values=('Только советы', 'Подтверждать действия', 'Автоматически')).pack(side='left')
        t.Button(row, text='Настройки AI…', command=self.open_ai_settings).pack(side='right')
        self.ai_transcript = tk.Text(self.ai_frame, height=7, bg='#14171d', fg='#bbc7dd', relief='flat',
                                     wrap='word', padx=10, pady=8, state='disabled')
        self.ai_transcript.pack(fill='both', expand=True, pady=8)
        t.Label(self.ai_frame, text='В OpenAI отправляются текст чата и краткие настройки UI. Файлы и ключ не прикладываются.',
                style='Muted.TLabel').pack(anchor='w')
        row = t.Frame(self.ai_frame)
        row.pack(fill='x', pady=(8, 0))
        self.ai_input = t.Entry(row)
        self.ai_input.pack(side='left', fill='x', expand=True)
        self.ai_send_button = t.Button(row, text='Отправить', command=self.ai_send)
        self.ai_send_button.pack(side='left', padx=8)
        self.ai_approve = t.Button(row, text='Выполнить предложение', command=lambda: self.ai_decide(True), state='disabled')
        self.ai_approve.pack(side='left')
        self.ai_reject = t.Button(row, text='Отклонить', command=lambda: self.ai_decide(False), state='disabled')
        self.ai_reject.pack(side='left', padx=8)
        self.ai_queue, self.ai_history = queue.Queue(), []
        self.ai_busy, self.ai_pending, self.ai_round = False, None, 0
        self.ai_stopped = False

    def ai_write(self, text):
        self.ai_transcript.configure(state='normal')
        self.ai_transcript.insert('end', text+'\n\n')
        self.ai_transcript.see('end')
        self.ai_transcript.configure(state='disabled')

    def ai_key_status(self):
        self.ai_write('Ключ подключён.' if assistant.has_key() else
                      'Ключ не найден. Откройте Настройки AI и введите API-ключ.')

    def ai_send(self):
        if self.ai_busy:
            return
        text = self.ai_input.get().strip()
        if not text:
            return
        if not assistant.has_key():
            self.ai_key_status()
            return
        self.ai_mode = self.ai_permission.get()
        self.ai_stopped = False
        self.ai_request_model = self.ai_model.get()
        # Only explicit, small UI context. No paths, source contents, reports or secrets.
        context = {'format': self.variables['source_format'].get(), 'variants': self.guide_variants.get(),
                   'renders': [k for k, v in self.guide_renders.items() if v.get()],
                   'lod': self.guide_lod.get(), 'source_selected': bool(self.variables['source_root'].get()),
                   'create_verified_zip': self.guide_finalize.get(),
                   'session': getattr(getattr(self, 'guide_session', None), 'label', 'ещё не запущена')}
        self.ai_history.append({'role': 'user', 'content': text+'\nТекущие настройки UI: '+json.dumps(context, ensure_ascii=False)})
        self.ai_input.delete(0, 'end')
        self.ai_write('Вы: '+text)
        self.ai_round = 0
        self.ai_launch()

    def ai_launch(self):
        self.ai_busy = True
        self.ai_send_button.configure(state='disabled')
        history = list(self.ai_history)
        model, advice, output = self.ai_request_model, self.ai_mode == 'Только советы', self.ai_queue
        def work():
            try:
                output.put(('output', assistant.request(model, history, advice)))
            except Exception as error:
                output.put(('error', str(error)))
        threading.Thread(target=work, daemon=True).start()

    def ai_poll(self):
        try:
            kind, value = self.ai_queue.get_nowait()
        except queue.Empty:
            return
        if self.ai_stopped:
            self.ai_history.clear()
            self.ai_write('Ответ отменён. Новые действия не запускаются.')
            self.ai_finish()
            return
        if kind == 'error':
            self.ai_write(value)
            self.ai_finish()
            return
        self.ai_history.extend(value)
        calls = [item for item in value if item.get('type') == 'function_call']
        for item in value:
            if item.get('type') == 'message':
                for content in item.get('content', []):
                    if content.get('type') == 'output_text':
                        self.ai_write('Помощник: '+content['text'])
        if not calls:
            self.ai_finish()
            return
        if len(calls) != 1:
            self.ai_write('Несколько действий за ответ отклонены. Начните новый вопрос.')
            self.ai_history.clear()
            self.ai_finish()
            return
        try:
            action = assistant.decode_action(calls[0])
        except Exception as error:
            self.ai_write(str(error))
            self.ai_history.clear()
            self.ai_finish()
            return
        self.ai_pending = calls[0]
        if self.ai_mode == 'Только советы':
            self.ai_decide(False)
        elif self.ai_mode == 'Автоматически' or action == 'status':
            self.ai_decide(True)
        else:
            self.ai_write('Предложение: '+action+'. Настройки возьмутся из окна в момент подтверждения.')
            self.ai_approve.configure(state='normal')
            self.ai_reject.configure(state='normal')

    def ai_decide(self, approved):
        item = self.ai_pending
        if not item:
            return
        self.ai_pending = None
        self.ai_approve.configure(state='disabled')
        self.ai_reject.configure(state='disabled')
        action = assistant.decode_action(item)
        try:
            if not approved:
                result = {'status': 'rejected'}
            elif action == 'status':
                session = getattr(self, 'guide_session', None)
                result = {'stage': session.label if session else 'not_started',
                          'done': session.done if session else False, 'active_run': self.api.readiness()['active_run']}
            elif action == 'stop':
                self.cancel()
                result = {'status': 'cancellation_requested'}
            else:
                result = self.guide_run(action == 'prepare_pack', raise_errors=True)
        except Exception:
            result = {'status': 'failed', 'details': 'Смотрите локальный журнал окна; ошибка операции. Файлы и пути не переданы в AI.'}
        self.ai_write('Действие '+action+': '+json.dumps(result, ensure_ascii=False))
        self._log('AI: '+action+' → '+result.get('status', 'read'))
        self.ai_history.append({'type': 'function_call_output', 'call_id': item['call_id'],
                                'output': json.dumps(result, ensure_ascii=False)})
        self.ai_round += 1
        if self.ai_stopped or self.ai_round >= 6:
            self.ai_write('Выполнение остановлено.' if self.ai_stopped else
                          'Лимит 6 действий за сообщение достигнут. Продолжите новым вопросом.')
            self.ai_finish()
        else:
            self.ai_launch()

    def ai_finish(self):
        self.ai_busy = False
        self.ai_send_button.configure(state='normal')

    def ai_cancel(self):
        self.ai_stopped = True
        if self.ai_pending:
            self.ai_pending = None
            self.ai_history.clear()
            self.ai_approve.configure(state='disabled')
            self.ai_reject.configure(state='disabled')
            self.ai_finish()
