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
    from tkinter import messagebox
    assert 'unreal' not in sys.modules
    root=tk.Tk();root.title('MESHFLOW · Настройки обновлений');root.geometry('780x540');root.minsize(700,500)
    root.configure(bg='#17191e')
    options=updater.settings();repo=tk.StringVar(value=options['repository']);auto=tk.BooleanVar(value=options['auto_check'])
    status=tk.StringVar(value='Установлена версия '+__version__+' · Unreal '+context['engine_version'])
    release=None;job=None;busy=False;results=queue.Queue()
    def label(text,**kwargs):
        item=tk.Label(root,text=text,bg='#17191e',fg='#dbe5f5',anchor='w',**kwargs);item.pack(fill='x',padx=22,pady=7);return item
    label('MESHFLOW · Обновления',font=('Segoe UI Semibold',18))
    label('GitHub Releases · публичный репозиторий · Git не требуется')
    label('Репозиторий (owner/name)')
    tk.Entry(root,textvariable=repo,bg='#242a35',fg='#ecf2ff',insertbackground='white',relief='flat',font=('Segoe UI',11)).pack(fill='x',padx=22,ipady=7)
    tk.Checkbutton(root,text='Проверять при запуске Unreal',variable=auto,bg='#17191e',fg='#dbe5f5',selectcolor='#242a35',
                   activebackground='#17191e',activeforeground='#dbe5f5',highlightthickness=0).pack(anchor='w',padx=20,pady=12)
    label('DLL устанавливаются после закрытия редактора. Предыдущая версия сохраняется.\nРабочие копии с .git обновляются через GitHub Desktop.',justify='left',wraplength=690)
    tk.Label(root,textvariable=status,bg='#222936',fg='#b9d3ff',wraplength=680,justify='left',anchor='w',padx=12,pady=12).pack(fill='x',padx=22,pady=8)
    bar=tk.Frame(root,bg='#17191e');bar.pack(fill='x',padx=22,pady=8)
    def save():updater.save_settings(repo.get().strip(),auto.get())
    def run(kind):
        nonlocal busy,release
        if busy or job:return
        try:save()
        except Exception as error:messagebox.showerror('Настройки',str(error),parent=root);return
        if kind=='install' and (not release or release['repository']!=repo.get().strip()):
            status.set('Репозиторий изменён. Сначала нажмите «Проверить сейчас».');return
        if kind=='install' and not messagebox.askyesno('Установить обновление',
            'Скачать проверенный релиз из '+repo.get()+'?\nПосле загрузки закройте Unreal и дождитесь завершения установки в этом окне.',parent=root):return
        busy=True;status.set('Проверка GitHub…' if kind=='check' else 'Загрузка и проверка ZIP…')
        check_button.configure(state='disabled');install_button.configure(state='disabled')
        snapshot=release;repository=repo.get().strip()
        def work():
            try:results.put((kind,updater.checked(context,repository) if kind=='check' else updater.prepare(context,snapshot)))
            except Exception as error:results.put(('error',{'message':str(error)}))
        threading.Thread(target=work,daemon=True).start()
    def button(text,command):
        item=tk.Button(bar,text=text,command=command,bg='#343e51',fg='#eff5ff',activebackground='#465a7b',
                       activeforeground='white',borderwidth=0,padx=12,pady=8);item.pack(side='left',padx=(0,8));return item
    check_button=button('Проверить сейчас',lambda:run('check'))
    install_button=button('Скачать и установить',lambda:run('install'));install_button.configure(state='disabled')
    def save_click():
        try:save();status.set('Настройки сохранены')
        except Exception as error:status.set(str(error))
    button('Сохранить',save_click)
    def poll():
        nonlocal busy,release,job
        try:
            while True:
                kind,value=results.get_nowait();busy=False;status.set(value['message'])
                if kind=='check':
                    release=value if value.get('status')=='available' else None
                    if release:
                        try:updater.validate_target(context['target'])
                        except Exception as error:status.set(value['message']+'\n'+str(error));release=None
                elif kind=='install':job=Path(value['directory'])
                check_button.configure(state='disabled' if job else 'normal')
                install_button.configure(state='normal' if release and not job else 'disabled')
        except queue.Empty:pass
        if job:
            try:status.set(json.loads((job/'result.json').read_text(encoding='utf-8'))['message'])
            except (OSError,ValueError):pass
        root.after(500,poll)
    root.after(100,poll);root.after(200,lambda:run('check'));root.mainloop()

if __name__=='__main__':main(json.loads(sys.stdin.readline(65536)))
