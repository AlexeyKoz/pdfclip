"""
clip_batch.py — PDF Clipper without the window.

  py clip_batch.py                         jobs.txt next to this script, PDFs from input/, images to output/
  py clip_batch.py my_jobs.txt             another job list
  py clip_batch.py plan.json [--docs DIR]  a JSON plan (see README); PDFs looked up in DIR (default input/)
  py clip_batch.py --auto FILE_OR_DIR [--depth 1-2] [--pages 4-200] [--save-plan plan.json]
                                           every numbered item becomes its own image, no list needed
Common options:  --out DIR   --dpi N   --dry (only check what would be cut)   --only NAME.png   --version

jobs.txt — one job per line:   pdf file | from | to | image name [| dpi]
  from : 6.2 / 6.2.1 (also items without title text) · 5. GENERAL (number + title, fuzzy) · any line start · ALL
  to   : same, or END (end of document) or NEXT (next item of the same or higher level)
  "dpi = 300" sets the quality for the following lines. Lines starting with # are comments.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip_pdf as C

HERE = os.path.dirname(os.path.abspath(__file__))
A = sys.argv[1:]
def opt(k, d=None): return A[A.index(k) + 1] if k in A else d

if "--version" in A: sys.exit(f"pdfclip {C.__version__}")
if "-h" in A or "--help" in A: sys.exit(__doc__)
values = {opt(k) for k in ("--out", "--dpi", "--docs", "--auto", "--depth", "--pages", "--save-plan", "--only")}
pos = [x for x in A if not x.startswith("--") and x not in values]
out = opt("--out", os.path.join(HERE, "output")); docs = opt("--docs", os.path.join(HERE, "input"))
dpi = int(opt("--dpi")) if opt("--dpi") else None; dry = "--dry" in A
os.makedirs(out, exist_ok=True); os.makedirs(os.path.join(HERE, "input"), exist_ok=True)

try:
    if "--auto" in A:
        src = opt("--auto"); dmin, dmax = C.parse_range(opt("--depth", "1-2"), 1, 6)
        plan = C.auto_plan(src, dmin, dmax, C.parse_range(opt("--pages"), None, None), dpi or 300)
        if opt("--save-plan"): C.save_plan(plan, opt("--save-plan")); print(f"plan saved: {opt('--save-plan')}")
        docs = src if os.path.isdir(src) else os.path.dirname(os.path.abspath(src))
    else:
        f = pos[0] if pos else os.path.join(HERE, "jobs.txt")
        if not os.path.exists(f): sys.exit(f"not found: {f}")
        if f.lower().endswith(".json"):
            import json; plan = json.load(open(f, encoding="utf-8-sig"))
        else:
            plan, problems = C.parse_jobs(f, dpi or 300)
            for p in problems: print(p)
    done, errors = C.run_plan(plan, docs, out, dry=dry, only=opt("--only"), dpi=dpi)
except FileNotFoundError as e:
    sys.exit(str(e))
sys.exit(1 if errors else 0)
