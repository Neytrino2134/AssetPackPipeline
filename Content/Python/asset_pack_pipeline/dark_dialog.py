"""Dark MESHFLOW dialogs: custom title bar, centred, no white flash, loading state.

Every window is created invisible (alpha 0) on a dark background, placed, given the
compact MESHFLOW title bar, then faded in showing a spinner while its data loads;
the real interface replaces the spinner once built. confirm() replaces the white
native message box with the same look.
"""
import queue
import sys
import threading

BG = '#17191e'
PANEL = '#20232b'
TEXT = '#e5e8ef'
MUTED = '#a1a9ba'
ACCENT = '#3975da'
DANGER = '#b83c50'


def work_area():
    """Primary monitor work area (excludes the taskbar): (x, y, width, height)."""
    if sys.platform == 'win32':
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
                return rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top
        except Exception:
            pass
    return None


def center(window, width, height, owner=None):
    """Centre over a visible owner window, otherwise on the primary work area."""
    window.update_idletasks()
    area = work_area() or (0, 0, window.winfo_screenwidth(), window.winfo_screenheight())
    width, height = min(width, area[2]), min(height, area[3])
    if owner is not None and owner.winfo_exists() and owner.winfo_viewable():
        x = owner.winfo_rootx() + (owner.winfo_width()-width)//2
        y = owner.winfo_rooty() + (owner.winfo_height()-height)//2
    else:
        x, y = area[0] + (area[2]-width)//2, area[1] + (area[3]-height)//2
    # Keep the title bar reachable even if the owner sits partly off-screen.
    x = max(area[0], min(x, area[0]+area[2]-width))
    y = max(area[1], min(y, area[1]+area[3]-height))
    window.geometry(f'{width}x{height}+{x}+{y}')


def fade_in(window, duration_ms=140, steps=7):
    def step(index=1):
        if not window.winfo_exists():
            return
        window.attributes('-alpha', min(1.0, index/steps))
        if index < steps:
            window.after(duration_ms//steps, lambda: step(index+1))
    step()


def button(parent, text, command, accent=False, danger=False):
    import tkinter as tk
    base = DANGER if danger else ACCENT if accent else '#343b4b'
    hover = '#cf4a61' if danger else '#4b87ef' if accent else '#465269'
    item = tk.Button(parent, text=text, command=command, bg=base, fg='#ffffff', activebackground=hover,
                     activeforeground='#ffffff', disabledforeground='#7c8597', relief='flat', borderwidth=0,
                     highlightthickness=0, font=('Segoe UI Semibold' if accent or danger else 'Segoe UI', 10),
                     padx=14, pady=7, cursor='hand2')
    item.colors = (base, hover)
    item.bind('<Enter>', lambda event: item.configure(bg=hover) if str(item['state']) != 'disabled' else None)
    item.bind('<Leave>', lambda event: item.configure(bg=base if str(item['state']) != 'disabled' else DISABLED))
    return item


DISABLED = '#2a303c'


def enable(item, enabled=True):
    """Disabled dark buttons must look disabled too, not just ignore clicks."""
    item.configure(state='normal' if enabled else 'disabled', bg=item.colors[0] if enabled else DISABLED,
                   cursor='hand2' if enabled else 'arrow')


def run_async(widget, work, done, threaded=False):
    """Run work() and call done(ok, result_or_exception) on the Tk thread.
    threaded=False keeps work on the Tk thread (Unreal API) after a short repaint delay."""
    results = queue.Queue()

    def run():
        try:
            results.put((True, work()))
        except Exception as error:
            results.put((False, error))

    def poll():
        try:
            ok, value = results.get_nowait()
        except queue.Empty:
            widget.after(60, poll)
            return
        done(ok, value)
    if threaded:
        threading.Thread(target=run, daemon=True).start()
        widget.after(60, poll)
    else:
        widget.after(80, lambda: (run(), poll()))


class Spinner:
    def __init__(self, parent, text='Загрузка…'):
        import tkinter as tk
        self.frame = tk.Frame(parent, bg=BG)
        self.canvas = tk.Canvas(self.frame, width=46, height=46, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=(0, 12))
        self.canvas.create_oval(5, 5, 41, 41, outline='#2a303c', width=4)
        self.arc = self.canvas.create_arc(5, 5, 41, 41, start=90, extent=100, style='arc', outline=ACCENT, width=4)
        self.label = tk.Label(self.frame, text=text, bg=BG, fg=MUTED, font=('Segoe UI', 10))
        self.label.pack()
        self.angle = 90
        self.running = True
        self._tick()

    def _tick(self):
        if not self.running or not self.canvas.winfo_exists():
            return
        self.angle = (self.angle - 12) % 360
        self.canvas.itemconfigure(self.arc, start=self.angle)
        self.canvas.after(30, self._tick)

    def stop(self):
        self.running = False


class Dialog:
    """Window with the compact MESHFLOW title bar.

    Build the interface inside `content`; it stays hidden behind a spinner until
    `ready()` (or `load(fetch, build)`) shows it. master=None creates a Tk root
    (standalone processes such as the updater)."""

    def __init__(self, master, title, width, height, owner=None, minsize=None, on_close=None, loading='Загрузка…'):
        import tkinter as tk
        from .custom_chrome import WindowChrome
        self.tk = tk
        self.window = window = tk.Tk() if master is None else tk.Toplevel(master, bg=BG)
        window.withdraw()
        window.attributes('-alpha', 0.0)
        window.configure(bg=BG)
        window.title(title)
        if master is not None:
            window.transient(owner or master)
        if minsize:
            window.minsize(*minsize)
        self.on_close = on_close
        self.closed = False
        self.chrome = WindowChrome(window, self.close, title=title, compact=True)
        if getattr(self.chrome, 'logo', None):
            window.iconphoto(False, self.chrome.logo)
        self.content = tk.Frame(window, bg=BG)
        self.loader = tk.Frame(window, bg=BG)
        self.loader.pack(fill='both', expand=True)
        self.spinner = Spinner(self.loader, loading)
        self.spinner.frame.place(relx=.5, rely=.45, anchor='center')
        window.protocol('WM_DELETE_WINDOW', self.close)
        window.bind('<Escape>', lambda event: self.close())
        center(window, width, height, owner if owner is not None else master)
        shown = []

        def reveal(event):
            if event.widget is window and not shown:
                shown.append(True)
                window.after_idle(lambda: (self.chrome.apply_native_frame(), fade_in(window)))
        window.bind('<Map>', reveal, add='+')
        window.deiconify()

    def ready(self):
        if self.closed:
            return
        self.spinner.stop()
        self.loader.destroy()
        self.content.pack(fill='both', expand=True)

    def fail(self, message):
        """Show an error in place of the spinner; the dialog stays dark and closable."""
        if self.closed:
            return
        self.spinner.stop()
        for child in self.loader.winfo_children():
            child.destroy()
        box = self.tk.Frame(self.loader, bg=BG)
        box.place(relx=.5, rely=.45, anchor='center')
        self.tk.Label(box, text='Не удалось загрузить данные', bg=BG, fg='#ff9d9d',
                      font=('Segoe UI Semibold', 12)).pack(pady=(0, 8))
        self.tk.Label(box, text=str(message), bg=BG, fg=MUTED, wraplength=520, justify='center').pack(pady=(0, 14))
        button(box, 'Закрыть', self.close).pack()

    def load(self, fetch, build, threaded=False):
        """Run fetch() while the spinner shows, then build(result) and reveal.

        threaded=True for calls that are safe off the Tk thread (Custom UI RPC);
        Unreal API calls must stay on the main thread, so they run after the
        spinner has painted instead."""
        results = queue.Queue()

        def finish():
            try:
                ok, value = results.get_nowait()
            except queue.Empty:
                self.window.after(40, finish)
                return
            if self.closed or not self.window.winfo_exists():
                return
            if not ok:
                self.fail(value)
                return
            try:
                build(value)
            except Exception as error:
                self.fail(error)
                return
            self.ready()

        def run():
            try:
                results.put((True, fetch()))
            except Exception as error:
                results.put((False, error))
        if threaded:
            threading.Thread(target=run, daemon=True).start()
            self.window.after(40, finish)
        else:
            self.window.after(80, lambda: (run(), finish()))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.spinner.stop()
        if self.on_close:
            self.on_close()
        if self.window.winfo_exists():
            self.window.destroy()


def confirm(owner, title, text, ok_text='Да', cancel_text='Отмена', danger=False):
    """Dark modal yes/no; returns True when confirmed."""
    import tkinter as tk
    result = []
    dialog = Dialog(owner, title, 560, 250, owner=owner)
    body = tk.Frame(dialog.content, bg=BG)
    body.pack(fill='both', expand=True, padx=24, pady=(20, 0))
    tk.Label(body, text=text, bg=BG, fg=TEXT, font=('Segoe UI', 10), wraplength=500,
             justify='left', anchor='nw').pack(fill='both', expand=True)
    bar = tk.Frame(dialog.content, bg=PANEL)
    bar.pack(fill='x', side='bottom')

    def answer(value):
        result.append(value)
        dialog.close()
    button(bar, cancel_text, lambda: answer(False)).pack(side='right', padx=(8, 16), pady=12)
    ok = button(bar, ok_text, lambda: answer(True), accent=not danger, danger=danger)
    ok.pack(side='right', pady=12)
    dialog.ready()
    dialog.window.bind('<Return>', lambda event: answer(True))
    try:
        dialog.window.grab_set()
    except tk.TclError:
        pass
    ok.focus_set()
    dialog.window.wait_window()
    return bool(result and result[0])
