@echo off
REM Run from any folder: full path to this .bat, then your arguments.
cd /d "%~dp0"
python "%~dp0pdf_page_screenshots.py" %*
