"""Client title bar; retain Windows sizing, taskbar and system move behavior."""
import sys
from pathlib import Path
from . import __version__

TITLE='MESHFLOW Asset Pack Pipeline v'+__version__
SUBTITLE='FBX / GLB   →   Static Mesh + LOD   →   Материалы   →   Проверка'
HEIGHT=64
PIN_BITMAP = """#define pin_width 16
#define pin_height 16
static unsigned char pin_bits[] = {
    0x00, 0x00, 0x00, 0x0c, 0x00, 0x1e, 0x00, 0x3e, 0x00, 0x3f, 0x80, 0x1f, 0xc0, 0x0f, 0xe0, 0x0f, 0xf0, 0x1f, 0xf0, 0x1b, 0xe0, 0x01, 0x70, 0x00, 0x18, 0x00, 0x0c, 0x00, 0x06, 0x00, 0x00, 0x00
};
"""
PIN_ACTIVE='#3975da'

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
        self.logo=None
        logo_path=Path(__file__).resolve().parents[3]/'Resources/MeshFlowLogo48.png'
        try:self.logo=tk.PhotoImage(master=root,file=str(logo_path))
        except tk.TclError:pass
        badge=tk.Label(self.bar,image=self.logo if self.logo else '',
                       text='' if self.logo else 'MF',bg=bg,fg='#ffffff',
                       font=('Segoe UI',12,'bold'),borderwidth=0,highlightthickness=0)
        self.badge=badge
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
        # Pin: keep the window above other apps (e.g. Unreal) while it renders.
        self.pinned=False
        self.bg=bg
        self.pin_icon=tk.BitmapImage(master=root,data=PIN_BITMAP,foreground='#b8c5db')
        self.pinned_icon=tk.BitmapImage(master=root,data=PIN_BITMAP,foreground='#ffffff')
        slot=tk.Frame(self.bar,bg=bg,width=button.winfo_reqwidth(),height=button.winfo_reqheight()+4)
        slot.pack(side='right',anchor='n')
        self.pin_button=tk.Button(slot,image=self.pin_icon,command=self.toggle_pin,bg=bg,fg='#b8c5db',
                                  activebackground='#30394a',activeforeground='#ffffff',relief='flat',
                                  borderwidth=0,highlightthickness=0,takefocus=True)
        self.pin_button.place(relwidth=1,relheight=1)
        self.pin_button.bind('<Enter>',lambda event:self.pin_button.configure(bg='#30394a' if not self.pinned else PIN_ACTIVE))
        self.pin_button.bind('<Leave>',lambda event:self._paint_pin())
        self.normal_geometry=None
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

    def toggle_pin(self):
        self.set_pinned(not self.pinned)

    def set_pinned(self,pinned):
        self.pinned=bool(pinned)
        self.root.attributes('-topmost',self.pinned)
        self._paint_pin()

    def _paint_pin(self):
        self.pin_button.configure(image=self.pinned_icon if self.pinned else self.pin_icon,
                                  bg=PIN_ACTIVE if self.pinned else self.bg,
                                  fg='#ffffff' if self.pinned else '#b8c5db')

    def configured(self,event):
        if event.widget is not self.root:return
        state=self.root.state()
        if state=='normal':self.normal_geometry=self.root.geometry()
        zoomed=state=='zoomed'
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
