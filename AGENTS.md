# AssetPackPipeline releases

When the user requests "push + update", "пуш + обновление", or a release, follow
Docs/AgentReleaseWorkflow.md. The requested result includes a published stable
GitHub Release with the compiled ZIP and matching update manifest, not only a git push.
Do not publish a release for an ordinary edit or a request for push only.
Use Tools/publish_release.py; perform checks and local preparation before any
authentication handoff. Never read or print authentication tokens. Initial browser
login through Tools/GitHub-Login.cmd is performed by the user.
Do not move an existing published tag or silently overwrite a published ZIP.
