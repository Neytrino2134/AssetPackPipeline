"""Real Custom UI layout across modes, scrolling and minimum window size."""
import json
import traceback
from preview_custom_chrome import create_window,plugin
from asset_pack_pipeline.custom_chrome import TITLE
window=create_window();root=window.root
result={'passed':False,'checks':[]}
def bounds(widget):
    return [widget.winfo_rootx()-root.winfo_rootx(),widget.winfo_rooty()-root.winfo_rooty(),widget.winfo_width(),widget.winfo_height()]
def check(index=0):
    try:
        modes=('Быстрый старт','Мастер','Профессиональный')
        if index==6:
            result['passed']=True;finish();return
        mode=modes[index%3];window.mode.set(mode);window.switch_mode()
        if index<3:root.geometry('1200x860')
        else:root.geometry('1100x800')
        def inspect():
            try:
                actions=window.expert_actions if mode=='Профессиональный' else window.guide_actions
                assert actions.master is window.controls_frame
                for widget in (actions,window.state_label,window.progress):
                    x,y,w,h=bounds(widget)
                    assert widget.winfo_ismapped() and y>=0 and y+h<=root.winfo_height(),(mode,bounds(widget))
                before=bounds(actions)
                if mode!='Профессиональный':
                    window.guided_frame.canvas.yview_moveto(1)
                else:
                    next(iter(window.scroll_pages.values())).canvas.yview_moveto(1)
                root.after(80,lambda:scrolled(before,actions,index,mode))
            except Exception:fail()
        root.after(150,inspect)
    except Exception:fail()
def scrolled(before,actions,index,mode):
    try:
        assert bounds(actions)==before
        assert root.title()==TITLE and 'v0.27.0' in TITLE
        result['checks'].append({'mode':mode,'root':[root.winfo_width(),root.winfo_height()],'actions':before,'pinned':True})
        check(index+1)
    except Exception:fail()
def fail():
    result['error']=traceback.format_exc();finish()
def finish():
    output=plugin.parents[1]/'Saved/PinnedFooter0270.json'
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    window.close(prompt=False)
root.after(200,check);root.mainloop()
assert result['passed'],result
