"""make_sample.py — builds sample.pdf: a fake 9-page procedure for trying PDF Clipper.
It has what real documents have: a table of contents, a page header (with a rule) and footer, numbered items
6.1 / 6.2 / 6.2.1, a bare number without a title, and measured values like "6.3 V" that must NOT be taken as headings.
  py make_sample.py      (needs only pymupdf)"""
import os
import pymupdf as fitz

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample.pdf")
LOREM = ("Make sure the unit is switched off and the work area is clean before you start. "
         "Check every connector visually and follow the torque values given in the table. ")

def header_footer(page, n, total):
    page.insert_text((40, 40), "SAMPLE PROCEDURE  |  Revision: 01  |  Reference: DOC-0001", fontsize=9)
    page.draw_line((36, 52), (page.rect.width - 36, 52), width=0.8)
    page.insert_text((40, page.rect.height - 30), f"Sample Company Ltd. — Confidential        Page {n} of {total}", fontsize=8)

def build():
    doc = fitz.open(); total = 9
    for _ in range(total): doc.new_page()
    pages = [doc[i] for i in range(total)]
    for i, p in enumerate(pages): header_footer(p, i + 1, total)
    # page 1: title, page 2: table of contents
    pages[0].insert_text((60, 300), "Sample Assembly Procedure", fontsize=24)
    toc = ["Table of contents", "5  General ........................ 4", "6  Assembly ....................... 5",
           "6.1  Preparation ................... 5", "6.2  Chassis ....................... 6", "7  Final test ..................... 9"]
    for k, t in enumerate(toc): pages[1].insert_text((60, 120 + 22 * k), t, fontsize=12)
    for k, t in enumerate(["Revision history", "01   First issue", "02   Figures updated"]): pages[2].insert_text((60, 120 + 22 * k), t, fontsize=12)
    y = {}
    def text(pno, s, size=11, bold=False, x=60):
        yy = y.get(pno, 90); pages[pno].insert_text((x, yy), s, fontsize=size, fontname="hebo" if bold else "helv")
        y[pno] = yy + size * 1.9
    def para(pno, n=3):
        for _ in range(n):
            pages[pno].insert_textbox(fitz.Rect(60, y.get(pno, 90) - 10, 540, y.get(pno, 90) + 40), LOREM, fontsize=10)
            y[pno] = y.get(pno, 90) + 52
    text(3, "5  General", 14, True); para(3, 4)
    text(4, "6  Assembly", 14, True); text(4, "6.1  Preparation", 12, True); para(4, 3)
    text(4, "6.1.1  Tools"); para(4, 2)
    text(5, "6.2  Chassis", 12, True); para(5, 2)
    text(5, "Supply voltage:"); text(5, "6.3 V", x=200)          # measured value, NOT a heading
    text(5, "6.2.1  Mount the base plate"); para(5, 2)
    text(6, "6.2.2"); para(6, 2)                                # bare number, no title text
    pages[6].draw_rect(fitz.Rect(60, y[6], 540, y[6] + 160), color=(0, 0, 0), fill=(0.9, 0.95, 1))
    pages[6].insert_text((240, y[6] + 85), "[ figure ]", fontsize=14); y[6] += 180
    text(7, "6.3  Cover", 12, True); para(7, 3)
    text(7, "Torque:"); text(7, "4.7", x=200)                       # table cell, NOT a heading
    text(8, "7  Final test", 14, True); para(8, 3)
    doc.save(OUT); print("written", OUT)

if __name__ == "__main__":
    build()
