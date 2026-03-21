# Assignment Plagiarism Checker

Compares two PDF assignments and reports how similar they are using multiple
NLP metrics. Runs fully offline — no internet, no API keys.

---

## Requirements

- Ubuntu 24.04 (or any Linux with Python 3.10+)
- Python 3 (already included in Ubuntu 24.04)

---

## Setup (one-time)

```bash
# 1. Install system PDF tools (needed for some fallback operations)
sudo apt update && sudo apt install -y poppler-utils

# 2. Install Python dependencies
pip3 install pdfplumber pypdf
```

---

## Usage

```bash
python3 plagiarism_checker.py <pdf1> <pdf2>
```

### Examples

```bash
# Basic comparison
python3 plagiarism_checker.py student_a.pdf student_b.pdf

# Skip sentence-level matching (faster for very large PDFs)
python3 plagiarism_checker.py student_a.pdf student_b.pdf --no-sentences

# Raise the bar for flagging sentences (default is 0.75)
python3 plagiarism_checker.py student_a.pdf student_b.pdf --sentence-threshold 0.85
```

---

## What the report shows

### Overall Similarity Score (0–100%)

| Range   | Verdict                                      |
|---------|----------------------------------------------|
| 70–100% | 🔴 HIGH SIMILARITY — likely plagiarism       |
| 45–69%  | 🟡 MODERATE — manual review advised          |
| 20–44%  | 🔵 LOW — some shared content                 |
| 0–19%   | 🟢 MINIMAL — likely original work            |

### Metric Breakdown

| Metric              | What it measures                                     |
|---------------------|------------------------------------------------------|
| Cosine Similarity   | Overall vocabulary distribution (TF-weighted)        |
| Jaccard Index       | Fraction of shared unique words                      |
| Bigram Dice         | Shared 2-word phrases                                |
| Trigram Dice        | Shared 3-word phrases (key plagiarism signal)        |
| 4-gram Dice         | Shared 4-word phrases including stopwords            |
| Chunk LCS           | Verbatim passage overlap (copy-paste detector)       |

### Matching Sentences

The tool also highlights specific sentence pairs that are suspiciously
similar, making it easy to locate the plagiarised sections.

---

## Limitations

- **Scanned PDFs** (image-only) will show very low scores because no text
  can be extracted. If you suspect a scanned PDF, use OCR tools like
  `ocrmypdf` first:  `ocrmypdf input.pdf output.pdf`
- **Paraphrasing** may lower scores even when ideas are copied. The
  trigram/4-gram metrics are best at catching this.
- Does **not** compare against a database — only compares the two files
  you provide.
