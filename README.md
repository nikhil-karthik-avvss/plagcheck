# plagcheck

A command-line tool to detect plagiarism between two PDF assignments. Compares documents across four dimensions — text, code, visuals, and structure — and produces a clear, colour-coded terminal report.

Works with PDFs from any source: Microsoft Word, LibreOffice, LaTeX, scanners, online tools, or anything else.

---

## Features

- **Text similarity** — cosine, Jaccard, bigram/trigram/4-gram Dice, and verbatim chunk overlap
- **Code similarity** — AST-based comparison that catches copied code even with renamed variables; heuristic detection works on PDFs from any source (no markdown fences required)
- **Visual comparison** — two-level perceptual hashing catches both copied pages and copied figures/diagrams embedded in otherwise different pages
- **Structure analysis** — compares section headings and document layout
- **OCR** — powered by [easyocr](https://github.com/JaidedAI/EasyOCR), a fully pip-installable OCR engine; no system-level Tesseract binary required. Runs alongside text extraction to also catch text hidden inside figures and diagrams
- **Sentence-level matching** — highlights specific sentence pairs that are most suspicious

---

## Requirements

- Ubuntu 24.04 (or any Linux with Python 3.10+)
- Python 3 (pre-installed on Ubuntu 24.04)
- No system-level dependencies — everything installs via pip

---

## Installation

Clone the repo and run the installer:

```bash
git clone https://github.com/nikhil-karthik-avvss/plagcheck.git
cd plagcheck
chmod +x install.sh
./install.sh
```

The installer will:
1. Create a dedicated Python virtual environment at `~/.plagcheck-venv`
2. Install all dependencies inside it (no `sudo apt` or system packages needed)
3. Register `plagcheck` as a system-wide command in `/usr/local/bin`

After installation, open a new terminal or run `source ~/.zshrc`.

> **Note:** On first run, easyocr will download its model weights (~100 MB). This only happens once and is cached automatically.

---

## Usage

```bash
plagcheck <pdf1> <pdf2> [options]
```

### Examples

```bash
# Basic comparison
plagcheck student_a.pdf student_b.pdf

# Skip OCR (faster, for text-based PDFs only)
plagcheck student_a.pdf student_b.pdf --no-ocr

# Skip visual comparison
plagcheck student_a.pdf student_b.pdf --no-visuals

# Skip sentence-level matching
plagcheck student_a.pdf student_b.pdf --no-sentences

# Raise the threshold for flagging similar sentences (default: 0.75)
plagcheck student_a.pdf student_b.pdf --sentence-threshold 0.85

# See all options
plagcheck --help
```

---

## How it works

### Text extraction pipeline (per document)

All three stages run. Their outputs are merged:

1. **pdfplumber** — extracts embedded text from digitally created PDFs (Word, LibreOffice, LaTeX). Best quality.
2. **PyMuPDF** — fast fallback for digitally created PDFs.
3. **easyocr** — rasterizes every page and runs OCR. Catches text in scanned documents, image-only PDFs, and text embedded inside figures and diagrams that the other two stages miss.

The merge step adds OCR lines that are not already present in the digital text (< 40% token overlap), so you always get the union of both.

### Visual comparison (two levels)

**Level A — Full-page perceptual hash:** Detects entirely copied or near-identical pages.

**Level B — Sliding-window tile hash:** Splits each page into overlapping 64×64 pixel tiles and hashes each one. A matching tile pair means a copied figure or diagram exists on those two pages, even when the surrounding content is completely different. This catches circuit diagrams, connection diagrams, charts, and any other copied visual.

### Code detection

Code segments are detected in two ways:
- Fenced code blocks (` ```python `, ` ```c `, etc.)
- Heuristic detection of consecutive lines containing C/C++/Arduino/Java/Python syntax patterns (braces, semicolons, keywords, operators)

This works on PDFs from Word, LaTeX, LibreOffice, and any other source — no special formatting required.

Once detected, Python code is parsed into an Abstract Syntax Tree and all variable/function names are normalised before comparison. Two code blocks that are functionally identical but use different names will still be flagged. Non-Python code falls back to token-level n-gram comparison.

---

## Report structure

### Overall Similarity Score

| Score   | Verdict                                     |
|---------|---------------------------------------------|
| 70–100% | 🔴 HIGH SIMILARITY — likely plagiarism     |
| 45–69%  | 🟡 MODERATE — manual review advised        |
| 20–44%  | 🔵 LOW — some shared content               |
| 0–19%   | 🟢 MINIMAL — likely original work          |

The final score is a weighted composite across all four dimensions. Weights shift dynamically based on what content is actually present (e.g. if no code is detected, code similarity does not affect the score).

### Dimension Summary

| Dimension    | What it checks                                                          |
|--------------|-------------------------------------------------------------------------|
| 📝 Text      | Overall vocabulary, phrase overlap, and verbatim passage matching       |
| 💻 Code      | Code segments compared at AST level                                     |
| 🖼 Visuals   | Full pages and individual figure tiles compared via perceptual hashing  |
| 🏗 Structure | Section headings compared for layout and naming similarity              |

---

## Limitations

- **Heavy paraphrasing** — Trigram and 4-gram metrics are the most resistant, but significant rewording can lower text scores even when ideas are copied.
- **Full-page visual comparison** — tile matching detects copied figures, but very small or low-contrast figures may fall below the hash threshold.
- **Non-Python code** — AST normalisation works for Python only. Other languages use token n-gram comparison, which is effective but cannot rename variables.
- **Two-file comparison only** — compares exactly two PDFs. Does not check against a database or corpus.

---

## Uninstalling

```bash
./uninstall.sh
```

Removes the `plagcheck` command and the virtual environment at `~/.plagcheck-venv`.
