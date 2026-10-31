"""Custom dark indicators and consistent states for Tk/ttk controls."""
import tkinter as tk


def apply(owner, style):
    images = []
    for selected, disabled, focus in ((False,False,False),(True,False,False),
                                      (False,True,False),(True,True,False),
                                      (False,False,True),(True,False,True)):
        image = tk.PhotoImage(master=owner.root, width=18, height=18)
        image.put('#20232b', to=(0,0,18,18))
        edge = '#598de0' if focus else '#343b49'
        fill = '#303a4d' if disabled else '#3975da' if selected else '#15181f'
        image.put(edge, to=(2,2,16,16))
        image.put(fill, to=(3,3,15,15))
        if selected:
            for x,y in ((5,8),(6,9),(7,10),(8,9),(9,8),(10,7),(11,6),(12,5)):
                image.put('#9aa8bc' if disabled else '#e4edff', to=(x,y,x+2,y+2))
        images.append(image)
    owner._control_images = images
    if 'Pipeline.Check.indicator' not in style.element_names():
        style.element_create('Pipeline.Check.indicator', 'image', images[0],
            ('disabled','selected',images[3]), ('disabled',images[2]),
            ('focus','selected',images[5]), ('focus',images[4]), ('selected',images[1]), sticky='w')
    style.layout('TCheckbutton', [('Checkbutton.padding', {'sticky':'nswe', 'children':[
        ('Pipeline.Check.indicator', {'side':'left','sticky':''}),
        ('Checkbutton.label', {'side':'left','sticky':'w'})]})])
    style.configure('TRadiobutton', background='#282e3b', foreground='#aab6ca', padding=(14,8),
                    borderwidth=0, focuscolor='#282e3b')
    style.layout('TRadiobutton', [('Radiobutton.padding', {'sticky':'nswe', 'children':[
        ('Radiobutton.label', {'sticky':'nswe'})]})])
    style.map('TRadiobutton', background=[('selected','#304e79'),('active','#343f52')],
              foreground=[('disabled','#758094'),('focus','#8ebaff'),('selected','#e4edff')])
    style.configure('TSpinbox', fieldbackground='#15181f', background='#282e3b', foreground='#eef0f5',
                    arrowcolor='#a9bded', insertcolor='#eef0f5', padding=5, borderwidth=1,
                    bordercolor='#363b47', lightcolor='#363b47', darkcolor='#363b47', relief='flat')
    style.map('TSpinbox', fieldbackground=[('readonly','#15181f'),('disabled','#20232b')],
              foreground=[('disabled','#758094')], background=[('active','#343f52')],
              bordercolor=[('focus','#598de0'),('!focus','#363b47')],
              lightcolor=[('focus','#598de0'),('!focus','#363b47')],
              darkcolor=[('focus','#598de0'),('!focus','#363b47')])
    style.configure('Horizontal.TProgressbar', background='#4e8cf2', troughcolor='#15181f',
                    bordercolor='#20232b', lightcolor='#15181f', darkcolor='#15181f', borderwidth=0)
    style.configure('TButton', bordercolor='#343b4b', lightcolor='#343b4b', darkcolor='#343b4b',
                    focuscolor='#598de0', relief='flat')
    style.configure('Treeview', bordercolor='#20232b', lightcolor='#20232b', darkcolor='#20232b')
    owner.root.option_add('*Menu.background', '#20232b')
    owner.root.option_add('*Menu.foreground', '#e5e8ef')
    owner.root.option_add('*Menu.activeBackground', '#304e79')
    owner.root.option_add('*Menu.activeForeground', '#eef0f5')
    owner.root.option_add('*Menu.borderWidth', 0)
    owner.root.option_add('*Text.highlightThickness', 0)
    owner.root.option_add('*Text.borderWidth', 0)
