#!/usr/bin/env python3
"""
Assignment Plagiarism Checker
Compares two PDF assignments across text, code, images, and structure.
"""

import sys
import os
import re
import ast
import math
import hashlib
import argparse
import tempfile
import subprocess
from collections import Counter

# ══════════════════════════════════════════════════════════════════════════════
# PDF TEXT EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_text_from_pdf(pdf_path: str) -> str:
    if not os.path.isfile(pdf_path):
        print(f"[ERROR] File not found: {pdf_path}")
        sys.exit(1)
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
        text = "\n".join(parts).strip()
        if text:
            return text
    except Exception:
        pass
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        text = "\n".join(parts).strip()
        if text:
            return text
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# OCR (SCANNED PDF SUPPORT)
# ══════════════════════════════════════════════════════════════════════════════

def ocr_pdf(pdf_path: str) -> str:
    """Rasterize each page and run Tesseract OCR on it."""
    try:
        import fitz          # PyMuPDF
        import pytesseract
        from PIL import Image
        import numpy as np
    except ImportError as e:
        print(f"  [WARN] OCR skipped — missing library: {e}")
        return ""

    text_parts = []
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            mat = fitz.Matrix(2.0, 2.0)   # 2× zoom ≈ 144 DPI — good for OCR
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            img = Image.fromarray(img_array)
            t = pytesseract.image_to_string(img, config="--psm 6")
            if t.strip():
                text_parts.append(t)
        doc.close()
    except Exception as e:
        print(f"  [WARN] OCR error: {e}")
    return "\n".join(text_parts).strip()


def get_text(pdf_path: str, use_ocr: bool) -> tuple[str, bool]:
    """
    Returns (text, used_ocr).
    Falls back to OCR automatically if text extraction yields < 50 words.
    """
    text = extract_text_from_pdf(pdf_path)
    used_ocr = False
    if len(text.split()) < 50 and use_ocr:
        print(f"  [OCR] Low text yield from {os.path.basename(pdf_path)} — trying OCR…")
        ocr_text = ocr_pdf(pdf_path)
        if len(ocr_text.split()) > len(text.split()):
            text = ocr_text
            used_ocr = True
    return text, used_ocr


# ══════════════════════════════════════════════════════════════════════════════
# TEXT PREPROCESSING
# ══════════════════════════════════════════════════════════════════════════════

STOPWORDS = {
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","are","was","were","be","been","being","have","has",
    "had","do","does","did","will","would","could","should","may","might",
    "shall","can","need","dare","ought","used","it","its","this","that",
    "these","those","i","we","you","he","she","they","me","us","him","her",
    "them","my","our","your","his","their","which","who","whom","what",
    "when","where","why","how","all","each","every","both","few","more",
    "most","other","some","such","no","nor","not","only","own","same","so",
    "than","too","very","just","as","if","into","through","during","before",
    "after","above","below","between","up","down","out","off","over","under",
    "again","then","once","here","there","about","against","without",
}

def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def tokenize(text: str, remove_stopwords: bool = True) -> list[str]:
    words = normalize(text).split()
    if remove_stopwords:
        words = [w for w in words if w not in STOPWORDS and len(w) > 2]
    return words

def get_ngrams(tokens: list[str], n: int) -> list[tuple]:
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]


# ══════════════════════════════════════════════════════════════════════════════
# TEXT SIMILARITY METRICS
# ══════════════════════════════════════════════════════════════════════════════

def cosine_similarity(t1: list[str], t2: list[str]) -> float:
    c1, c2 = Counter(t1), Counter(t2)
    vocab = set(c1) | set(c2)
    if not vocab:
        return 0.0
    dot  = sum(c1[w] * c2[w] for w in vocab)
    mag1 = math.sqrt(sum(v**2 for v in c1.values()))
    mag2 = math.sqrt(sum(v**2 for v in c2.values()))
    return dot / (mag1 * mag2) if mag1 and mag2 else 0.0

def jaccard_similarity(s1: set, s2: set) -> float:
    if not s1 and not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)

def ngram_overlap(t1: list[str], t2: list[str], n: int = 3) -> float:
    ng1 = Counter(get_ngrams(t1, n))
    ng2 = Counter(get_ngrams(t2, n))
    shared = sum((ng1 & ng2).values())
    total  = sum(ng1.values()) + sum(ng2.values())
    return 2 * shared / total if total else 0.0

def lcs_chunk_ratio(t1: str, t2: str, chunk: int = 200) -> float:
    def chunks(s, size):
        return {s[i:i+size] for i in range(0, len(s)-size+1, size//2)}
    c1, c2 = chunks(t1, chunk), chunks(t2, chunk)
    if not c1 and not c2:
        return 0.0
    return len(c1 & c2) / max(len(c1), len(c2))

def text_similarity(text1: str, text2: str) -> dict:
    tok1  = tokenize(text1)
    tok2  = tokenize(text2)
    raw1  = tokenize(text1, remove_stopwords=False)
    raw2  = tokenize(text2, remove_stopwords=False)
    norm1 = normalize(text1)
    norm2 = normalize(text2)

    scores = {
        "cosine":        cosine_similarity(tok1, tok2),
        "jaccard":       jaccard_similarity(set(tok1), set(tok2)),
        "bigram_dice":   ngram_overlap(tok1, tok2, n=2),
        "trigram_dice":  ngram_overlap(tok1, tok2, n=3),
        "fourgram_dice": ngram_overlap(raw1, raw2, n=4),
        "lcs_chunk":     lcs_chunk_ratio(norm1, norm2),
    }
    weights = {"cosine":0.20,"jaccard":0.10,"bigram_dice":0.15,
               "trigram_dice":0.25,"fourgram_dice":0.20,"lcs_chunk":0.10}
    scores["composite"] = sum(scores[k] * weights[k] for k in weights)
    return scores


# ══════════════════════════════════════════════════════════════════════════════
# CODE SIMILARITY (AST-BASED)
# ══════════════════════════════════════════════════════════════════════════════

CODE_FENCE_RE = re.compile(
    r"```(?:python|py|java|javascript|js|c|cpp|c\+\+|go|rust|ts|typescript)?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)

INLINE_CODE_RE = re.compile(r"`([^`\n]{10,})`")

def extract_code_blocks(text: str) -> list[str]:
    blocks = CODE_FENCE_RE.findall(text)
    if not blocks:
        blocks = INLINE_CODE_RE.findall(text)
    return [b.strip() for b in blocks if b.strip()]

class ASTNormalizer(ast.NodeVisitor):
    """Walk a Python AST and emit a canonical token sequence."""
    def __init__(self):
        self.tokens: list[str] = []
        self._var_map: dict[str, str] = {}
        self._counter = 0

    def _var(self, name: str) -> str:
        if name not in self._var_map:
            self._var_map[name] = f"VAR{self._counter}"
            self._counter += 1
        return self._var_map[name]

    def generic_visit(self, node):
        self.tokens.append(type(node).__name__)
        super().generic_visit(node)

    def visit_Name(self, node):
        self.tokens.append(self._var(node.id))

    def visit_FunctionDef(self, node):
        self.tokens.append("FunctionDef")
        self.tokens.append(self._var(node.name))
        self.generic_visit(node)

    def visit_arg(self, node):
        self.tokens.append(self._var(node.arg))

    def visit_Constant(self, node):
        # Collapse all literals to their type
        self.tokens.append(f"CONST_{type(node.value).__name__}")

def ast_tokens(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
        v = ASTNormalizer()
        v.visit(tree)
        return v.tokens
    except SyntaxError:
        # Not valid Python — fall back to token-level comparison
        return re.findall(r"[A-Za-z_]\w*|[+\-*/=<>!&|^~]+|[(){}\[\],.;:]", code)

def code_block_similarity(blocks1: list[str], blocks2: list[str]) -> float:
    """
    Compare all pairs of code blocks and return the mean best-match score.
    Uses AST token n-gram overlap for Python; raw token overlap otherwise.
    """
    if not blocks1 or not blocks2:
        return 0.0

    def block_score(b1: str, b2: str) -> float:
        t1 = ast_tokens(b1)
        t2 = ast_tokens(b2)
        return ngram_overlap(t1, t2, n=3)

    # For each block in doc1, find its best match in doc2
    scores = []
    for b1 in blocks1:
        best = max(block_score(b1, b2) for b2 in blocks2)
        scores.append(best)
    # Symmetric: also check from doc2's perspective
    for b2 in blocks2:
        best = max(block_score(b2, b1) for b1 in blocks1)
        scores.append(best)

    return sum(scores) / len(scores) if scores else 0.0


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE SIMILARITY
# ══════════════════════════════════════════════════════════════════════════════

def extract_images_from_pdf(pdf_path: str) -> list:
    """Return list of PIL Images extracted from the PDF."""
    images = []
    try:
        import fitz
        from PIL import Image
        import numpy as np
        doc = fitz.open(pdf_path)
        for page in doc:
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                base = doc.extract_image(xref)
                img_bytes = base["image"]
                import io
                img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                # Skip tiny images (icons, decorations)
                if img.width >= 80 and img.height >= 80:
                    images.append(img)
        doc.close()
    except Exception:
        pass
    return images

def image_hash(img, size: int = 16) -> str:
    """Perceptual hash (average hash) of an image."""
    try:
        from PIL import Image, ImageFilter
        img = img.resize((size, size)).convert("L")
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p >= avg else "0" for p in pixels)
        return bits
    except Exception:
        return ""

def hamming_distance(h1: str, h2: str) -> int:
    return sum(b1 != b2 for b1, b2 in zip(h1, h2))

def image_similarity(imgs1: list, imgs2: list) -> tuple[float, int]:
    """
    Returns (similarity_score 0-1, number_of_matching_pairs).
    Two images match if their perceptual hash distance < threshold.
    """
    if not imgs1 or not imgs2:
        return 0.0, 0

    HASH_SIZE   = 16
    THRESHOLD   = int(HASH_SIZE * HASH_SIZE * 0.15)  # 15% bit difference allowed

    hashes1 = [image_hash(img, HASH_SIZE) for img in imgs1]
    hashes2 = [image_hash(img, HASH_SIZE) for img in imgs2]

    matched1 = set()
    matched2 = set()
    for i, h1 in enumerate(hashes1):
        if not h1:
            continue
        for j, h2 in enumerate(hashes2):
            if not h2:
                continue
            if hamming_distance(h1, h2) <= THRESHOLD:
                matched1.add(i)
                matched2.add(j)

    if not matched1:
        return 0.0, 0

    # Score = fraction of images that have a match (penalises large unique sets)
    score = len(matched1) / max(len(imgs1), len(imgs2))
    return score, len(matched1)


# ══════════════════════════════════════════════════════════════════════════════
# STRUCTURE SIMILARITY
# ══════════════════════════════════════════════════════════════════════════════

HEADING_RE = re.compile(
    r"^(?:"
    r"(?:\d+[\.\d]*\.?\s+[A-Z].{2,80})"       # Numbered: "1. Introduction"
    r"|(?:[A-Z][A-Z\s]{3,50})"                 # ALL CAPS heading
    r"|(?:#{1,4}\s+.{3,80})"                   # Markdown: "## Heading"
    r")$",
    re.MULTILINE,
)

def extract_headings(text: str) -> list[str]:
    headings = []
    for line in text.splitlines():
        line = line.strip()
        if HEADING_RE.match(line):
            # Normalize heading text
            h = re.sub(r"^[#\d\.\s]+", "", line).strip().lower()
            h = re.sub(r"[^a-z0-9\s]", "", h).strip()
            if 3 <= len(h.split()) <= 12:
                headings.append(h)
    return headings

def structure_similarity(text1: str, text2: str) -> tuple[float, list[tuple[str,str]]]:
    """
    Returns (score, list_of_matching_heading_pairs).
    """
    h1 = extract_headings(text1)
    h2 = extract_headings(text2)

    if not h1 or not h2:
        return 0.0, []

    matches = []
    used2   = set()
    for head1 in h1:
        tok1 = set(head1.split())
        best_score, best_j, best_h2 = 0.0, -1, ""
        for j, head2 in enumerate(h2):
            if j in used2:
                continue
            tok2 = set(head2.split())
            s = jaccard_similarity(tok1, tok2)
            if s > best_score:
                best_score, best_j, best_h2 = s, j, head2
        if best_score >= 0.5:
            matches.append((head1, best_h2))
            used2.add(best_j)

    score = len(matches) / max(len(h1), len(h2)) if (h1 or h2) else 0.0
    return score, matches[:10]


# ══════════════════════════════════════════════════════════════════════════════
# SENTENCE MATCHING
# ══════════════════════════════════════════════════════════════════════════════

def find_matching_sentences(text1: str, text2: str,
                            min_words: int = 8,
                            threshold: float = 0.75) -> list[tuple[str, str, float]]:
    def split_sentences(text):
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

    matches.sort(key=lambda x: -x[2])
    seen, unique = set(), []
    for m in matches:
        if m[0] not in seen:
            seen.add(m[0])
            unique.append(m)
    return unique[:15]


# ══════════════════════════════════════════════════════════════════════════════
# COMPOSITE SCORE
# ══════════════════════════════════════════════════════════════════════════════

def overall_score(text_score: float,
                  code_score: float,  has_code: bool,
                  img_score: float,   has_imgs: bool,
                  struct_score: float) -> float:
    """
    Weighted composite across all four dimensions.
    Weights shift depending on what content was actually found.
    """
    if has_code and has_imgs:
        w = {"text": 0.50, "code": 0.20, "image": 0.20, "struct": 0.10}
    elif has_code:
        w = {"text": 0.60, "code": 0.25, "image": 0.00, "struct": 0.15}
    elif has_imgs:
        w = {"text": 0.60, "code": 0.00, "image": 0.25, "struct": 0.15}
    else:
        w = {"text": 0.75, "code": 0.00, "image": 0.00, "struct": 0.25}

    return (text_score   * w["text"]   +
            code_score   * w["code"]   +
            img_score    * w["image"]  +
            struct_score * w["struct"])


# ══════════════════════════════════════════════════════════════════════════════
# RENDERING
# ══════════════════════════════════════════════════════════════════════════════

COLORS = {
    "reset":  "\033[0m",  "bold":   "\033[1m",
    "red":    "\033[91m", "yellow": "\033[93m",
    "green":  "\033[92m", "cyan":   "\033[96m",
    "dim":    "\033[2m",  "blue":   "\033[94m",
}

def c(color: str, text: str) -> str:
    return f"{COLORS.get(color,'')}{text}{COLORS['reset']}"

def verdict(score: float) -> tuple[str, str]:
    if score >= 0.70: return "HIGH SIMILARITY — likely plagiarism",          "red"
    if score >= 0.45: return "MODERATE SIMILARITY — manual review advised",  "yellow"
    if score >= 0.20: return "LOW SIMILARITY — some shared content",         "cyan"
    return                   "MINIMAL SIMILARITY — likely original work",    "green"

def bar(value: float, width: int = 36) -> str:
    filled = int(round(value * width))
    col = "red" if value >= 0.7 else "yellow" if value >= 0.45 else "green"
    return c(col, "█" * filled) + c("dim", "░" * (width - filled))

def section(title: str, w: int = 67) -> None:
    print(c("bold", f"\n  {title}"))
    print(c("dim",  "  " + "─" * (w - 2)))

def print_report(path1, path2, word_counts,
                 text_scores, sent_matches,
                 code_score, code_blocks,
                 img_score,  img_match_count, img_counts,
                 struct_score, struct_matches,
                 final_score,
                 ocr_flags) -> None:

    W = 67
    print()
    print(c("bold", "═" * W))
    print(c("bold", "        ASSIGNMENT PLAGIARISM CHECKER — REPORT"))
    print(c("bold", "═" * W))
    ocr1 = " [OCR]" if ocr_flags[0] else ""
    ocr2 = " [OCR]" if ocr_flags[1] else ""
    print(f"  File 1 : {os.path.basename(path1)}{ocr1}  ({word_counts[0]:,} words)")
    print(f"  File 2 : {os.path.basename(path2)}{ocr2}  ({word_counts[1]:,} words)")

    # ── Overall ───────────────────────────────────────────────────────────────
    label, col = verdict(final_score)
    print()
    print(c("bold", "  OVERALL SIMILARITY SCORE"))
    print(f"  {bar(final_score)}  {c(col, f'{final_score*100:.1f}%')}")
    print(f"\n  Verdict: {c(col, c('bold', label))}")

    # ── Dimension summary ─────────────────────────────────────────────────────
    section("DIMENSION SUMMARY", W)
    dims = [
        ("📝 Text",      text_scores["composite"], True),
        ("💻 Code",      code_score,               len(code_blocks[0]) > 0 or len(code_blocks[1]) > 0),
        ("🖼  Images",   img_score,                img_counts[0] > 0 or img_counts[1] > 0),
        ("🏗  Structure", struct_score,             True),
    ]
    for name, score, active in dims:
        note = "" if active else c("dim", "  (not detected)")
        print(f"  {name:<14}  {bar(score, 20)}  {score*100:5.1f}%{note}")

    # ── Text metrics ──────────────────────────────────────────────────────────
    section("TEXT METRIC BREAKDOWN", W)
    labels = {
        "cosine":        "Cosine Similarity (TF-weighted)",
        "jaccard":       "Jaccard Index (vocabulary overlap)",
        "bigram_dice":   "Bigram Dice (2-word phrases)",
        "trigram_dice":  "Trigram Dice (3-word phrases)",
        "fourgram_dice": "4-gram Dice (4-word phrases)",
        "lcs_chunk":     "Chunk LCS (verbatim passage overlap)",
    }
    for key, lbl in labels.items():
        v = text_scores[key]
        print(f"  {lbl:<44}  {bar(v, 16)}  {v*100:5.1f}%")

    # ── Code blocks ───────────────────────────────────────────────────────────
    section("CODE ANALYSIS", W)
    nb1, nb2 = len(code_blocks[0]), len(code_blocks[1])
    if nb1 == 0 and nb2 == 0:
        print(c("dim", "  No code blocks detected in either document."))
    else:
        print(f"  Code blocks found — Doc1: {nb1}, Doc2: {nb2}")
        print(f"  AST-level code similarity:  {bar(code_score, 20)}  {code_score*100:.1f}%")
        if code_score >= 0.7:
            print(c("red", "  ⚠  High code similarity — possible code copying detected."))

    # ── Images ────────────────────────────────────────────────────────────────
    section("IMAGE ANALYSIS", W)
    n1, n2 = img_counts
    if n1 == 0 and n2 == 0:
        print(c("dim", "  No embedded images found in either document."))
    else:
        print(f"  Images found — Doc1: {n1}, Doc2: {n2}")
        print(f"  Matching image pairs: {img_match_count}")
        print(f"  Visual similarity:    {bar(img_score, 20)}  {img_score*100:.1f}%")
        if img_score >= 0.5:
            print(c("yellow", "  ⚠  Significant image overlap detected."))

    # ── Structure ─────────────────────────────────────────────────────────────
    section("STRUCTURE ANALYSIS", W)
    if not struct_matches:
        if struct_score == 0.0:
            print(c("dim", "  No headings detected — structure comparison unavailable."))
        else:
            print("  No matching headings found.")
    else:
        print(f"  Heading similarity: {bar(struct_score, 20)}  {struct_score*100:.1f}%")
        print(f"  Matching headings ({len(struct_matches)}):")
        for h1, h2 in struct_matches:
            eq = "≈" if h1 != h2 else "="
            print(f"    {c('dim','•')} \"{h1}\"  {eq}  \"{h2}\"")

    # ── Sentence matches ──────────────────────────────────────────────────────
    section("HIGHLY SIMILAR SENTENCE PAIRS", W)
    if not sent_matches:
        print(c("green", "  No highly similar individual sentences found."))
    else:
        for i, (s1, s2, score) in enumerate(sent_matches, 1):
            col2 = "red" if score >= 0.9 else "yellow"
            print(f"\n  {c('bold', f'[{i}]')}  Similarity: {c(col2, f'{score*100:.0f}%')}")
            print(f"  {c('dim','  Doc1:')} {s1[:200]}{'…' if len(s1)>200 else ''}")
            print(f"  {c('dim','  Doc2:')} {s2[:200]}{'…' if len(s2)>200 else ''}")

    print()
    print(c("bold", "═" * W))
    print()


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Compare two assignment PDFs for plagiarism.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  plagcheck essay1.pdf essay2.pdf
  plagcheck essay1.pdf essay2.pdf --no-ocr
  plagcheck essay1.pdf essay2.pdf --no-images
  plagcheck essay1.pdf essay2.pdf --sentence-threshold 0.85
        """,
    )
    parser.add_argument("pdf1",  help="Path to the first PDF")
    parser.add_argument("pdf2",  help="Path to the second PDF")
    parser.add_argument("--no-ocr",       action="store_true", help="Disable OCR fallback for scanned PDFs")
    parser.add_argument("--no-images",    action="store_true", help="Skip image comparison")
    parser.add_argument("--no-sentences", action="store_true", help="Skip sentence-level matching")
    parser.add_argument("--sentence-threshold", type=float, default=0.75, metavar="T",
                        help="Jaccard threshold for sentence pairs (default: 0.75)")
    args = parser.parse_args()

    # ── Extract text ──────────────────────────────────────────────────────────
    print(c("cyan", "\n  Extracting text…"))
    text1, ocr1 = get_text(args.pdf1, not args.no_ocr)
    text2, ocr2 = get_text(args.pdf2, not args.no_ocr)
    wc1, wc2 = len(text1.split()), len(text2.split())
    print(f"  → Doc 1: {wc1:,} words {'(OCR)' if ocr1 else ''}")
    print(f"  → Doc 2: {wc2:,} words {'(OCR)' if ocr2 else ''}")

    if wc1 < 20 or wc2 < 20:
        print(c("yellow", "  [WARN] Very little text extracted. Results may be unreliable."))

    # ── Text scores ───────────────────────────────────────────────────────────
    print(c("cyan", "  Computing text similarity…"))
    t_scores = text_similarity(text1, text2)

    # ── Sentence matches ──────────────────────────────────────────────────────
    sent_matches = []
    if not args.no_sentences:
        print(c("cyan", "  Scanning for matching sentences…"))
        sent_matches = find_matching_sentences(text1, text2, threshold=args.sentence_threshold)

    # ── Code similarity ───────────────────────────────────────────────────────
    print(c("cyan", "  Analysing code blocks…"))
    blocks1 = extract_code_blocks(text1)
    blocks2 = extract_code_blocks(text2)
    c_score = code_block_similarity(blocks1, blocks2)

    # ── Image similarity ──────────────────────────────────────────────────────
    i_score, img_match_count, imgs1, imgs2 = 0.0, 0, [], []
    if not args.no_images:
        print(c("cyan", "  Comparing images…"))
        imgs1 = extract_images_from_pdf(args.pdf1)
        imgs2 = extract_images_from_pdf(args.pdf2)
        i_score, img_match_count = image_similarity(imgs1, imgs2)

    # ── Structure similarity ──────────────────────────────────────────────────
    print(c("cyan", "  Analysing document structure…"))
    s_score, struct_matches = structure_similarity(text1, text2)

    # ── Final composite ───────────────────────────────────────────────────────
    has_code = len(blocks1) > 0 or len(blocks2) > 0
    has_imgs = len(imgs1) > 0 or len(imgs2) > 0
    final = overall_score(t_scores["composite"], c_score, has_code,
                          i_score, has_imgs, s_score)

    print_report(
        args.pdf1, args.pdf2,
        (wc1, wc2),
        t_scores, sent_matches,
        c_score, (blocks1, blocks2),
        i_score, img_match_count, (len(imgs1), len(imgs2)),
        s_score, struct_matches,
        final,
        (ocr1, ocr2),
    )


if __name__ == "__main__":
    main()
