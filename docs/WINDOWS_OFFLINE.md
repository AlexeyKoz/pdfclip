# Running PDF Clipper on an offline or locked-down Windows PC

## 1. Prepare the libraries (on any PC with internet)

Download the wheels for the Python version installed on the **target** PC (check it there with `py -3 --version`):

```powershell
cd C:\pdfclip
py -3 -m pip download pymupdf pillow -d wheels --only-binary=:all: --python-version 3.13 --platform win_amd64
```

Replace `3.13` with the target version (3.10 … 3.14). You can run the command several times with different
versions into the same `wheels` folder. Copy the whole `pdfclip` folder (with `wheels`) to the target PC.

`run_gui.bat` / `run.bat` install from `wheels` automatically and fall back to the internet if the folder is missing
or does not fit.

## 2. Start without .bat files (when antivirus blocks scripts)

Open **PowerShell** (Start → `powershell` → Enter), paste the whole block, press Enter.
If your folder is not `C:\pdfclip`, fix the first line.

```powershell
cd "C:\pdfclip"
py -3 --version
py -3 -m venv venv
.\venv\Scripts\python.exe -m pip install --no-index --find-links wheels pymupdf pillow
.\venv\Scripts\pythonw.exe clip_gui.py
```

What happens: go to the folder → check Python → create a private environment `venv` inside the folder
(nothing changes on the system) → install the libraries from `wheels` without internet → open the window.

**Next times** only two lines:

```powershell
cd "C:\pdfclip"
.\venv\Scripts\pythonw.exe clip_gui.py
```

If PowerShell is not available, the same in **CMD**:

```bat
cd /d "C:\pdfclip"
py -3 -m venv venv
venv\Scripts\python.exe -m pip install --no-index --find-links wheels pymupdf pillow
venv\Scripts\pythonw.exe clip_gui.py
```

> Run the lines **in this order and after `cd`**. Running `py -3 -m venv venv` from `C:\Windows\System32`
> creates the environment there instead of in your folder.

## If something goes wrong

| Message | Fix |
|---------|-----|
| `py is not recognized` | Python missing or not on PATH — reinstall with *Add python to PATH*, or use `python` instead of `py -3`. |
| `Location 'wheels' is ignored` | You are not in the program folder — run the `cd` line first. |
| `No matching distribution found` | The wheels are for another Python version — see step 1, or with internet: `venv\Scripts\python.exe -m pip install pymupdf pillow`. |
| The window does not open, no error | Start with `python.exe` instead of `pythonw.exe` to see the message: `venv\Scripts\python.exe clip_gui.py` |
| Antivirus blocks pip / venv | Ask IT to whitelist the folder: it is plain Python plus PyMuPDF and Pillow from pypi.org. |
| A cut looks wrong | Check the page numbers next to the headings; table rows can look like headings — pick the real section numbers. |
