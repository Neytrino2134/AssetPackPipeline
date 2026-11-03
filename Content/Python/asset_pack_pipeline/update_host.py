"""Standalone update settings window; never loads Tk inside Unreal."""
import json
import os
import queue
import sys
import threading
from pathlib import Path
from . import updater,__version__

def main(context):
    for name,directory in (('TCL_LIBRARY','tcl8.6'),('TK_LIBRARY','tk8.6')):
        candidate=Path(sys.base_prefix)/'tcl'/directory
        if candidate.is_dir():os.environ.setdefault(name,str(candidate))
    import tkinter as tk
    from . import dark_dialog as dd
    assert 'unreal' not in sys.modules
    dialog=dd.Dialog(None,'MESHFLOW · Настройки обновлений',800,560,minsize=(700,500),loading='Чтение настроек обновлений…')
    root=dialog.window
    dialog.load(updater.settings,lambda options:build(options))
    def build(options):
        body=dialog.content
        repo=tk.StringVar(value=options['repository']);auto=tk.BooleanVar(value=options['auto_check'])
        status=tk.StringVar(value='Установлена версия '+__version__+' · Unreal '+context['engine_version'])
        state={'release':None,'job':None,'busy':False};results=queue.Queue()
        def label(text,**kwargs):
            kwargs.setdefault('fg','#dbe5f5')
            item=tk.Label(body,text=text,bg=dd.BG,anchor='w',**kwargs);item.pack(fill='x',padx=22,pady=6);return item
        label('Обновления плагина',font=('Segoe UI Semibold',18)).pack_configure(pady=(18,6))
        label('GitHub Releases · публичный репозиторий · Git не требуется',fg=dd.MUTED)
        label('Репозиторий (owner/name)')
        tk.Entry(body,textvariable=repo,bg='#242a35',fg='#ecf2ff',insertbackground='white',relief='flat',
                 highlightthickness=1,highlightbackground='#363b47',highlightcolor=dd.ACCENT,font=('Segoe UI',11)).pack(fill='x',padx=22,ipady=7)
        tk.Checkbutton(body,text='Проверять при запуске Unreal',variable=auto,bg=dd.BG,fg='#dbe5f5',selectcolor='#242a35',
                       activebackground=dd.BG,activeforeground='#dbe5f5',highlightthickness=0).pack(anchor='w',padx=20,pady=12)
        label('DLL устанавливаются после закрытия редактора. Предыдущая версия сохраняется.\nРабочие копии с .git обновляются через GitHub Desktop.',
              justify='left',wraplength=700,fg=dd.MUTED)
        tk.Label(body,textvariable=status,bg='#222936',fg='#b9d3ff',wraplength=700,justify='left',anchor='w',padx=12,pady=12).pack(fill='x',padx=22,pady=8)
        bar=tk.Frame(body,bg=dd.PANEL);bar.pack(fill='x',side='bottom')
        def save():updater.save_settings(repo.get().strip(),auto.get())
        def run(kind):
            if state['busy'] or state['job']:return
            try:save()
            except Exception as error:status.set('Настройки: '+str(error));return
            release=state['release']
            if kind=='install' and (not release or release['repository']!=repo.get().strip()):
                status.set('Репозиторий изменён. Сначала нажмите «Проверить сейчас».');return
            if kind=='install' and not dd.confirm(root,'Установить обновление',
                'Скачать проверенный релиз из '+repo.get()+'?\n\nПосле загрузки закройте Unreal и дождитесь завершения установки в этом окне.',
                ok_text='Скачать'):return
            work(kind,release,repo.get().strip())
        def work(kind,snapshot,repository):
            state['busy']=True;status.set('Проверка GitHub…' if kind=='check' else 'Загрузка и проверка ZIP…')
            dd.enable(check_button,False);dd.enable(install_button,False)
            def task():
                try:results.put((kind,updater.checked(context,repository) if kind=='check' else updater.prepare(context,snapshot)))
                except Exception as error:results.put(('error',{'message':str(error)}))
            threading.Thread(target=task,daemon=True).start()
        check_button=dd.button(bar,'Проверить сейчас',lambda:run('check'))
        check_button.pack(side='left',padx=(16,8),pady=12)
        install_button=dd.button(bar,'Скачать и установить',lambda:run('install'),accent=True)
        install_button.pack(side='left',pady=12);dd.enable(install_button,False)
        def save_click():
            try:save();status.set('Настройки сохранены')
            except Exception as error:status.set(str(error))
        dd.button(bar,'Закрыть',dialog.close).pack(side='right',padx=(8,16),pady=12)
        dd.button(bar,'Сохранить',save_click).pack(side='right',pady=12)
        def poll():
            if dialog.closed:return
            try:
                while True:
                    kind,value=results.get_nowait();state['busy']=False;status.set(value['message'])
                    if kind=='check':
                        state['release']=value if value.get('status')=='available' else None
                        if state['release']:
                            try:updater.validate_target(context['target'])
                            except Exception as error:status.set(value['message']+'\n'+str(error));state['release']=None
                    elif kind=='install':state['job']=Path(value['directory'])
                    dd.enable(check_button,not state['job'])
                    dd.enable(install_button,bool(state['release'] and not state['job']))
            except queue.Empty:pass
            if state['job']:
                try:status.set(json.loads((state['job']/'result.json').read_text(encoding='utf-8'))['message'])
                except (OSError,ValueError):pass
            root.after(500,poll)
        root.after(100,poll);root.after(200,lambda:run('check'))
    root.mainloop()

if __name__=='__main__':main(json.loads(sys.stdin.readline(65536)))
