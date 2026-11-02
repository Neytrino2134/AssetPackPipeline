"""Native Slate adapter. No Tk imports; session lives independently of the tab."""
import base64
import json
import time
import uuid
import os
import queue
import threading
import copy
from pathlib import Path
import unreal
from . import api, guided

_session = None
_tick = None
_last = 0
_network = queue.Queue()
_network_busy = False
_history = []
_cleanup = None
_observed_run = None
_chat_log = []
_events = []
_last_result = {}
_pending_ai = None
_ai_snapshot = {}
_ai_permission = 'Только советы'
_ai_round = 0
_ai_cancelled = False
_polling = False


def clean_text(text):
    import re
    from . import ai_settings
    key = ai_settings.get_key()
    if key: text = text.replace(key,'[API KEY REDACTED]')
    return re.sub(r'sk-[A-Za-z0-9_-]{8,}', '[API KEY REDACTED]',text)


def chat_line(role,text):
    _chat_log.append(role+': '+clean_text(text))
    del _chat_log[:-200]


def launch_ai():
    global _network_busy
    from . import assistant
    history = copy.deepcopy(_history)
    model = _ai_snapshot['model']
    advice = _ai_permission=='Только советы'
    def work():
        try: _network.put(('chat',assistant.request(model,history,advice)))
        except Exception as error: _network.put(('error',str(error)))
    _network_busy = True
    threading.Thread(target=work,daemon=True).start()
    ensure_tick()


def decide_ai(approved):
    global _pending_ai, _ai_round
    from . import assistant
    if not _pending_ai: raise ValueError('Нет ожидающего предложения AI.')
    item = _pending_ai
    _pending_ai = None
    action = assistant.decode_action(item)
    if not approved:
        result = {'status':'rejected'}
    elif action=='status':
        result = {'stage':_session.label if _session else 'not_started','done':_session.done if _session else False,
                  'active_run':api.readiness()['active_run']}
    else:
        command = dict(copy.deepcopy(_ai_snapshot),action={'check_sources':'plan','prepare_pack':'start','stop':'cancel'}[action])
        submit_b64(base64.b64encode(json.dumps(command).encode()).decode())
        result = {'status':'failed' if 'error' in _last_result else 'accepted',
                  'note':'Asynchronous start is not completion. See local job status.'}
    chat_line('Действие '+action,json.dumps(result,ensure_ascii=False))
    _history.append({'type':'function_call_output','call_id':item['call_id'],'output':json.dumps(result)})
    _ai_round += 1
    if not _ai_cancelled and _ai_round < 6:
        launch_ai()
    else:
        _history.clear()
        chat_line('Система','Остановлено или достигнут лимит 6 действий за сообщение.')
    state({'ai':'Результат действия обработан'})


def ensure_tick():
    global _tick
    if _tick is None:
        _tick = unreal.register_slate_post_tick_callback(poll)


def folder():
    path = Path(unreal.Paths.project_saved_dir()).resolve()/'AssetPackPipeline/Native'
    path.mkdir(parents=True, exist_ok=True)
    return path


def state(value):
    global _last_result
    _last_result = value
    event = clean_text(json.dumps(value,ensure_ascii=False,default=str))[:4000]
    if not _events or _events[-1].split(' ',1)[-1]!=event:
        _events.append(time.strftime('%H:%M:%S')+' '+event)
        del _events[:-200]
    view = dict(value,chat_history='\n\n'.join(_chat_log),task_history='\n'.join(_events),
                ai_pending=bool(_pending_ai))
    (folder()/'state.json').write_text(json.dumps(view,ensure_ascii=False,indent=2),encoding='utf-8')


def poll(delta):
    global _polling
    if _polling: return
    _polling = True
    try: _poll_impl(delta)
    finally: _polling = False


def _poll_impl(delta):
    global _last, _tick, _network_busy, _observed_run, _pending_ai
    if time.monotonic()-_last < .5:
        return
    _last = time.monotonic()
    try:
        kind, value = _network.get_nowait()
        _network_busy = False
        if kind == 'chat':
            if _ai_cancelled:
                state({'ai':'Ответ отменён; действия не выполнялись'})
                return
            _history.extend(value)
            text = '\n'.join(c.get('text','') for item in value if item.get('type')=='message' for c in item.get('content',[]) if c.get('type')=='output_text')
            if text: chat_line('Помощник',text)
            calls = [item for item in value if item.get('type')=='function_call']
            if calls:
                from . import assistant
                if len(calls)!=1:
                    _history.clear()
                    chat_line('Система','Пакет из нескольких действий отклонён.')
                else:
                    try:
                        action = assistant.decode_action(calls[0])
                        _pending_ai = calls[0]
                        summary = {k:_ai_snapshot.get(k) for k in ('source','pack','format','mode','lod','mid','render','zip','output')}
                        chat_line('Предложение',action+'\nСнимок параметров: '+json.dumps(summary,ensure_ascii=False))
                        if _ai_permission=='Только советы': decide_ai(False)
                        elif _ai_permission=='Автоматически' or action=='status': decide_ai(True)
                    except Exception as error:
                        _pending_ai = None
                        _history.clear()
                        chat_line('Ошибка',str(error))
            value = text
        elif kind=='error': chat_line('Ошибка',str(value))
        state({kind:value})
    except queue.Empty:
        pass
    try:
        if _observed_run:
            report = api.status(_observed_run)
            state({'job':report})
            if report['status']!='running': _observed_run = None
        if _session and not _session.done:
            _session.tick()
            state({'stage':_session.label,'done':_session.done,'error':_session.error,'result':_session.result,
                   'active_run':api.readiness()['active_run']})
    except Exception as error:
        state({'error':str(error)})
        if _session: _session.done = True
    if (not _session or _session.done) and not _network_busy and not _observed_run and _tick is not None:
        unreal.unregister_slate_post_tick_callback(_tick)
        _tick = None


def submit_b64(encoded):
    global _session, _tick, _network_busy, _cleanup, _observed_run, _pending_ai, _ai_snapshot, _ai_permission, _ai_round, _ai_cancelled
    try:
        data = json.loads(base64.b64decode(encoded).decode('utf-8'))
        action = data['action']
        if action=='updates':
            from . import ui
            ui.open_updates()
            return
        if action in ('ai_approve','ai_reject'):
            decide_ai(action=='ai_approve')
            return
        if action=='chat_clear':
            if _network_busy or _pending_ai: raise RuntimeError('Сначала остановите/отклоните текущий запрос.')
            _history.clear(); _chat_log.clear()
            state({'ai':'История чата очищена'})
            return
        if action=='queue':
            state({'queue':api.list_runs(50)})
            return
        if action=='job_status':
            state({'job':api.status(data['run_id'])})
            return
        if action=='load_profile':
            from . import native_profile
            active = folder().parent/'active_profile.json'
            template = Path(__file__).resolve().parents[2]/'Profiles/profile.example.json'
            p = json.loads((active if active.is_file() else template).read_text(encoding='utf-8-sig'))
            state({'loaded_profile':p,'professional_fields':native_profile.form_values(p)})
            return
        if action == 'ai_save':
            from . import ai_settings
            import ctypes
            buffer = ctypes.create_unicode_buffer(2048)
            read = ctypes.WinDLL('kernel32').GetEnvironmentVariableW
            read.argtypes = [ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint32]
            read.restype = ctypes.c_uint32
            count = read('OPENAI_API_KEY',buffer,len(buffer))
            if count >= len(buffer): raise ValueError('Некорректная длина ключа.')
            ai_settings.save(data['model'],buffer.value if count else '',data.get('remember',False))
            state({'ai':'Настройки применены; ключ подключён' if ai_settings.get_key() else 'Введите API-ключ'})
            return
        if action in ('ai_models','chat'):
            if _network_busy or _pending_ai: raise RuntimeError('Дождитесь ответа или подтвердите/отклоните предложение.')
            from . import assistant
            if action=='chat':
                if not data.get('chat','').strip(): raise ValueError('Введите сообщение.')
                _ai_snapshot = copy.deepcopy(data)
                _ai_permission = data.get('ai_permission','Только советы')
                if _ai_permission not in ('Только советы','Подтверждать действия','Автоматически'): raise ValueError('Неизвестный режим AI')
                _ai_round = 0; _ai_cancelled = False
                text = clean_text(data['chat'])
                chat_line('Вы',text)
                context = {'format':data.get('format'),'LOD':data.get('lod'),'MID':data.get('mid'),
                           'final_zip':data.get('zip'),'source_selected':bool(data.get('source'))}
                _history.append({'role':'user','content':text+'\nНастройки UI: '+json.dumps(context)})
                launch_ai()
                state({'ai':'Запрос отправлен…'})
                return
            history = list(_history)
            def work():
                try:
                    result = assistant.list_models() if action=='ai_models' else assistant.request(data['model'],history,True)
                    _network.put(('models' if action=='ai_models' else 'chat',result))
                except Exception as error: _network.put(('error',str(error)))
            _network_busy = True
            threading.Thread(target=work,daemon=True).start()
            state({'ai':'Запрос отправлен…'})
            ensure_tick()
            return
        if action == 'cancel':
            _ai_cancelled = True
            _pending_ai = None
            _history.clear()
            if _session and not _session.done:
                _session.cancel()
            active = api.readiness()['active_run']
            if active:
                api.cancel(active)
            state({'stage':'Запрошена остановка'})
            return
        if api.readiness()['active_run'] or _session and not _session.done:
            raise RuntimeError('Дождитесь текущей задачи.')
        if action=='resume':
            _observed_run = api.resume(data['run_id'])
            ensure_tick()
            state({'resumed_run':_observed_run})
            return
        if action=='scan_content':
            from collections import Counter
            counts = Counter('/'.join(str(p).split('.')[0].split('/')[:3]) for p in unreal.EditorAssetLibrary.list_assets('/Game',recursive=True,include_folder=False) if len(str(p).split('/'))>3)
            state({'content_folders':dict(sorted(counts.items()))})
            return
        if action in ('cleanup_plan','cleanup_confirm'):
            from . import cleanup
            if action=='cleanup_plan':
                root = data['cleanup_root'].rstrip('/')
                manifest = {'profile':{'destination_root':root,'pack_id':root.rsplit('/',1)[-1]}}
                proposal = cleanup.plan(manifest,imported=True,folder_scope=True)
                _cleanup = (manifest,proposal)
                state({'cleanup_plan':proposal})
            else:
                if not _cleanup: raise ValueError('Сначала просмотрите план очистки.')
                manifest,proposal = _cleanup
                if data['cleanup_root'].rstrip('/') != manifest['profile']['destination_root']:
                    raise ValueError('Папка изменилась; создайте новый план.')
                _cleanup = None
                backup = folder()/'Cleanup'/uuid.uuid4().hex
                backup.mkdir(parents=True)
                (backup/'plan.json').write_text(json.dumps(proposal,ensure_ascii=False,indent=2),encoding='utf-8')
                result = cleanup.execute(manifest,backup/'backup',imported=True,folder_scope=True,expected=proposal['delete_packages'])
                (backup/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                state({'cleanup_result':result})
            return
        if action not in ('plan','start','save_profile','validate_assets','settings','source_diagnostics','import_diagnostics','override_load','override_store','override_delete','flythrough'):
            raise ValueError('Unknown native action')
        root = Path(__file__).resolve().parents[2]/'Profiles/profile.example.json'
        base = json.loads(root.read_text(encoding='utf-8'))
        professional = data.get('mode')=='Профессиональный'
        if action in ('override_load','override_store','override_delete'):
            if not professional: raise ValueError('Откройте профессиональный режим.')
            from . import native_profile
            if data.get('profile_json','').strip(): base = json.loads(data['profile_json'])
            base = native_profile.apply_fields(base,data.get('professional_fields',{}))
            base.update(source_root=data['source'],pack_id=data['pack'],source_format=data['format'])
            if action=='override_load':
                values = base.get('asset_overrides',{}).get(data['override_id'],{})
                from . import profiles as profile_schema
                fields = {}
                for key in profile_schema.OVERRIDE_KEYS:
                    value = values.get(key,'')
                    if isinstance(value,list): value = ', '.join(map(str,value))
                    elif isinstance(value,bool): value = str(value).lower()
                    elif key=='orm_texture' and key in values and value=='': value = '-'
                    fields[key] = str(value)
                state({'override_fields':fields,'override_id':data['override_id']})
                return
            base = native_profile.edit_override(base,data['override_id'],data['override_fields'],action=='override_delete')
            state({'loaded_profile':base,'overrides_updated':data['override_id'],'note':'Изменено в UI; нажмите Сохранить активный профиль для записи на диск.'})
            return
        if professional and data.get('raw_profile',False) and data.get('profile_json', '').strip():
            profiles = {'Profile':json.loads(data['profile_json'])}
            steps = [('Profile',x) for x in ('import','validate','overview')]
            if data['render']: steps.append(('Profile','preview'))
            if data['zip']: steps.extend(('Profile',x) for x in ('delivery','verify_delivery','package'))
        else:
            if professional:
                from . import native_profile
                if data.get('profile_json','').strip():
                    base = json.loads(data['profile_json'])
                base = native_profile.apply_fields(base,data.get('professional_fields',{}))
            if not data['mid'] and not data['lod']:
                raise ValueError('Выберите LOD и/или MID.')
            variants = 'both' if data['mid'] and data['lod'] else 'Nanite' if data['mid'] else 'LOD'
            renders = [r for r in ('MID','LOW','LODS','selected') if data.get('render_'+r,False)]
            if data['render']: renders.append('overview')
            profiles, steps = guided.prepare(base,data['source'],data['pack'],data['format'].upper(),variants,
                renders,lod=int(data.get('selected_lod',0)),finalize=data['zip'],output=data['output'])
            if professional:
                for profile in profiles.values():
                    profile['destination_root'] = base['destination_root']
                    profile['texture_directory'] = base['texture_directory']
                    profile['nanite_source'] = base.get('nanite_source','AUTO')
                    profile['asset_overrides'] = base.get('asset_overrides',{})
                    if base.get('asset_ids'): profile['asset_ids'] = base['asset_ids']
        if action=='save_profile':
            saved = dict(next(iter(profiles.values())))
            (folder().parent/'active_profile.json').write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
            state({'saved_profile':str(folder().parent/'active_profile.json'),'note':'Сохранён первый выбранный тип; второй строится из общих настроек.'})
            return
        work = folder()/uuid.uuid4().hex
        work.mkdir()
        paths, summaries = {}, []
        for name, profile in profiles.items():
            path = work/(name+'.json')
            path.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
            paths[name] = str(path)
            if action=='flythrough':
                _observed_run = api.start_flythrough(str(path))
                ensure_tick()
                state({'flythrough_run':_observed_run,'note':'Пролёт использует первый выбранный профиль.'})
                return
            if action=='source_diagnostics':
                summaries.append(api.analyze_sources(str(path)))
                continue
            if action=='import_diagnostics':
                if profile.get('nanite_enabled',False): continue
                _observed_run = api.start_diagnostics(str(path))
                ensure_tick()
                state({'diagnostics_run':_observed_run})
                return
            if action=='validate_assets':
                report = api.validate(str(path))
                summaries.append({'variant':name,'passed':report['passed'],'assets':report['assets']})
                continue
            report = api.plan(str(path))
            summaries.append({'variant':name,'assets':len(report['assets']),'ready':report['ready'],'conflicts':report['conflicts']})
            if not report['ready']:
                raise RuntimeError(json.dumps(summaries,ensure_ascii=False))
        state({'plan':summaries,'steps':steps})
        if action=='import_diagnostics':
            raise ValueError('Для диагностики импорта включите LOW/LOD; анализ исходников доступен для MID.')
        if action in ('start','settings'):
            if action=='settings': steps = [(name,'settings') for name in paths]
            _session = guided.Session(api,paths,steps)
            ensure_tick()
    except Exception as error:
        state({'error':str(error)})
        unreal.log_error('AssetPackPipeline: '+str(error))
