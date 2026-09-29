@echo off
setlocal
cd /d "%~dp0"
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py -m PyInstaller --noconfirm --clean --onefile --windowed --name Ksiegi_CzarnoZlote app.py
if errorlevel 1 exit /b 1
echo Gotowe: dist\Ksiegi_CzarnoZlote.exe
