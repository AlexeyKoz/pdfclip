r"""
clip_pdf.py — PDF Clipper engine. Cuts a section range of a PDF into ONE image (text + figures, headers/footers removed).

Used by clip_gui.py (window) and clip_batch.py (jobs.txt / plan.json / auto). Direct command line:
  py clip_pdf.py <file.pdf> <from> <to|END> <out.png> [--dpi 300] [--first-page N]
  py clip_pdf.py --version
Anchors ("from" / "to"):
  6.2                       numbered item, also when it has NO title text in the document
  6.3. Power Supply         number + title, compared fuzzily (dashes, spacing, a typo, a title broken over 2 lines)
  General description       text at the start of a line
  ^6\.2\s                   a regular expression (starts with ^ or (?)
  END / NEXT                end of the document / next item of the same or higher level
Image quality: 150 dpi normal, 300 small print / tables, 600-1200 maximum (big files, lots of memory).
"""
import sys, os, re, json, difflib, unicodedata
import pymupdf as fitz

__version__ = "1.1.0"
from PIL import Image, ImageChops
Image.MAX_IMAGE_PIXELS = None   # whole-document images can be very tall

TOC_ENTRY = re.compile(r"(?:\.\s?){3,}\s*\d{1,4}\s*$")                   # "6.2 Title ........ 12"
TOC_PAGE = re.compile(r"\b(table of contents|contents|table of figures|table of tables|содержание|оглавление)\b|תוכן עניינים", re.I)
NUM_ONLY = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){0,5})\.?$")
HEAD_RX = re.compile(r"^(?:(?:step|section|chapter|appendix|annex|part)\s+)?(\d{1,2}(?:\.\d{1,3}){0,5}|[A-Z]|[IVX]{1,5})(?:[.):]\s*|\s+|$)(.*)$", re.I)
UNIT_RE = re.compile(r"^(?:[\d±=<>×]|[x*]\s*\d|(?:v|mv|kv|ma|ua|µa|hz|khz|mhz|ghz|mm|cm|kg|ohm|ω|db|dbm|ms|us|µs|ns|vdc|vac|nm|µm|mw|kw|sec|w)\b|[%°])", re.I)

def is_toc_page(page):
    txt = page.get_text()
    return bool(TOC_PAGE.search(txt[:600])) and len(TOC_ENTRY.findall(txt.replace("\n", "  \n"))) >= 3

def page_rows(page):
    """text lines of a page as (x0, y0, text, bold, size), top-to-bottom; a number that sits in its own span/block
    with the title next to it on the same line ("6.2" | "Title") is also returned joined"""
    ls = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            sp = [s for s in l["spans"] if s["text"].strip()]
            if not sp: continue
            t = re.sub(r"\s+", " ", "".join(s["text"] for s in l["spans"])).strip()
            bold = any("bold" in s["font"].lower() or s["flags"] & 16 for s in sp)
            ls.append((l["bbox"][0], l["bbox"][1], l["bbox"][2], t, bold, max(s["size"] for s in sp)))
    ls.sort(key=lambda l: (round(l[1] / 3), l[0]))
    out = []
    for i, (x0, y0, x1, t, bold, size) in enumerate(ls):
        out.append((x0, y0, t, bold, size))
        if NUM_ONLY.match(t):
            nxt = [l for l in ls[i + 1:i + 6] if abs(l[1] - y0) < 6 and l[0] >= x1 - 1]
            if nxt: out.append((x0, y0, t + " " + nxt[0][3], bold or nxt[0][4], max(size, nxt[0][5])))
    return out

def find_heading(doc, pattern, first_page=0, after=None):
    """first text LINE near the left margin matching the regex (every line of a block is checked, TOC skipped)"""
    rx = re.compile(pattern)
    for pno in range(first_page, len(doc)):
        if is_toc_page(doc[pno]): continue
        for x0, y0, t, *_ in page_rows(doc[pno]):
            if x0 < 200 and rx.search(t) and not TOC_ENTRY.search(t) and (after is None or (pno, y0) > tuple(after)):
                return pno, y0
    return None

def _step(a, b):
    """can section number b follow a?  0 = no, 1 = yes, <1 = yes with skipped numbers"""
    if len(b) > len(a) and b[:len(a)] == a and b[len(a)] in (1, 2) and all(x <= 1 for x in b[len(a) + 1:]): return 1.0
    for i in range(len(a)):
        if b[:i] == a[:i] and len(b) > i and a[i] < b[i] <= a[i] + 4 and all(x <= 1 for x in b[i + 1:]):
            return 1.0 - 0.3 * (b[i] - a[i] - 1)
    return 0

def scan_headings(doc, first_page=0, last_page=None):
    """all items and sub-items: 5. Title / 6.2 Title / 6.2.1 / bare "6.2" without any title text.
    returns [(page, y, label, depth, num, title)] in document order.
    Bare numbers are kept only when they fit the numbering sequence (so "6.3 V" or a "6.4" table cell is ignored)."""
    cands = []; rng = range(first_page, min(last_page or len(doc), len(doc)))
    rows = {p: page_rows(doc[p]) for p in rng if not is_toc_page(doc[p])}
    sizes = sorted(r[4] for rs in rows.values() for r in rs) or [10]
    body = sizes[len(sizes) // 2]                                                  # typical body-text size
    for pno, prow in rows.items():
        page = doc[pno]
        H = page.rect.height
        for x0, y0, t, bold, size in prow:
            if x0 >= 260 or len(t) >= 140 or y0 < H * 0.04 or y0 > H * 0.95 or TOC_ENTRY.search(t): continue
            m = HEAD_RX.match(t)
            if not m: continue
            num, title = m.group(1), m.group(2).strip()
            numeric = num[0].isdigit(); depth = num.count(".") + 1 if numeric else 1
            if numeric and depth >= 2:
                if UNIT_RE.match(title): continue                                   # measured value, not a heading
            else:                                                                   # top level: 6 / A / IV
                if not title or re.search(r"\b\d{8,}\b", title) or not (title[0].isupper() or title[0].isdigit()): continue
                if not (bold or size >= body * 1.1): continue                       # "7. Tighten the screws" is a list item
            if cands and cands[-1][0] == pno and abs(cands[-1][1] - y0) < 3 and cands[-1][4] == num:   # joined duplicate
                if len(title) > len(cands[-1][5]): cands[-1] = (pno, y0, None, depth, num, title, bold)
                continue
            cands.append((pno, y0, None, depth, num, title, bold))
    # numbering-sequence check for 6.2-style items: longest believable chain wins
    sub = [i for i, c in enumerate(cands) if c[4][0].isdigit() and c[3] >= 2]
    keep = set(i for i, c in enumerate(cands) if i not in set(sub) or c[5])           # titled items are always kept
    if sub:
        parts = {i: tuple(int(x) for x in cands[i][4].split(".")) for i in sub}
        best, prev = {}, {}
        for jj, j in enumerate(sub):
            sc = 1 + 0.5 * bool(cands[j][5]) + 0.3 * cands[j][6]; best[j], prev[j] = sc, None
            for i in sub[max(0, jj - 400):jj]:
                st = _step(parts[i], parts[j])
                if st and best[i] + sc * st > best[j]: best[j], prev[j] = best[i] + sc * st, i
        j = max(sub, key=lambda k: best[k])
        while j is not None: keep.add(j); j = prev[j]
    res = []
    for i, (pno, y0, _, depth, num, title, bold) in enumerate(cands):
        if i not in keep: continue
        label = f"{'    ' * (depth - 1)}{num}  {title[:60] if title else '·  (number only)'}   [p.{pno+1}]"
        res.append((pno, y0, label, depth, num, title))
    res.sort(key=lambda h: (h[0], h[1]))
    return res

def safe_name(num, title=""):
    return re.sub(r"[^\w.-]+", "_", f"{num} {title}".strip()).strip("_")[:60] or "clip"

# words that mark a page footer (extend for your documents' templates)
FOOTER_RX = re.compile(r"\b(page\s+\d+|classification|confidential|proprietary|all rights reserved|copyright|©)", re.I)

def footer_y(page):
    """top of the page footer: footer-like text in the bottom 15 % of the page, or any text in the bottom 6 %"""
    H = page.rect.y1
    ys = [b[1] for b in page.get_text("blocks") if b[1] > H * 0.85 and (FOOTER_RX.search(b[4]) or b[1] > H * 0.94)]
    fy = min(ys) - 4 if ys else H - 60
    return max(fy, H * 0.72)          # never treat more than the bottom 28 % as footer

def header_bottom(page):
    ys = [r.y1 + 14 for img in page.get_images(full=True) for r in page.get_image_rects(img[0]) if r.y0 < 130 and r.height < 90]
    # header text block (Revision / Reference / File Name) -> everything up to the rule below it is header
    hb = [b[3] for b in page.get_text("blocks") if b[1] < 220 and re.search(r"Revision:|Reference:|File Name", b[4])]
    if hb:
        top = max(hb)
        ys.append(top + 10)
        ys += [d["rect"].y1 + 8 for d in page.get_drawings() if top - 5 <= d["rect"].y0 <= top + 40 and d["rect"].height < 4 and d["rect"].width > 100 and d["rect"].x0 < 60]
    # header rule: may be one wide line or several segments on the same y
    segs = [d["rect"] for d in page.get_drawings() if d["rect"].y0 < 150 and d["rect"].height < 4 and d["rect"].width > 100 and d["rect"].x0 < 60]
    ys += [r.y1 + 8 for r in segs]
    # header table/vertical separators
    ys += [d["rect"].y1 + 8 for d in page.get_drawings() if d["rect"].y0 < 60 and d["rect"].height > 40 and d["rect"].width < 6]
    hb = max(ys) if ys else 120
    return min(hb, page.rect.y1 * 0.30)          # never treat more than the top 30 % as header

def trim(im, pad=8):
    bbox = ImageChops.difference(im, Image.new("RGB", im.size, "white")).getbbox()
    if not bbox: return None
    return im.crop((0, max(bbox[1] - pad, 0), im.width, min(bbox[3] + pad, im.height)))

def band_colors(page):
    """fill colours of large background shapes (e.g. grey side bands) to be whitened"""
    cols = set()
    for d in page.get_drawings():
        r = d["rect"]
        if d.get("fill") and r.width > 120 and r.height > 250:
            cols.add(tuple(int(round(c * 255)) for c in d["fill"]))
    return cols

def whiten(im, cols, tol=6):
    """paint background bands of the given colours white (fast, PIL masks instead of a per-pixel loop)"""
    if not cols: return im
    white = Image.new("RGB", im.size, "white")
    for c in cols:
        r, g, b = ImageChops.difference(im, Image.new("RGB", im.size, c)).split()
        mask = ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda v: 255 if v <= tol else 0, "L")
        im = Image.composite(white, im, mask)
    return im

def margin_band(page):
    """right-margin comment band (Word review export): x-range to white out entirely"""
    for d in page.get_drawings():
        r = d["rect"]
        if d.get("fill") and r.x0 > page.rect.width * 0.6 and r.height > 250 and r.x1 >= page.rect.width - 2: return r.x0
    return None

def clip_images(doc, start, end, dpi=150, margins=None, max_height_pt=None):
    """cut start=(page, y) .. end=(page, y | None = page end) into images.
    margins: None = detect headers/footers automatically, or {"top","bottom","left","right"} in points (fixed cut).
    max_height_pt: split into several images when taller (None = always one image). Returns a list of PIL images."""
    (sp, sy), (ep, ey) = start, end
    x0, x1 = (margins["left"], margins["right"]) if margins else (30, 15)
    parts = []; p, y0 = sp, sy - 4
    while p <= ep:
        page = doc[p]
        fy = page.rect.y1 - margins["bottom"] if margins else footer_y(page)
        if margins: y0 = max(y0, margins["top"])
        y1 = min(ey - 2, fy) if (p == ep and ey is not None) else fy
        if y1 - y0 > 30:
            px = page.get_pixmap(clip=fitz.Rect(x0, y0, page.rect.x1 - x1, y1), dpi=dpi)
            im = Image.frombytes("RGB", (px.width, px.height), px.samples)
            mb = margin_band(page)
            if mb:
                from PIL import ImageDraw
                ImageDraw.Draw(im).rectangle([int((mb - x0) * dpi / 72), 0, im.width, im.height], fill="white")
            else:
                im = whiten(im, band_colors(page))
            im = trim(im)
            if im: parts.append(im)
        p += 1
        if p < len(doc): y0 = margins["top"] if margins else header_bottom(doc[p])
    if not parts: raise ValueError("nothing to clip between these headings (empty range)")
    limit = max_height_pt * dpi / 72 if max_height_pt else float("inf")
    groups, cur, h = [], [], 0
    for im in parts:
        if cur and h + im.height > limit: groups.append(cur); cur, h = [], 0
        cur.append(im); h += im.height + 12
    groups.append(cur)
    out = []
    for g in groups:
        W = max(i.width for i in g); H = sum(i.height for i in g) + 12 * (len(g) - 1)
        canvas = Image.new("RGB", (W, H), "white"); y = 0
        for im in g: canvas.paste(im, (0, y)); y += im.height + 12
        out.append(canvas)
    return out

def clip(doc, start, end, dpi=150, margins=None):
    """one stitched image (no splitting)"""
    return clip_images(doc, start, end, dpi, margins)[0]

def save_images(images, path):
    """name.png, or name-1.png, name-2.png ... when the clip was split; returns the written paths"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not path.lower().endswith(".png"): path += ".png"
    names = [path] if len(images) == 1 else [path[:-4] + f"-{i + 1}.png" for i in range(len(images))]
    for im, n in zip(images, names): im.save(n, optimize=True)
    return names

# ======================================================================== anchors (fuzzy headings)
MM = 72 / 25.4
NUM_RE = re.compile(r"^(\d+(?:\.\d+)*|appendix\s+[a-z])\.?\s*", re.I)
BARE = re.compile(r"^\d{1,2}(?:\.\d{1,3}){0,5}\.?$")

def norm(s):
    s = unicodedata.normalize("NFKC", s).replace("–", "-").replace("—", "-").replace("\\", "/").replace("\u00a0", " ")
    s = re.sub(r"[*_`]", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()

def default_first_page(doc):
    """title / revision / contents pages are skipped: 3 pages for documents longer than 6 pages"""
    return 3 if len(doc) > 6 else 0

def margins_pt(mm):
    """{"top": 18, "bottom": 15, "left": 8, "right": 8} in mm -> points (missing keys: those defaults)"""
    if not mm: return None
    d = {"top": 18, "bottom": 15, "left": 8, "right": 8, **mm}
    return {k: float(v) * MM for k, v in d.items()}

def anchor_lines(page):
    """(x0, y0, text, bold) per line near the left margin + a heading broken over two lines, joined"""
    rows = [r[:4] for r in page_rows(page)]
    for b in page.get_text("dict")["blocks"]:
        ls = []
        for l in b.get("lines", []):
            t = re.sub(r"\s+", " ", "".join(s["text"] for s in l["spans"])).strip()
            if t: ls.append((l["bbox"], t, max(s["size"] for s in l["spans"]), any("bold" in s["font"].lower() or s["flags"] & 16 for s in l["spans"])))
        for a, c in zip(ls, ls[1:]):
            if abs(a[2] - c[2]) < 0.6 and c[0][1] - a[0][3] < a[2] * 1.2:
                rows.append((a[0][0], a[0][1], a[1] + " " + c[1], a[3] and c[3]))
    return [r for r in rows if r[0] < 260]

class Ctx:
    """one opened PDF + its scanned headings, shared by all anchors of a job"""
    def __init__(self, doc, first_page=None, last_page=None):
        self.doc = doc
        self.pmin = default_first_page(doc) if first_page is None else first_page
        self.pmax = min(last_page or len(doc), len(doc))          # exclusive
        self._heads = None
    @property
    def heads(self):
        if self._heads is None: self._heads = scan_headings(self.doc, self.pmin, self.pmax)
        return self._heads
    def end(self): return (self.pmax - 1, None)

def head_label(h): return f"{h[4]} {h[5]}".strip()

def find_anchor(ctx, anchor, after=None, from_depth=None):
    """-> (page, y, found_text); y None = end of page. Raises LookupError."""
    if isinstance(anchor, str): anchor = {"text": anchor}
    text = str(anchor["text"]).strip(); key = text.upper(); pg = anchor.get("page")
    after = tuple(after) if after else (-1, -1e9)
    ok = lambda p, y: (p, y) > after and (pg is None or p == pg - 1)
    if key == "END": return (*ctx.end(), "END")
    if key == "NEXT":
        for h in ctx.heads:
            if (h[0], h[1]) > after and h[3] <= (from_depth or 99): return h[0], h[1], head_label(h)
        return (*ctx.end(), "END (no next item)")
    if text.startswith("^") or text.startswith("(?"):                    # regular expression
        r = find_heading(ctx.doc, text, max(ctx.pmin, after[0], 0) if pg is None else pg - 1, after if after[0] >= 0 else None)
        if r and ok(*r): return r[0], r[1], text
        raise LookupError(f"no line matches the expression {text!r}")
    want = norm(text)
    if BARE.match(want):                                                  # bare number: 6 / 6.2 / 6.2.1
        num = want.rstrip(".")
        for h in ctx.heads:
            if h[4] == num and ok(h[0], h[1]): return h[0], h[1], head_label(h)
        r = find_heading(ctx.doc, r"(?i)^" + re.escape(num).replace(r"\.", r"\.\s*") + r"\.?(?![\d.]\d)(?!\s*(?:v|mm|%|°)\b)",
                         ctx.pmin if pg is None else pg - 1, after if after[0] >= 0 else None)
        if r and ok(*r): return r[0], r[1], num + "  (outside the numbering sequence — check!)"
        raise LookupError(f"item {num!r} not found")
    if pg:                                                                # auto plans: item number on a known page
        for h in ctx.heads:
            if h[4].lower() == want.rstrip(".") and ok(h[0], h[1]): return h[0], h[1], head_label(h)
    m = NUM_RE.match(want)
    num, words = (m.group(1).lower(), want[m.end():].strip()) if m else (None, want)
    pages = [pg - 1] if pg else range(ctx.pmin, ctx.pmax)
    cands = []
    for pno in pages:
        page = ctx.doc[pno]
        if pg is None and is_toc_page(page): continue
        for x0, y0, t, bold in anchor_lines(page):
            if not ok(pno, y0) or (pg is None and TOC_ENTRY.search(t)): continue
            nt = norm(t)
            if num:
                mm = NUM_RE.match(nt)
                if not mm or mm.group(1).lower() != num: continue
                rest = nt[mm.end():].strip()
            else:
                if not nt.startswith(words[:12]): continue
                rest = nt
            if not words: sim = 1.0
            elif rest.startswith(words): sim = 1.0                       # prefix: "5.2 NUC" matches "5.2 NUC assembly"
            else: sim = difflib.SequenceMatcher(None, words, rest[:len(words) + 8]).ratio()
            if sim < 0.55: continue
            cands.append((sim + 0.1 * bool(bold), pno, y0, t))
    if not cands: raise LookupError(f"not found: {text!r}")
    cands.sort(key=lambda c: (c[1], c[2]))
    nth = anchor.get("nth")
    if nth:
        if nth > len(cands): raise LookupError(f"{text!r}: only {len(cands)} occurrence(s)")
        c = cands[nth - 1]
    else: c = max(cands, key=lambda c: c[0])
    return c[1], c[2], c[3]

def has_own_content(doc, h, nx):
    """False when heading h is followed straight away by the next item nx (6 Assembly -> 6.1 on the next line)"""
    if nx is None or nx[0] != h[0]: return True
    page = doc[h[0]]; band = fitz.Rect(0, h[1] + 4, page.rect.width, nx[1] - 1)
    if band.height <= 0: return False
    words = [w for w in page.get_text("words", clip=band) if w[1] > h[1] + 4 and w[3] < nx[1] + 1]
    pics = [r for img in page.get_images(full=True) for r in page.get_image_rects(img[0]) if r.intersects(band) and r.height > 10]
    drawn = [d for d in page.get_drawings() if d["rect"].intersects(band) and d["rect"].height > 20]
    return bool(words or pics or drawn)

def depth_of(found_text):
    m = re.match(r"^(\d+(?:\.\d+)*)", found_text.strip())
    return m.group(1).count(".") + 1 if m else 99

# ======================================================================== plans
def resolve_pdf(docs_dir, key):
    """exact path, or the PDF in docs_dir whose name contains / resembles key ("Assembly Instructions")"""
    p = key if os.path.isabs(key) else os.path.join(docs_dir, key)
    if os.path.exists(p): return p
    pdfs = sorted(f for f in os.listdir(docs_dir) if f.lower().endswith(".pdf")) if os.path.isdir(docs_dir) else []
    k = norm(os.path.basename(key)).replace(".pdf", "")
    hits = [f for f in pdfs if k in norm(f)] or sorted(pdfs, key=lambda f: difflib.SequenceMatcher(None, k, norm(f)).ratio(), reverse=True)[:1]
    if hits and (k in norm(hits[0]) or difflib.SequenceMatcher(None, k, norm(hits[0])).ratio() > 0.6): return os.path.join(docs_dir, hits[0])
    raise FileNotFoundError(f"no PDF matching {key!r} in {docs_dir}")

def text_layer_warning(doc, pmin, pmax, log):
    empty = [p + 1 for p in range(pmin, pmax) if len(doc[p].get_text().strip()) < 5]
    if empty: log(f"  ! {len(empty)} page(s) have no text layer (scan) — items there can't be found: {empty[:30]}{' …' if len(empty) > 30 else ''}")

def run_plan(plan, docs_dir, out_dir, dry=False, only=None, dpi=None, log=print):
    """plan = {"dpi", "margins_mm", "max_height_pt", "jobs": [{"pdf", "page_min", "page_max", "clips": [{"out","from","to","dpi"}]}]}
    returns (done, errors). dry = only find the anchors, write nothing."""
    pdpi = dpi or plan.get("dpi", 300); M = margins_pt(plan.get("margins_mm")); maxh = plan.get("max_height_pt")
    done, errors = 0, []
    for job in plan["jobs"]:
        try: path = resolve_pdf(docs_dir, job["pdf"])
        except FileNotFoundError as e: log(f"!! {e}"); errors.append(str(e)); continue
        doc = fitz.open(path)
        ctx = Ctx(doc, job["page_min"] - 1 if job.get("page_min") else None, job.get("page_max"))
        log(f"== {os.path.basename(path)}  ({len(doc)} pages, searching pages {ctx.pmin + 1}-{ctx.pmax})")
        text_layer_warning(doc, ctx.pmin, ctx.pmax, log)
        for c in job["clips"]:
            name = c["out"] if c["out"].lower().endswith(".png") else c["out"] + ".png"
            if only and name != only and c["out"] != only: continue
            cdpi = int(c.get("dpi") or pdpi)
            try:
                if str(c["from"]).upper() == "ALL" or (isinstance(c["from"], dict) and str(c["from"].get("text")).upper() == "ALL"):
                    s, t0 = (ctx.pmin if job.get("page_min") else 0, header_bottom(doc[ctx.pmin if job.get("page_min") else 0]) if not M else 0), "whole document"
                    e, t1 = ctx.end(), "END"
                else:
                    p0, y0, t0 = find_anchor(ctx, c["from"]); s = (p0, y0)
                    p1, y1, t1 = find_anchor(ctx, c["to"], after=s, from_depth=depth_of(t0)); e = (p1, y1)
                log(f"  {name}: p{s[0] + 1} «{t0[:55]}»  ->  p{e[0] + 1} «{t1[:55]}»")
                if not dry:
                    names = save_images(clip_images(doc, s, e, cdpi, M, maxh), os.path.join(out_dir, name))
                    for n in names:
                        w, h = Image.open(n).size; log(f"     OK {os.path.relpath(n, out_dir) if out_dir else n}  {w}x{h}px  {cdpi} dpi")
                done += 1
            except (LookupError, ValueError) as ex:
                log(f"  !! {name}: {ex}"); errors.append(f"{name}: {ex}")
        doc.close()
    log(f"Done: {done} clip(s) {'checked' if dry else 'written' + (' to ' + out_dir if out_dir else '')}, {len(errors)} problem(s).")
    return done, errors

def auto_plan(src, dmin=1, dmax=2, pages=(None, None), dpi=300, log=print):
    """plan that cuts every numbered item of levels dmin..dmax, each up to the next item (src = PDF file or folder).
    Items deeper than dmax stay inside their parent; a heading with no own content (6 -> 6.1 at once) is skipped."""
    pdfs = [src] if os.path.isfile(src) else sorted(os.path.join(src, f) for f in os.listdir(src) if f.lower().endswith(".pdf"))
    if not pdfs: raise FileNotFoundError(f"no PDF in {src}")
    plan = {"dpi": dpi, "jobs": []}
    for path in pdfs:
        doc = fitz.open(path)
        ctx = Ctx(doc, pages[0] - 1 if pages[0] else None, pages[1])
        stem = os.path.splitext(os.path.basename(path))[0]; sub = "" if len(pdfs) == 1 else re.sub(r"[^\w.-]+", "_", stem)[:60] + "/"
        bounds = [h for h in ctx.heads if h[3] <= dmax]
        items = [h for h in bounds if h[3] >= dmin]
        log(f"== {os.path.basename(path)}: {len(items)} item(s) of levels {dmin}-{dmax}")
        job = {"pdf": os.path.basename(path), "page_min": ctx.pmin + 1, "clips": []}
        if pages[1]: job["page_max"] = ctx.pmax
        used = set()
        for h in items:
            k = bounds.index(h); nx = bounds[k + 1] if k + 1 < len(bounds) else None
            if not has_own_content(doc, h, nx): log(f"  {h[4]}: heading only, its content is in {nx[4]} — skipped"); continue
            name = safe_name(h[4], h[5]); base, n = name, 2
            while name in used: name = f"{base}_{n}"; n += 1
            used.add(name)
            job["clips"].append({"out": f"{sub}{name}.png", "from": {"text": h[4], "page": h[0] + 1},
                                 "to": {"text": nx[4], "page": nx[0] + 1} if nx else "END"})
        plan["jobs"].append(job); doc.close()
    return plan

def parse_jobs(path, default_dpi=300):
    """jobs.txt -> plan.  Lines:  file.pdf | from | to | name [| dpi]   ·   dpi = N   ·   # comment"""
    plan = {"dpi": default_dpi, "jobs": []}; dpi = None; problems = []
    for ln, line in enumerate(open(path, encoding="utf-8-sig"), 1):
        line = line.strip()
        if not line or line.startswith("#"): continue
        m = re.match(r"(?i)^dpi\s*=\s*(\d+)$", line)
        if m: dpi = int(m.group(1)); continue
        p = [x.strip() for x in line.split("|")]
        if len(p) not in (4, 5): problems.append(f"line {ln}: expected 4 or 5 parts separated by | — skipped: {line}"); continue
        clip_ = {"out": p[3], "from": p[1], "to": p[2]}
        d = int(p[4]) if len(p) == 5 and p[4].isdigit() else dpi
        if d: clip_["dpi"] = d
        if not plan["jobs"] or plan["jobs"][-1]["pdf"] != p[0]: plan["jobs"].append({"pdf": p[0], "clips": []})
        plan["jobs"][-1]["clips"].append(clip_)
    return plan, problems

def parse_range(s, lo=None, hi=None):
    """"5-200" -> (5, 200), "5" -> (5, 5), "5-" -> (5, hi), "" -> (lo, hi)"""
    if not s or not str(s).strip(): return lo, hi
    a, dash, b = str(s).replace(" ", "").partition("-")
    return (int(a) if a else lo), (int(b) if b else (hi if dash else int(a)))

def save_plan(plan, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump(plan, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

if __name__ == "__main__":
    a = sys.argv[1:]
    if "--version" in a: sys.exit(f"pdfclip {__version__}")
    if len([x for x in a if not x.startswith("--")]) < 4: sys.exit(__doc__)
    def opt(k, d): return a[a.index(k) + 1] if k in a else d
    pdf, frm, to, out = [x for x in a if not x.startswith("--") and x not in (opt("--dpi", None), opt("--first-page", None))][:4]
    fp = opt("--first-page", None)
    plan = {"dpi": int(opt("--dpi", 300)), "jobs": [{"pdf": os.path.abspath(pdf), **({"page_min": int(fp)} if fp else {}),
                                                    "clips": [{"out": os.path.abspath(out), "from": frm, "to": to}]}]}
    done, errors = run_plan(plan, ".", "", dpi=None)
    sys.exit(1 if errors else 0)
