#!/usr/bin/env python3
"""
Assignment Plagiarism Checker
Compares two PDF assignments and reports similarity using multiple methods.
"""

import sys
import os
import re
import math
import argparse
from collections import Counter

# ── Text extraction ────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF using pdfplumber (preferred) or pypdf as fallback."""
    if not os.path.isfile(pdf_path):
        print(f"[ERROR] File not found: {pdf_path}")
        sys.exit(1)

    # Try pdfplumber first
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        text = "\n".join(text_parts).strip()
        if text:
            return text
    except ImportError:
        pass
    except Exception as e:
        print(f"[WARN] pdfplumber failed on {pdf_path}: {e}")

    # Fallback: pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text_parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
        text = "\n".join(text_parts).strip()
        if text:
            return text
    except ImportError:
        pass
    except Exception as e:
        print(f"[WARN] pypdf failed on {pdf_path}: {e}")

    print(f"[ERROR] Could not extract text from {pdf_path}.\n"
          "Install dependencies:  pip install pdfplumber pypdf")
    sys.exit(1)


# ── Preprocessing ──────────────────────────────────────────────────────────────

STOPWORDS = {
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","are","was","were","be","been","being","have","has",
    "had","do","does","did","will","would","could","should","may","might",
    "shall","can","need","dare","ought","used","it","its","this","that",
    "these","those","i","we","you","he","she","they","me","us","him","her",
    "them","my","our","your","his","our","their","which","who","whom","what",
    "when","where","why","how","all","each","every","both","few","more",
    "most","other","some","such","no","nor","not","only","own","same","so",
    "than","too","very","just","as","if","into","through","during","before",
    "after","above","below","between","up","down","out","off","over","under",
    "again","then","once","here","there","about","against","during","without",
}

def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def tokenize(text: str, remove_stopwords: bool = True) -> list[str]:
    words = normalize(text).split()
    if remove_stopwords:
        words = [w for w in words if w not in STOPWORDS and len(w) > 2]
    return words

def get_ngrams(tokens: list[str], n: int) -> list[tuple]:
    return [tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1)]


# ── Similarity Metrics ─────────────────────────────────────────────────────────

def cosine_similarity(tokens1: list[str], tokens2: list[str]) -> float:
    """TF-based cosine similarity."""
    c1, c2 = Counter(tokens1), Counter(tokens2)
    vocab = set(c1) | set(c2)
    if not vocab:
        return 0.0
    dot = sum(c1[w] * c2[w] for w in vocab)
    mag1 = math.sqrt(sum(v**2 for v in c1.values()))
    mag2 = math.sqrt(sum(v**2 for v in c2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)

def jaccard_similarity(set1: set, set2: set) -> float:
    """Jaccard index on token sets."""
    if not set1 and not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2)

def ngram_overlap(tokens1: list[str], tokens2: list[str], n: int = 3) -> float:
    """Dice coefficient over n-gram multisets."""
    ng1 = Counter(get_ngrams(tokens1, n))
    ng2 = Counter(get_ngrams(tokens2, n))
    shared = sum((ng1 & ng2).values())
    total = sum(ng1.values()) + sum(ng2.values())
    if total == 0:
        return 0.0
    return 2 * shared / total

def longest_common_substring_ratio(t1: str, t2: str, chunk: int = 200) -> float:
    """
    Approximate LCS by splitting normalized text into fixed-length char chunks
    and measuring overlap. Fast enough for typical assignment lengths.
    """
    def chunks(s, size):
        return {s[i:i+size] for i in range(0, len(s)-size+1, size//2)}

    c1 = chunks(t1, chunk)
    c2 = chunks(t2, chunk)
    if not c1 and not c2:
        return 0.0
    return len(c1 & c2) / max(len(c1), len(c2))

def plagiarism_score(text1: str, text2: str) -> dict:
    """Run all metrics and return a dict of scores (0–1)."""
    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)
    raw1    = tokenize(text1, remove_stopwords=False)
    raw2    = tokenize(text2, remove_stopwords=False)
    norm1   = normalize(text1)
    norm2   = normalize(text2)

    scores = {
        "cosine":        cosine_similarity(tokens1, tokens2),
        "jaccard":       jaccard_similarity(set(tokens1), set(tokens2)),
        "bigram_dice":   ngram_overlap(tokens1, tokens2, n=2),
        "trigram_dice":  ngram_overlap(tokens1, tokens2, n=3),
        "fourgram_dice": ngram_overlap(raw1,    raw2,    n=4),
        "lcs_chunk":     longest_common_substring_ratio(norm1, norm2),
    }

    # Weighted composite
    weights = {
        "cosine":        0.20,
        "jaccard":       0.10,
        "bigram_dice":   0.15,
        "trigram_dice":  0.25,
        "fourgram_dice": 0.20,
        "lcs_chunk":     0.10,
    }
    scores["composite"] = sum(scores[k] * weights[k] for k in weights)
    return scores


# ── Suspicious sentence detection ─────────────────────────────────────────────

def find_matching_sentences(text1: str, text2: str,
                             min_words: int = 8,
                             threshold: float = 0.75) -> list[tuple[str, str, float]]:
    """
    Find sentence pairs that are highly similar.
    Returns list of (sent1, sent2, jaccard_score).
    """
    def split_sentences(text):
        # Split on . ! ? followed by whitespace/end
        parts = re.split(r'(?<=[.!?])\s+', text.strip())
        return [p.strip() for p in parts if len(p.split()) >= min_words]

    sents1 = split_sentences(text1)
    sents2 = split_sentences(text2)

    matches = []
    for s1 in sents1:
        tok1 = set(tokenize(s1))
        for s2 in sents2:
            tok2 = set(tokenize(s2))
            j = jaccard_similarity(tok1, tok2)
            if j >= threshold:
                matches.append((s1, s2, j))

    # Sort by similarity desc, deduplicate by s1
    matches.sort(key=lambda x: -x[2])
    seen = set()
    unique = []
    for m in matches:
        if m[0] not in seen:
            seen.add(m[0])
            unique.append(m)
    return unique[:15]  # top 15


# ── Result rendering ───────────────────────────────────────────────────────────

COLORS = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "red":    "\033[91m",
    "yellow": "\033[93m",
    "green":  "\033[92m",
    "cyan":   "\033[96m",
    "dim":    "\033[2m",
}

def c(color: str, text: str) -> str:
    return f"{COLORS.get(color,'')}{text}{COLORS['reset']}"

def verdict(score: float) -> tuple[str, str]:
    """Return (label, color) based on composite score."""
    if score >= 0.70:
        return "HIGH SIMILARITY — likely plagiarism", "red"
    elif score >= 0.45:
        return "MODERATE SIMILARITY — manual review advised", "yellow"
    elif score >= 0.20:
        return "LOW SIMILARITY — some shared content", "cyan"
    else:
        return "MINIMAL SIMILARITY — likely original work", "green"

def bar(value: float, width: int = 40) -> str:
    filled = int(round(value * width))
    empty  = width - filled
    col = "red" if value >= 0.7 else "yellow" if value >= 0.45 else "green"
    return c(col, "█" * filled) + c("dim", "░" * empty)

def print_report(path1: str, path2: str,
                 scores: dict,
                 matches: list[tuple[str, str, float]],
                 word_counts: tuple[int, int]) -> None:

    w = 65
    print()
    print(c("bold", "=" * w))
    print(c("bold", "       ASSIGNMENT PLAGIARISM CHECKER — REPORT"))
    print(c("bold", "=" * w))
    print(f"  File 1 : {os.path.basename(path1)}  ({word_counts[0]:,} words)")
    print(f"  File 2 : {os.path.basename(path2)}  ({word_counts[1]:,} words)")
    print()

    # ── Composite score ───────────────────────────────────────────────────────
    comp = scores["composite"]
    label, col = verdict(comp)
    print(c("bold", "  OVERALL SIMILARITY SCORE"))
    pct = comp * 100
    print(f"  {bar(comp)}  {c(col, f'{pct:.1f}%')}")
    print(f"\n  Verdict: {c(col, c('bold', label))}")
    print()

    # ── Per-metric breakdown ──────────────────────────────────────────────────
    print(c("bold", "  METRIC BREAKDOWN"))
    print(c("dim",  "  " + "-" * (w-2)))
    metric_labels = {
        "cosine":        "Cosine Similarity (TF-weighted)",
        "jaccard":       "Jaccard Index (vocabulary overlap)",
        "bigram_dice":   "Bigram Dice (2-word phrases)",
        "trigram_dice":  "Trigram Dice (3-word phrases)",
        "fourgram_dice": "4-gram Dice (4-word phrases, incl. stopwords)",
        "lcs_chunk":     "Chunk LCS (verbatim passage overlap)",
    }
    for key, label in metric_labels.items():
        v = scores[key]
        print(f"  {label:<44}  {bar(v, 20)}  {v*100:5.1f}%")
    print()

    # ── Suspicious sentences ──────────────────────────────────────────────────
    if matches:
        print(c("bold", "  HIGHLY SIMILAR SENTENCE PAIRS"))
        print(c("dim",  "  " + "-" * (w-2)))
        for i, (s1, s2, score) in enumerate(matches, 1):
            col2 = "red" if score >= 0.9 else "yellow"
            print(f"\n  {c('bold', f'[{i}]')}  Similarity: {c(col2, f'{score*100:.0f}%')}")
            # Wrap long sentences
            print(f"  {c('dim','  Doc1:')} {s1[:200]}{'…' if len(s1)>200 else ''}")
            print(f"  {c('dim','  Doc2:')} {s2[:200]}{'…' if len(s2)>200 else ''}")
    else:
        print(c("green", "  No highly similar individual sentences found."))

    print()
    print(c("bold", "=" * w))
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Compare two assignment PDFs for plagiarism.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 plagiarism_checker.py essay1.pdf essay2.pdf
  python3 plagiarism_checker.py essay1.pdf essay2.pdf --no-sentences
  python3 plagiarism_checker.py essay1.pdf essay2.pdf --sentence-threshold 0.85
        """,
    )
    parser.add_argument("pdf1", help="Path to the first PDF")
    parser.add_argument("pdf2", help="Path to the second PDF")
    parser.add_argument(
        "--no-sentences", action="store_true",
        help="Skip sentence-level matching (faster for large PDFs)"
    )
    parser.add_argument(
        "--sentence-threshold", type=float, default=0.75, metavar="T",
        help="Jaccard threshold for flagging sentence pairs (default: 0.75)"
    )
    args = parser.parse_args()

    print(c("cyan", "\n  Extracting text from PDFs…"))
    text1 = extract_text_from_pdf(args.pdf1)
    text2 = extract_text_from_pdf(args.pdf2)

    wc1 = len(text1.split())
    wc2 = len(text2.split())
    print(f"  → Doc 1: {wc1:,} words extracted")
    print(f"  → Doc 2: {wc2:,} words extracted")

    if wc1 < 20 or wc2 < 20:
        print(c("yellow", "\n  [WARN] Very little text extracted. "
                "The PDF may be scanned/image-based — OCR not supported here."))

    print(c("cyan", "\n  Computing similarity scores…"))
    scores = plagiarism_score(text1, text2)

    matches = []
    if not args.no_sentences:
        print(c("cyan", "  Scanning for matching sentences…"))
        matches = find_matching_sentences(
            text1, text2,
            threshold=args.sentence_threshold
        )

    print_report(args.pdf1, args.pdf2, scores, matches, (wc1, wc2))


if __name__ == "__main__":
    main()
