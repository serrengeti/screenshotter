@echo off
setlocal
cd /d "%~dp0"
echo Installing Playwright for the Python that runs when you type: python
echo.
python -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo.
  echo pip failed. Use the same Python you use to run pdf_page_screenshots.py
  echo Example:  py -3 -m pip install -r "%~dp0requirements.txt"
  exit /b 1
)
echo.
echo Downloading Chromium for Playwright (one-time)...
python -m playwright install chromium
if errorlevel 1 exit /b 1
echo.
echo Done. Run your pdf_page_screenshots.py command again.
exit /b 0
