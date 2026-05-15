@echo off
REM TikTok Movie Monitor — startup launcher
REM Placed in Windows Startup folder. Runs every time you log in.
REM Internally checks "should I actually run now?" using a stamp file.

cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8
"D:\搬运\.venv\Scripts\python.exe" -m local_processor.scheduler
