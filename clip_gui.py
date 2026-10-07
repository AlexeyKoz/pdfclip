"""clip_gui.py — PDF Clipper window (tkinter, part of standard Python).   py clip_gui.py
Tabs:  Manual — open a PDF, pick From / To items (or "Add all items"), queue, Run
       Auto   — every numbered item of a PDF or a whole folder of PDFs becomes its own image, no picking
       Plan   — repeat saved cuts from a plan .json (made by hand, by Auto, or by "Save queue as plan")
Images go to the output folder (default: output/ next to this script)."""
import os, re, sys, json, subprocess, threading, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip_pdf as C
import pymupdf as fitz

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "pdfclip_gui.cfg")
QUALITY = ["150 dpi — normal", "200 dpi — good", "300 dpi — small print / tables", "400 dpi — very fine",
           "600 dpi — maximum", "800 dpi — extra", "1000 dpi — extreme", "1200 dpi — limit (huge files)"]
A4_PT = 842

def open_path(path):
    if not path or not os.path.exists(path): return
    if hasattr(os, "startfile"): os.startfile(path)
    else: subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])

def load_cfg():
    try: return json.load(open(CFG, encoding="utf-8"))
    except Exception: return {}

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(f"PDF Clipper {C.__version__} — cut document sections into images")
        self.geometry("940x720"); self.minsize(800, 560)
        cfg = load_cfg(); V = lambda k, d: tk.StringVar(value=cfg.get(k, d))
        self.v_out, self.v_q, self.v_split = V("out", os.path.join(HERE, "output")), V("quality", QUALITY[2]), V("split", "0")
        self.v_src, self.v_dmin, self.v_dmax, self.v_pages = V("auto_src", ""), V("dmin", "1"), V("dmax", "2"), V("pages", "")
        self.v_save = tk.BooleanVar(value=cfg.get("save_plan", True))
        self.v_docs, self.v_plan = V("plan_docs", ""), V("plan_file", "")
        self.doc = None; self.heads = []; self.jobs = []; self.busy = []

        top = ttk.Frame(self, padding=(10, 8, 10, 0)); top.pack(fill="x")
        ttk.Label(top, text="Output folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.v_out).grid(row=0, column=1, columnspan=3, sticky="ew", padx=6)
        ttk.Button(top, text="Browse…", command=lambda: self.pick_dir(self.v_out, "Output folder")).grid(row=0, column=4)
        ttk.Button(top, text="Open", command=lambda: open_path(self.out_dir())).grid(row=0, column=5, padx=(4, 0))
        ttk.Label(top, text="Image quality:").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Combobox(top, values=QUALITY, textvariable=self.v_q, width=32).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(top, text="Split images taller than").grid(row=1, column=2, sticky="e", padx=(16, 4))
        f = ttk.Frame(top); f.grid(row=1, column=3, sticky="w")
        ttk.Spinbox(f, from_=0, to=50, width=4, textvariable=self.v_split).pack(side="left")
        ttk.Label(f, text="pages  (0 = never)").pack(side="left", padx=4)
        top.columnconfigure(1, weight=1)

        nb = ttk.Notebook(self); nb.pack(fill="x", padx=10, pady=6)
        self.build_manual(nb); self.build_auto(nb); self.build_plan(nb)
        nb.select(cfg.get("tab", 0))
        self.nb = nb

        lf = ttk.Frame(self, padding=(10, 0, 10, 8)); lf.pack(fill="both", expand=True)
        hdr = ttk.Frame(lf); hdr.pack(fill="x")
        ttk.Label(hdr, text="Log:").pack(side="left"); ttk.Button(hdr, text="Clear log", command=lambda: self.log.delete("1.0", "end")).pack(side="right")
        self.log = tk.Text(lf, height=10, wrap="word"); self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lf, command=self.log.yview); sb.pack(side="right", fill="y"); self.log["yscrollcommand"] = sb.set
        self.protocol("WM_DELETE_WINDOW", self.close)

    # ------------------------------------------------------------ shared
    def dpi(self):
        m = re.search(r"\d+", self.v_q.get()); return max(72, min(int(m.group()) if m else 300, 1200))
    def max_h(self):
        try: n = float(self.v_split.get())
        except ValueError: n = 0
        return n * A4_PT if n > 0 else None
    def out_dir(self):
        d = self.v_out.get().strip() or os.path.join(HERE, "output"); os.makedirs(d, exist_ok=True); return d
    def logw(self, s):
        self.after(0, lambda: (self.log.insert("end", s + "\n"), self.log.see("end")))
    def pick_dir(self, var, title):
        d = filedialog.askdirectory(title=title, initialdir=var.get() or None)
        if d: var.set(d)
    def pick_file(self, var, title, types):
        f = filedialog.askopenfilename(title=title, filetypes=types, initialdir=os.path.dirname(var.get()) or None)
        if f: var.set(f)
    def work(self, fn):
        """run fn in the background with the Run/Check buttons disabled"""
        for b in self.busy: b.state(["disabled"])
        def go():
            try: fn()
            except Exception as e: self.logw(f"!! {e}"); traceback.print_exc()
            self.after(0, lambda: [b.state(["!disabled"]) for b in self.busy])
        threading.Thread(target=go, daemon=True).start()
    def close(self):
        cfg = {"out": self.v_out.get(), "quality": self.v_q.get(), "split": self.v_split.get(), "auto_src": self.v_src.get(),
               "dmin": self.v_dmin.get(), "dmax": self.v_dmax.get(), "pages": self.v_pages.get(), "save_plan": self.v_save.get(),
               "plan_docs": self.v_docs.get(), "plan_file": self.v_plan.get(), "tab": self.nb.index("current")}
        try: json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=1)
        except Exception: pass
        self.destroy()

    # ------------------------------------------------------------ Manual
    def build_manual(self, nb):
        f = ttk.Frame(nb, padding=8); nb.add(f, text="  Manual  ")
        r = ttk.Frame(f); r.pack(fill="x")
        ttk.Label(r, text="PDF:").pack(side="left"); self.pdf_var = tk.StringVar()
        ttk.Entry(r, textvariable=self.pdf_var, state="readonly").pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(r, text="Open PDF…", command=self.open_pdf).pack(side="left")
        g = ttk.Frame(f); g.pack(fill="x", pady=(8, 0))
        ttk.Label(g, text="From item:").grid(row=0, column=0, sticky="w")
        self.start_cb = ttk.Combobox(g, width=82, state="readonly", height=30); self.start_cb.grid(row=0, column=1, columnspan=3, padx=6, pady=2, sticky="w")
        ttk.Label(g, text="To item:").grid(row=1, column=0, sticky="w")
        self.end_cb = ttk.Combobox(g, width=82, state="readonly", height=30); self.end_cb.grid(row=1, column=1, columnspan=3, padx=6, pady=2, sticky="w")
        self.start_cb.bind("<<ComboboxSelected>>", self.auto_end)
        ttk.Label(g, text="Image name:").grid(row=2, column=0, sticky="w"); self.name_var = tk.StringVar()
        ttk.Entry(g, textvariable=self.name_var, width=40).grid(row=2, column=1, sticky="w", padx=6, pady=2)
        ttk.Button(g, text="Add to queue", command=self.add_job).grid(row=2, column=2, padx=6, sticky="w")
        self.whole = tk.BooleanVar(value=False)
        ttk.Checkbutton(g, text="Whole document (ignore headings)", variable=self.whole, command=self.toggle_whole).grid(row=3, column=1, sticky="w", padx=6)
        a = ttk.Frame(f); a.pack(fill="x", pady=(6, 0))
        ttk.Label(a, text="Add all items down to level").pack(side="left")
        self.level_var = tk.StringVar(value="2"); ttk.Spinbox(a, from_=1, to=6, width=3, textvariable=self.level_var).pack(side="left", padx=4)
        ttk.Label(a, text="(1 = 6,  2 = 6.2,  3 = 6.2.1 — deeper sub-items stay inside their parent)").pack(side="left")
        ttk.Button(a, text="Add all items", command=self.add_all).pack(side="left", padx=8)
        self.jobs_lb = tk.Listbox(f, height=7, selectmode="extended"); self.jobs_lb.pack(fill="x", pady=(6, 0))
        b = ttk.Frame(f); b.pack(fill="x", pady=(6, 0))
        ttk.Button(b, text="Remove selected", command=self.del_job).pack(side="left")
        ttk.Button(b, text="Clear queue", command=self.clear_jobs).pack(side="left", padx=6)
        ttk.Button(b, text="Save queue as plan…", command=self.save_queue).pack(side="left")
        run = ttk.Button(b, text="▶ Run", command=self.run_manual); run.pack(side="right"); self.busy.append(run)

    def toggle_whole(self):
        st = "disabled" if self.whole.get() else "readonly"; self.start_cb.configure(state=st); self.end_cb.configure(state=st)

    def open_pdf(self):
        p = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not p: return
        try:
            doc = fitz.open(p); heads = C.scan_headings(doc, C.default_first_page(doc))
        except Exception as e: messagebox.showerror("Error", f"Cannot open PDF:\n{e}"); return
        self.doc, self.heads = doc, heads
        self.pdf_var.set(p); labels = [h[2] for h in heads]
        self.start_cb["values"] = labels; self.end_cb["values"] = labels + ["— to the end of the document —"]
        if labels: self.whole.set(False); self.toggle_whole(); self.start_cb.current(0); self.auto_end()
        else: self.whole.set(True); self.toggle_whole()
        bare = sum(1 for h in heads if not h[5])
        self.logw(f"Opened {os.path.basename(p)}: {len(doc)} pages, items found: {len(labels)}  (of them without title: {bare})")
        C.text_layer_warning(doc, 0, len(doc), self.logw)
        if not labels: messagebox.showwarning("No headings", "No numbered items found — 'Whole document' mode selected.")

    def auto_end(self, _=None):
        si = self.start_cb.current()
        if si < 0: return
        d = self.heads[si][3]
        self.end_cb.current(next((k for k in range(si + 1, len(self.heads)) if self.heads[k][3] <= d), len(self.heads)))

    def add_job(self):
        if not self.doc: messagebox.showinfo("PDF", "Open a PDF first."); return
        dpi, pdf = self.dpi(), self.pdf_var.get()
        if self.whole.get():
            name = self.name_var.get().strip() or re.sub(r"[^\w.-]+", "_", os.path.splitext(os.path.basename(pdf))[0])[:60]
            self.jobs.append((pdf, -1, -1, name, dpi, self.heads))
            self.jobs_lb.insert("end", f"{os.path.basename(pdf)}:  WHOLE DOCUMENT   ⇒ {name}.png   @{dpi}dpi"); self.name_var.set(""); return
        si, ei = self.start_cb.current(), self.end_cb.current()
        if si < 0 or ei < 0: return
        if ei < len(self.heads) and (self.heads[ei][0], self.heads[ei][1]) <= (self.heads[si][0], self.heads[si][1]):
            messagebox.showwarning("Order", "The end item must come after the start item."); return
        self._queue(si, ei, self.name_var.get().strip() or C.safe_name(self.heads[si][4], self.heads[si][5]), dpi); self.name_var.set("")

    def _queue(self, si, ei, name, dpi):
        h = self.heads
        self.jobs.append((self.pdf_var.get(), si, ei, name, dpi, h))
        self.jobs_lb.insert("end", f"{h[si][4]}  →  {'END' if ei >= len(h) else h[ei][4]}   ⇒ {name}.png   @{dpi}dpi   (p.{h[si][0]+1})")

    def add_all(self):
        if not self.heads: messagebox.showinfo("PDF", "Open a PDF with numbered items first."); return
        try: lvl = int(self.level_var.get())
        except ValueError: lvl = 2
        idx = [i for i, h in enumerate(self.heads) if h[3] <= lvl]
        dpi = self.dpi(); used = set(j[3] for j in self.jobs); n_added = 0
        for n, si in enumerate(idx):
            ei = idx[n + 1] if n + 1 < len(idx) else len(self.heads)
            if not C.has_own_content(self.doc, self.heads[si], self.heads[ei] if ei < len(self.heads) else None): continue  # heading only
            name = C.safe_name(self.heads[si][4], self.heads[si][5]); base, k = name, 2
            while name in used: name = f"{base}_{k}"; k += 1
            used.add(name); self._queue(si, ei, name, dpi); n_added += 1
        skipped = len(idx) - n_added
        self.logw(f"Added {n_added} item(s) down to level {lvl} @{dpi}dpi" + (f"  ({skipped} heading(s) without own text skipped)" if skipped else ""))

    def del_job(self):
        for i in reversed(self.jobs_lb.curselection()): self.jobs_lb.delete(i); del self.jobs[i]
    def clear_jobs(self): self.jobs_lb.delete(0, "end"); self.jobs.clear()

    def save_queue(self):
        if not self.jobs: messagebox.showinfo("Empty queue", "Add at least one job."); return
        f = filedialog.asksaveasfilename(title="Save queue as plan", defaultextension=".json", filetypes=[("JSON plan", "*.json")],
                                         initialdir=self.out_dir(), initialfile="plan.json")
        if not f: return
        plan = {"dpi": self.dpi(), "jobs": []}
        if self.max_h(): plan["max_height_pt"] = self.max_h()
        for pdf, si, ei, name, dpi, h in self.jobs:
            if not plan["jobs"] or plan["jobs"][-1]["pdf"] != os.path.basename(pdf): plan["jobs"].append({"pdf": os.path.basename(pdf), "clips": []})
            if si < 0: c = {"out": name + ".png", "from": "ALL", "to": "END"}
            else: c = {"out": name + ".png", "from": {"text": h[si][4], "page": h[si][0] + 1},
                       "to": "END" if ei >= len(h) else {"text": h[ei][4], "page": h[ei][0] + 1}}
            c["dpi"] = dpi; plan["jobs"][-1]["clips"].append(c)
        C.save_plan(plan, f); self.logw(f"Plan saved: {f}  (use it in the Plan tab with the folder of the PDF)")

    def run_manual(self):
        if not self.jobs: messagebox.showinfo("Empty queue", "Add at least one job."); return
        jobs, out, maxh = list(self.jobs), self.out_dir(), self.max_h()
        def go():
            ok, docs = 0, {}
            for pdf, si, ei, name, dpi, heads in jobs:
                try:
                    doc = docs.setdefault(pdf, fitz.open(pdf)); last = (len(doc) - 1, None)
                    if si < 0: s, e = (0, C.header_bottom(doc[0])), last
                    else: s = (heads[si][0], heads[si][1]); e = last if ei >= len(heads) else (heads[ei][0], heads[ei][1])
                    for n in C.save_images(C.clip_images(doc, s, e, dpi, None, maxh), os.path.join(out, name + ".png")):
                        w, hh = C.Image.open(n).size; self.logw(f"OK  {os.path.basename(n)}  ({w}x{hh}, {dpi} dpi, pages {s[0]+1}–{e[0]+1})")
                    ok += 1
                except Exception as ex: self.logw(f"ERROR {name}: {ex}"); traceback.print_exc()
            self.logw(f"Done: {ok} of {len(jobs)} — images in {out}")
        self.work(go)

    # ------------------------------------------------------------ Auto
    def build_auto(self, nb):
        f = ttk.Frame(nb, padding=8); nb.add(f, text="  Auto  ")
        ttk.Label(f, text="Every numbered item becomes its own image — for one PDF or a whole folder of PDFs (one subfolder each).").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(f, text="PDF file / folder:").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(f, textvariable=self.v_src).grid(row=1, column=1, sticky="ew", padx=6)
        b = ttk.Frame(f); b.grid(row=1, column=2, sticky="w")
        ttk.Button(b, text="File…", command=lambda: self.pick_file(self.v_src, "PDF", [("PDF", "*.pdf")])).pack(side="left")
        ttk.Button(b, text="Folder…", command=lambda: self.pick_dir(self.v_src, "Folder with PDF files")).pack(side="left", padx=4)
        o = ttk.Frame(f); o.grid(row=2, column=0, columnspan=4, sticky="w")
        ttk.Label(o, text="Levels from").pack(side="left"); ttk.Spinbox(o, from_=1, to=6, width=3, textvariable=self.v_dmin).pack(side="left", padx=3)
        ttk.Label(o, text="to").pack(side="left"); ttk.Spinbox(o, from_=1, to=6, width=3, textvariable=self.v_dmax).pack(side="left", padx=3)
        ttk.Label(o, text="(1 = 6,  2 = 6.2,  3 = 6.2.1)").pack(side="left", padx=(4, 18))
        ttk.Label(o, text="Pages:").pack(side="left"); ttk.Entry(o, textvariable=self.v_pages, width=9).pack(side="left", padx=3)
        ttk.Label(o, text="e.g. 4-120, empty = auto").pack(side="left")
        ttk.Checkbutton(f, text="Save what was found as plan_auto.json in the output folder (edit it, re-run in the Plan tab)", variable=self.v_save).grid(row=3, column=0, columnspan=4, sticky="w", pady=6)
        r = ttk.Frame(f); r.grid(row=4, column=0, columnspan=4, sticky="w")
        b1 = ttk.Button(r, text="Check (dry run)", command=lambda: self.run_auto(True)); b1.pack(side="left")
        b2 = ttk.Button(r, text="▶ Run — write images", command=lambda: self.run_auto(False)); b2.pack(side="left", padx=6)
        self.busy += [b1, b2]; f.columnconfigure(1, weight=1)

    def run_auto(self, dry):
        src = self.v_src.get().strip()
        if not os.path.exists(src): messagebox.showerror("PDF", "Choose a PDF file or a folder with PDFs."); return
        try:
            dmin, dmax = sorted((int(self.v_dmin.get()), int(self.v_dmax.get())))
            pages = C.parse_range(self.v_pages.get(), None, None)
        except ValueError as e: messagebox.showerror("Settings", f"Check the fields:\n{e}"); return
        out, dpi, maxh, save = self.out_dir(), self.dpi(), self.max_h(), self.v_save.get()
        docs = src if os.path.isdir(src) else os.path.dirname(src)
        def go():
            self.logw(f"--- AUTO {'CHECK' if dry else 'RUN'}: levels {dmin}-{dmax}, {dpi} dpi -> {out}")
            plan = C.auto_plan(src, dmin, dmax, pages, dpi, log=self.logw)
            if maxh: plan["max_height_pt"] = maxh
            if save:
                p = os.path.join(out, "plan_auto.json"); C.save_plan(plan, p); self.logw(f"plan saved: {p}")
            C.run_plan(plan, docs, out, dry=dry, log=self.logw)
        self.work(go)

    # ------------------------------------------------------------ Plan
    def build_plan(self, nb):
        f = ttk.Frame(nb, padding=8); nb.add(f, text="  Plan  ")
        ttk.Label(f, text="Repeat saved cuts: a plan .json lists PDFs (full name or part of it) and From / To anchors — see README.").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(f, text="PDF folder:").grid(row=1, column=0, sticky="w", pady=(8, 2))
        ttk.Entry(f, textvariable=self.v_docs).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(f, text="Browse…", command=lambda: self.pick_dir(self.v_docs, "Folder with the PDF files")).grid(row=1, column=2, sticky="w")
        ttk.Label(f, text="Plan (.json):").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(f, textvariable=self.v_plan).grid(row=2, column=1, sticky="ew", padx=6)
        b = ttk.Frame(f); b.grid(row=2, column=2, sticky="w")
        ttk.Button(b, text="Browse…", command=lambda: self.pick_file(self.v_plan, "Plan", [("JSON plan", "*.json")])).pack(side="left")
        ttk.Button(b, text="Edit", command=lambda: open_path(self.v_plan.get())).pack(side="left", padx=4)
        r = ttk.Frame(f); r.grid(row=3, column=0, columnspan=4, sticky="w", pady=(10, 0))
        b1 = ttk.Button(r, text="Check (dry run)", command=lambda: self.run_plan(True)); b1.pack(side="left")
        b2 = ttk.Button(r, text="▶ Run — write images", command=lambda: self.run_plan(False)); b2.pack(side="left", padx=6)
        self.busy += [b1, b2]; f.columnconfigure(1, weight=1)

    def run_plan(self, dry):
        docs, pf = self.v_docs.get().strip(), self.v_plan.get().strip()
        if not os.path.isfile(pf): messagebox.showerror("Plan", "Choose the plan .json file."); return
        if not os.path.isdir(docs): docs = os.path.dirname(pf); self.v_docs.set(docs)
        try: plan = json.load(open(pf, encoding="utf-8-sig"))
        except Exception as e: messagebox.showerror("Plan", f"Cannot read the plan:\n{e}"); return
        out, maxh = self.out_dir(), self.max_h()
        if maxh and "max_height_pt" not in plan: plan["max_height_pt"] = maxh
        plan.setdefault("dpi", self.dpi())
        def go():
            self.logw(f"--- PLAN {'CHECK' if dry else 'RUN'}: {os.path.basename(pf)} | PDFs: {docs} -> {out}")
            C.run_plan(plan, docs, out, dry=dry, log=self.logw)
        self.work(go)

if __name__ == "__main__":
    if "--version" in sys.argv: sys.exit(f"pdfclip {C.__version__}")
    App().mainloop()
