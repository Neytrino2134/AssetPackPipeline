"""Client title bar; retain Windows sizing, taskbar and system move behavior."""
import sys

TITLE='MESHFLOW Asset Pack Pipeline'
SUBTITLE='FBX / GLB   →   Static Mesh + LOD   →   Материалы   →   Проверка'
HEIGHT=64

class WindowChrome:
    """One full-width header: brand, pipeline steps and window buttons; every
    non-button pixel of it drags the window."""
    def __init__(self,root,on_close):
        import tkinter as tk
        self.root=root
        bg='#12151b'
        self.bar=tk.Frame(root,bg=bg,height=HEIGHT)
        self.bar.pack(side='top',fill='x')
        self.bar.pack_propagate(False)
        badge=tk.Label(self.bar,text='MF',bg='#3975da',fg='#ffffff',
                       font=('Segoe UI',12,'bold'),padx=9,pady=5)
        badge.pack(side='left',padx=(18,14))
        text=tk.Frame(self.bar,bg=bg)
        text.pack(side='left',fill='y',pady=(10,10))
        title=tk.Label(text,text=TITLE,bg=bg,fg='#e5e8ef',font=('Segoe UI Semibold',14),anchor='w')
        title.pack(anchor='w')
        subtitle=tk.Label(text,text=SUBTITLE,bg=bg,fg='#8f98aa',font=('Segoe UI',9),anchor='w')
        subtitle.pack(anchor='w')
        for label,command,hover in [('×',on_close,'#b83c50'),('□',self.toggle_maximize,'#30394a'),('−',self.minimize,'#30394a')]:
            button=tk.Button(self.bar,text=label,command=command,bg=bg,fg='#b8c5db',
                             activebackground=hover,activeforeground='#ffffff',relief='flat',
                             borderwidth=0,highlightthickness=0,font=('Segoe UI',14),width=4,takefocus=True)
            button.pack(side='right',anchor='n',ipady=2)
            button.bind('<Enter>',lambda event,b=button,c=hover:b.configure(bg=c))
            button.bind('<Leave>',lambda event,b=button:b.configure(bg=bg))
            if label=='□':self.maximize_button=button
        for widget in (self.bar,badge,text,title,subtitle):
            widget.bind('<ButtonPress-1>',self.move)
            widget.bind('<Double-Button-1>',self.toggle_maximize)
            widget.bind('<Button-3>',self.system_menu)
        root.bind('<Map>',self.mapped,add='+')
        root.bind('<Configure>',self.configured,add='+')
        self.zoomed=None

    def _windows(self):
        import ctypes
        from ctypes import wintypes
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];user.GetAncestor.restype=wintypes.HWND
        hwnd=user.GetAncestor(self.root.winfo_id(),2)
        return ctypes,wintypes,user,hwnd

    def apply_native_frame(self):
        if sys.platform!='win32':return
        ctypes,w,user,hwnd=self._windows()
        # No overrideredirect or Python WndProc: preserve taskbar, Alt-Tab,
        # keyboard system menu, native edge resizing and minimize/restore.
        user.GetWindowLongW.argtypes=[w.HWND,ctypes.c_int];user.GetWindowLongW.restype=ctypes.c_long
        user.SetWindowLongW.argtypes=[w.HWND,ctypes.c_int,ctypes.c_long]
        style=user.GetWindowLongW(hwnd,-16)
        user.SetWindowLongW(hwnd,-16,style & ~0x00c00000) # WS_CAPTION
        user.SetWindowPos.argtypes=[w.HWND,w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.UINT]
        user.SetWindowPos(hwnd,None,0,0,0,0,0x0037) # FRAMECHANGED | NOMOVE | NOSIZE | NOZORDER | NOACTIVATE
        dwm=ctypes.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes=[w.HWND,w.DWORD,ctypes.c_void_p,w.DWORD]
        for attribute,value in ((20,1),(34,0x002b231b)):
            color=w.DWORD(value)
            dwm.DwmSetWindowAttribute(hwnd,attribute,ctypes.byref(color),ctypes.sizeof(color))

    def mapped(self,event):
        if event.widget is self.root:self.root.after_idle(self.apply_native_frame)

    def configured(self,event):
        if event.widget is not self.root:return
        zoomed=self.root.state()=='zoomed'
        if zoomed!=self.zoomed:
            self.zoomed=zoomed;self.maximize_button.configure(text='❐' if zoomed else '□')

    def minimize(self):self.root.iconify()

    def toggle_maximize(self,event=None):
        self.root.state('normal' if self.root.state()=='zoomed' else 'zoomed')
        return 'break'

    # Modal Win32 loops (move, system menu) must be posted, never sent: a
    # SendMessageW/TrackPopupMenu from inside a Tk callback lets Tk service
    # timers that re-enter Python without a thread state -> fatal GIL error.
    def _post(self,message,wparam,event):
        ctypes,w,user,hwnd=self._windows()
        user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
        point=(event.y_root & 0xffff)<<16 | (event.x_root & 0xffff)
        user.ReleaseCapture()
        user.PostMessageW(hwnd,message,wparam,point)

    def move(self,event):
        if sys.platform=='win32':
            self._post(0x00a1,2,event) # WM_NCLBUTTONDOWN / HTCAPTION
        return 'break'

    def system_menu(self,event):
        if sys.platform=='win32':
            self._post(0x0313,0,event) # WM_POPUPSYSTEMMENU
        return 'break'
