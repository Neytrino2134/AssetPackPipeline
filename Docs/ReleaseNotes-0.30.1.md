# MESHFLOW Asset Pack Pipeline v0.30.1

- The window journal is now also written to disk:
  `Saved/AssetPackPipeline/Logs/journal-<date-time>.log`, one file per window session
  (last 30 kept), with plugin version, UI type and full Python tracebacks for errors.
- When the status shows «Ошибка — подробности в журнале», a «Журнал в папке…» button
  opens Explorer with the journal file selected, so it can be copied and sent.
- Custom UI also records errors of steps executed inside Unreal and lost connections
  to Unreal; failed step messages now include the path of the run's report.json.

Same C++ module as v0.30.0. Validated: 157 unit tests, Custom UI preview (error →
journal file with traceback → button → Explorer /select), title bar smoke test and
window-state round trip. Unreal Engine 5.8.4 Win64.
