"""Scrollable notebook form; width follows viewport, height follows content."""
import tkinter as tk
from tkinter import ttk


class ScrollPage(ttk.Frame):
    def __init__(self, notebook):
        super().__init__(notebook)
        self.canvas = tk.Canvas(self, background='#20232b', highlightthickness=0,
                                borderwidth=0, yscrollincrement=24)
        self.bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.content = ttk.Frame(self.canvas, padding=10)
        self.window_id = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.content.bind('<Configure>', self.resize_content)
        self.canvas.bind('<Configure>', self.resize_view)
        self.canvas.configure(yscrollcommand=self.bar.set)

    def resize_content(self, event=None):
        height = max(self.canvas.winfo_height(), self.content.winfo_reqheight())
        if int(float(self.canvas.itemcget(self.window_id, 'height'))) != height:
            self.canvas.itemconfigure(self.window_id, height=height)
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def resize_view(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width,
                                  height=max(event.height, self.content.winfo_reqheight()))
        self.resize_content()

    def wheel(self, event):
        if self.content.winfo_reqheight() <= self.canvas.winfo_height():
            return
        delta = event.delta
        if delta:
            self.canvas.yview_scroll(-max(1, abs(delta)//120) if delta > 0 else max(1, abs(delta)//120), 'units')
            return 'break'

    def reveal(self, widget):
        self.update_idletasks()
        top = widget.winfo_rooty()-self.canvas.winfo_rooty()
        bottom = top+widget.winfo_height()
        height = self.canvas.winfo_height()
        shift = top-8 if top < 8 else bottom-height+8 if bottom > height-8 else 0
        if shift:
            total = max(self.content.winfo_height(), 1)
            self.canvas.yview_moveto((self.canvas.canvasy(0)+shift)/total)


def page_for(widget):
    while widget is not None:
        if isinstance(widget, ScrollPage):
            return widget
        widget = getattr(widget, 'master', None)


def route_wheel(event):
    # Nested scrollable editors retain their own wheel; comboboxes don't also scroll the page.
    if event.widget.winfo_class() in ('Text', 'Treeview', 'Listbox', 'TCombobox', 'TSpinbox', 'Scrollbar', 'TScrollbar'):
        return
    page = page_for(event.widget)
    if page:
        return page.wheel(event)


def route_focus(event):
    if event.widget.winfo_class() in ('TEntry', 'TCombobox', 'TSpinbox', 'TButton', 'TCheckbutton'):
        page = page_for(event.widget)
        if page:
            page.reveal(event.widget)
