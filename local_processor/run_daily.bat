@echo off
REM TikTok Movie Monitor — daily local processor
REM Triggered by Windows Task Scheduler at 02:00.

cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8

REM Ensure D: drive output directory exists
if not exist "D:\搬运\01原素材带字幕" mkdir "D:\搬运\01原素材带字幕"
if not exist "D:\搬运\_索引"          mkdir "D:\搬运\_索引"

REM Run the processor (look back 26 hours so a missed day still gets caught up)
"D:\搬运\.venv\Scripts\python.exe" -m local_processor.runner --hours 26 >> "D:\搬运\_log.txt" 2>&1

exit /b %ERRORLEVEL%
