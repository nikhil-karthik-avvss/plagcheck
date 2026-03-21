# plagcheck

A command-line tool to detect plagiarism between two PDF assignments. Compares documents across four dimensions: text, code, images, and document structure — and produces a clear, colour-coded terminal report.

---

## Features

- **Text similarity** — cosine, Jaccard, bigram/trigram/4-gram Dice, and verbatim chunk overlap
- **Code similarity** — AST-based comparison that catches copied code even with renamed variables
- **Image comparison** — perceptual hashing to detect reused figures and diagrams
- **Structure analysis** — compares section headings and document layout
- **OCR fallback** — automatically runs Tesseract OCR on scanned/image-based PDFs
- **Sentence-level matching** — highlights the specific sentence pairs that are most suspicious

---

## Requirements

- Ubuntu 24.04 (or any Linux with Python 3.10+)
- Python 3 (pre-installed on Ubuntu 24.04)

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
2. Install all Python dependencies inside it
3. Attempt to install `tesseract-ocr` via apt (needed for scanned PDFs — skipped gracefully if apt has issues)
4. Register `plagcheck` as a system-wide command in `/usr/local/bin`

After installation, open a new terminal or run `source ~/.zshrc` and you're ready.

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

# Skip image comparison
plagcheck student_a.pdf student_b.pdf --no-images

# Skip sentence-level matching
plagcheck student_a.pdf student_b.pdf --no-sentences

# Raise the threshold for flagging similar sentences (default: 0.75)
plagcheck student_a.pdf student_b.pdf --sentence-threshold 0.85

# See all options
plagcheck --help
```

---

## Report Structure

### Overall Similarity Score

A weighted composite across all four dimensions, displayed as a percentage with a colour-coded verdict:

| Score  | Verdict                                     |
|--------|---------------------------------------------|
| 70–100% | 🔴 HIGH SIMILARITY — likely plagiarism     |
| 45–69%  | 🟡 MODERATE — manual review advised        |
| 20–44%  | 🔵 LOW — some shared content               |
| 0–19%   | 🟢 MINIMAL — likely original work          |

The final score is dynamically weighted based on what content is actually present. If no images are detected, image similarity does not affect the score.

### Dimension Summary

| Dimension   | What it checks                                                        |
|-------------|-----------------------------------------------------------------------|
| 📝 Text     | Overall vocabulary, phrase overlap, and verbatim passage matching     |
| 💻 Code     | Code blocks extracted and compared at the AST level                   |
| 🖼 Images   | Embedded figures matched using perceptual hashing                     |
| 🏗 Structure | Section headings compared for layout and naming similarity           |

### Text Metric Breakdown

| Metric              | What it measures                                        |
|---------------------|---------------------------------------------------------|
| Cosine Similarity   | Overall vocabulary distribution (TF-weighted)           |
| Jaccard Index       | Fraction of shared unique words                         |
| Bigram Dice         | Shared 2-word phrases                                   |
| Trigram Dice        | Shared 3-word phrases (strong plagiarism signal)        |
| 4-gram Dice         | Shared 4-word sequences including stopwords             |
| Chunk LCS           | Verbatim passage overlap — catches direct copy-paste    |

### Code Analysis

Extracts fenced code blocks (` ```python `, ` ```js `, etc.) from both documents, parses them into an Abstract Syntax Tree, and normalises away variable names before comparing. Two code blocks that are functionally identical but use different variable names will still be flagged.

### Image Analysis

Extracts embedded raster images from both PDFs and computes a perceptual hash for each. Images that are visually similar — even if slightly resized or re-saved — are counted as matches. Reports the number of matching image pairs and an overall visual similarity score.

### Structure Analysis

Detects headings using numbered patterns (`1. Introduction`), ALL CAPS lines, and Markdown-style headers (`## Heading`). Compares the heading sets between both documents and lists matching pairs.

### Matching Sentence Pairs

Lists up to 15 sentence pairs that exceed the similarity threshold, showing the exact text from each document side by side so you can pinpoint where copying occurred.

---

## Limitations

- **Scanned PDFs without OCR installed** — if `tesseract-ocr` could not be installed, scanned PDFs will show very low scores. Install it manually with `sudo apt install tesseract-ocr` once your apt issues are resolved.
- **Paraphrasing** — heavy paraphrasing can lower text scores even when ideas are copied. Trigram and 4-gram metrics are the most resistant to this.
- **Non-Python code** — AST parsing works best for Python. Other languages fall back to token-level comparison, which is still effective but cannot normalise variable names.
- **Vector graphics** — charts drawn as vectors (e.g. from matplotlib exports) are not raster images and will not be picked up by image comparison. Text in those charts will still be captured by text extraction.
- **Two-file comparison only** — this tool compares exactly two PDFs. It does not check against a database or corpus.

---

## Uninstalling

```bash
./uninstall.sh
```

This removes the `plagcheck` command from `/usr/local/bin` and deletes the virtual environment at `~/.plagcheck-venv`.
