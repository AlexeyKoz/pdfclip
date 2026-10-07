# Changelog

## [1.1.0] — 2026-10-07

Manual clipping, automatic clipping and plans are now one program.

### Added
- **Auto tab** / `clip_batch.py --auto`: every numbered item of one PDF or a whole folder of PDFs becomes its own
  image (levels and page range selectable); the result can be saved as `plan_auto.json`.
- **Plan tab** / `clip_batch.py plan.json`: JSON plans with `from` / `to` anchors, `NEXT`, `END`, `ALL`,
  `{"text", "page", "nth"}`, per-clip dpi, `page_min` / `page_max`, image names with subfolders.
- **Save queue as plan…** in the Manual tab.
- **Fuzzy anchors**: number + title matched despite other dashes, spacing, a typo or a title broken over two lines;
  PDFs in plans found by part of the file name.
- **Check (dry run)** in the window and `--dry` on the command line.
- **Splitting** of very long images into `name-1.png`, `name-2.png` … (`max_height_pt`, *Split images taller than*).
- **Fixed margins** in mm (`margins_mm`) as an alternative to automatic header/footer detection.
- Shared output folder, quality and split settings for all tabs; the window remembers folders and settings.
- `examples/sample_plan.json`; Russian and Hebrew table-of-contents titles recognised.

### Fixed
- Numbered list steps with a capital letter (`7. DSP step …`) were listed as top-level headings: top-level items now
  have to be bold or larger than the body text.
- *Add all items* / Auto no longer produce images that contain only a heading (`6 Assembly` directly followed by `6.1`).

### Changed
- `jobs.txt` runs through the same engine as plans; the old format still works, `NEXT` is new.
- `clip_pdf.py` on the command line takes the same anchors (`6.2`, `NEXT`, …); regular expressions still work when
  they start with `^` or `(?`.

## [1.0.0] — 2026-10-07

First public release.

- **GUI** (`clip_gui.py`): open a PDF, pick *From item* / *To item* from the detected headings, queue several cuts, run.
  - *Add all items*: queue every section up to a chosen depth (1 = `6`, 2 = `6.2`, 3 = `6.2.1`) in one click.
  - *To item* is filled automatically with the next item of the same or higher level.
  - *Whole document* mode for PDFs without numbered headings.
  - Image quality presets 150–1200 dpi, or any number typed in.
- **Batch mode** (`clip_batch.py` + `jobs.txt`): one job per line, `dpi = N` lines, optional per-job dpi,
  `ALL` / `END` anchors, bare section numbers (`6.2.1`) as anchors, `--jobs` to use another job file.
- **Engine** (`clip_pdf.py`), also usable from the command line with regex headings.
  - Heading detection on every text line, including numbers without title text.
  - Numbering-sequence check filters out measured values (`6.3 V`) and stray table numbers.
  - Table-of-contents pages and entries are skipped.
  - Page headers/footers, blank page tails, grey side bands and Word comment margins are removed.
- `--version` flag for all three scripts; `examples/sample.pdf` to try everything without your own documents.
