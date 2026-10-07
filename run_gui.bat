@echo off
rem PDF Clipper — first start creates a private Python environment (venv) inside this folder.
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
    echo Creating environment...
    py -3 -m venv venv || python -m venv venv || (echo Python 3.10+ not found. Install it from python.org with "Add python to PATH". & pause & exit /b 1)
    if exist wheels (
        venv\Scripts\python.exe -m pip install --no-index --find-links wheels -r requirements.txt || venv\Scripts\python.exe -m pip install -r requirements.txt
    ) else (
        venv\Scripts\python.exe -m pip install -r requirements.txt
    )
)
start "" venv\Scripts\pythonw.exe clip_gui.py
