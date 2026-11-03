# MESHFLOW Asset Pack Pipeline v0.31.1

## Custom UI windows
- The main window is created hidden and transparent, gets its custom title bar and
  placement, then fades in: no white first frame and no flash of the Windows caption.
- First launch centres the window on the primary work area (taskbar excluded); later
  launches restore the saved position.
- Updates, AI settings, «Сканировать Content» and the cleanup plan use one shared dark
  window (`dark_dialog.py`): compact MESHFLOW title bar instead of the Windows caption,
  drag by the title, Esc closes, centred over the main window.
- Each window opens dark with a loading spinner while its data loads (Content folders,
  cleanup plan, OpenAI key state, update settings), then shows the interface. Custom UI
  loads Unreal data on a background thread so the animation keeps running.
- No white panels or buttons: dark button bars, accent/danger colours, disabled buttons
  look disabled. Load errors are shown inside the dark window.
- Delete and install confirmations use the same dark style instead of native message boxes.
- Cleanup plan: header with pack and folder, delete/keep counts, coloured rows, scrollbar.

Validated in the window preview (loading and ready screenshots of every window and the
confirmation, centring, start-up time ≈0.5 s), unit tests, title bar smoke test and
window-state round trip. Same C++ module as v0.30.0. Unreal Engine 5.8.4 Win64.
