@echo off
setlocal
cd /d "%~dp0"
echo Installing EasyOCR (includes PyTorch; first time may take a while)...
python -m pip install -r "%~dp0requirements-ocr.txt"
if errorlevel 1 exit /b 1
echo.
echo Done. First run of images_to_text.py will download OCR models (needs internet once).
exit /b 0
