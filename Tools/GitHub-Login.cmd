@echo off
set "MESHFLOW_GH=%~dp0..\..\..\Saved\ReleaseTools\gh.exe"
if not exist "%MESHFLOW_GH%" (
  echo GitHub CLI not found. Ask the agent to set up the official GitHub CLI.
  pause
  exit /b 1
)
"%MESHFLOW_GH%" auth login --hostname github.com --git-protocol https --web
pause
