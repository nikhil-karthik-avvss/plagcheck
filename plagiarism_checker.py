#!/usr/bin/env python3
"""
plagcheck — Assignment Plagiarism Checker
Robust comparison across text, code, visuals, and structure.
Works with PDFs from Word, LibreOffice, LaTeX, scanners, or any source.
"""

import sys
import os
import re
import ast
import io
import math
import argparse
from collections import Counter

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

COLORS = {
    "reset":  "\033[0m", "bold":   "\033[1m",
    "red":    "\033[91m","yellow": "\033[93m",
    "green":  "\033[92m","cyan":   "\033[96m",
    "dim":    "\033[2m", "blue":   "\033[94m",
}
def c(color, text): return f"{COLORS.get(color,'')}{text}{COLORS['reset']}"
def die(msg):  print(c("red", f"\n  [ERROR] {msg}")); sys.exit(1)
def warn(msg): print(c("yellow", f"  [WARN] {msg}"))


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — PAGE RASTERIZATION
# Converts every PDF page to a PIL Image.
# • 150 DPI  → visual comparison (perceptual hashing)
# • 250 DPI  → OCR-quality render (used in extract_all_text if needed)
# Works regardless of PDF origin: Word, LibreOffice, LaTeX, scanner.
# ══════════════════════════════════════════════════════════════════════════════

def rasterize_pdf(pdf_path: str, dpi: int = 150) -> list:
    """Return list of (PIL.Image, page_number) for every page."""
    try:
        import fitz
        from PIL import Image
    except ImportError as e:
        die(f"PyMuPDF / Pillow not installed: {e}")

    pages = []
    try:
        doc = fitz.open(pdf_path)
        zoom = dpi / 72.0
        mat  = fitz.Matrix(zoom, zoom)
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            pages.append((img, i + 1))
        doc.close()
    except Exception as e:
        die(f"Could not open {pdf_path}: {e}")
    return pages


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — TEXT EXTRACTION
# Three-stage pipeline, all stages run and results are merged:
#
#   Stage 1: pdfplumber  — best for digital PDFs (Word, LibreOffice, LaTeX)
#   Stage 2: PyMuPDF     — fast fallback for most digitally-created PDFs
#   Stage 3: easyocr     — fully pip-installable OCR engine (no system binary
#                          needed). Runs on rasterized pages to catch:
#                            • scanned / image-only PDFs
#                            • text inside embedded figures/diagrams
#                            • handwritten labels
#
# Merging: OCR output lines that are NOT already present in digital text
# (< 40% token overlap) are appended, so we get the union of both.
# ══════════════════════════════════════════════════════════════════════════════

def _extract_digital(pdf_path: str) -> str:
    """Embedded-text extraction: pdfplumber then PyMuPDF fallback."""
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t: parts.append(t)
        text = "\n".join(parts).strip()
        if len(text.split()) > 30:
            return text
    except Exception:
        pass
    try:
        import fitz
        doc = fitz.open(pdf_path)
        parts = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(p for p in parts if p).strip()
    except Exception:
        pass
    return ""


def _run_easyocr(page_images: list) -> str:
    """
    Run easyocr on pre-rasterized page images.
    easyocr is fully pip-installable — no system Tesseract binary required.
    """
    try:
        import easyocr
        import numpy as np
    except ImportError:
        return ""
    try:
        reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        parts = []
        for img, _ in page_images:
            arr = np.array(img)
            results = reader.readtext(arr, detail=0, paragraph=True)
            parts.extend(results)
        return "\n".join(parts)
    except Exception as e:
        warn(f"OCR error: {e}")
        return ""


def _merge(digital: str, ocr: str) -> str:
    """
    Merge digital + OCR text.
    Adds OCR lines that are not already present in the digital text,
    catching text hidden inside images/figures that pdfplumber can't see.
    """
    if not ocr:    return digital
    if not digital: return ocr
    digital_tokens = set(digital.lower().split())
    extra = []
    for line in ocr.splitlines():
        line = line.strip()
        if len(line.split()) < 4: continue
        overlap = len(set(line.lower().split()) & digital_tokens) / max(len(line.split()), 1)
        if overlap < 0.4:
            extra.append(line)
    return (digital + "\n" + "\n".join(extra)).strip() if extra else digital


def extract_all_text(pdf_path: str, page_images: list,
                     use_ocr: bool) -> tuple[str, bool]:
    """Full pipeline. Returns (text, ocr_was_used)."""
    digital  = _extract_digital(pdf_path)
    ocr_text = ""
    used_ocr = False

    if use_ocr:
        ocr_text = _run_easyocr(page_images)
        used_ocr = bool(ocr_text.strip())

    merged = _merge(digital, ocr_text)

    # Last resort: re-rasterize at higher DPI if still nearly empty
    if len(merged.split()) < 40 and use_ocr and not used_ocr:
        warn(f"Low yield for {os.path.basename(pdf_path)}, retrying OCR at 250 DPI…")
        hi_pages = rasterize_pdf(pdf_path, dpi=250)
        ocr_text = _run_easyocr(hi_pages)
        merged   = _merge(digital, ocr_text)
        used_ocr = bool(ocr_text.strip())

    return merged.strip(), used_ocr


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — CODE DETECTION & SIMILARITY
# Detects code in PDFs from any origin:
#   • Fenced markdown blocks  (```)
#   • Heuristic detection of monospaced / indented blocks
#     using C/C++/Arduino/Java/Python syntax signals
# Comparison: AST normalisation for Python (renames all variables),
#             raw token n-gram for other languages.
# ══════════════════════════════════════════════════════════════════════════════

CODE_FENCE_RE = re.compile(r"```[\w+]*\s*\n(.*?)```", re.DOTALL)

CODE_LINE_RE = re.compile(
    r"(?:[{};]"
    r"|(?:void|int|float|char|bool|String|return|if\s*\(|for\s*\(|while\s*\()"
    r"|(?:def |class |import |from |#include|#define|pinMode|digitalWrite|analogRead)"
    r"|(?:==|!=|<=|>=|&&|\|\||\+\+|--)"
    r"|(?:\w+\s*\(.*\)\s*[{;]))"
)

def extract_code_blocks(text: str) -> list[str]:
    blocks = []
    # 1. Fenced markdown
    for m in CODE_FENCE_RE.finditer(text):
        b = m.group(1).strip()
        if b: blocks.append(b)
    # 2. Heuristic: consecutive lines that look like code
    current = []
    for line in text.splitlines():
        stripped = line.strip()
        if CODE_LINE_RE.search(stripped) or (line.startswith("    ") and stripped):
            current.append(line)
        else:
            if len(current) >= 3:
                blocks.append("\n".join(current))
            current = []
    if len(current) >= 3:
        blocks.append("\n".join(current))
    # Deduplicate
    seen, out = set(), []
    for b in blocks:
        key = b[:120]
        if key not in seen:
            seen.add(key); out.append(b)
    return out


class ASTNorm(ast.NodeVisitor):
    """Canonical token stream from a Python AST, all identifiers renamed."""
    def __init__(self):
        self.tokens: list[str] = []
        self._m: dict[str, str] = {}
        self._n = 0
    def _r(self, name):
        if name not in self._m: self._m[name] = f"V{self._n}"; self._n += 1
        return self._m[name]
    def generic_visit(self, node):
        self.tokens.append(type(node).__name__); super().generic_visit(node)
    def visit_Name(self, node):        self.tokens.append(self._r(node.id))
    def visit_FunctionDef(self, node):
        self.tokens += ["FuncDef", self._r(node.name)]; self.generic_visit(node)
    def visit_arg(self, node):         self.tokens.append(self._r(node.arg))
    def visit_Constant(self, node):    self.tokens.append(f"C_{type(node.value).__name__}")


def _code_tokens(block: str) -> list[str]:
    try:
        tree = ast.parse(block); v = ASTNorm(); v.visit(tree); return v.tokens
    except SyntaxError:
        return re.findall(r"[A-Za-z_]\w*|[+\-*/=<>!&|^~]+|[(){}\[\],.;:]|\d+", block)


def _ngram(t1, t2, n=3) -> float:
    ng1 = Counter(tuple(t1[i:i+n]) for i in range(len(t1)-n+1))
    ng2 = Counter(tuple(t2[i:i+n]) for i in range(len(t2)-n+1))
    shared = sum((ng1 & ng2).values())
    total  = sum(ng1.values()) + sum(ng2.values())
    return 2 * shared / total if total else 0.0


def code_similarity(b1: list[str], b2: list[str]) -> float:
    if not b1 or not b2: return 0.0
    scores = []
    for x in b1:
        tx = _code_tokens(x)
        scores.append(max(_ngram(tx, _code_tokens(y), 3) for y in b2))
    for y in b2:
        ty = _code_tokens(y)
        scores.append(max(_ngram(ty, _code_tokens(x), 3) for x in b1))
    return sum(scores) / len(scores)


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — VISUAL SIMILARITY
# Two-level comparison to catch copies at any scale:
#
#   Level A — Full-page perceptual hash
#             Catches entirely copied or near-identical pages.
#
#   Level B — Sliding-window tile hashing
#             Splits each page into overlapping 64×64 px tiles.
#             A matching tile means a copied figure/diagram even when
#             the surrounding page content is completely different.
#             This is what catches circuit diagrams, connection diagrams,
#             charts, and any other visual copied into an otherwise unique page.
# ══════════════════════════════════════════════════════════════════════════════

def _phash(img, size: int = 16) -> str:
    try:
        thumb  = img.resize((size, size)).convert("L")
        pixels = list(thumb.getdata())
        avg    = sum(pixels) / len(pixels)
        return "".join("1" if p >= avg else "0" for p in pixels)
    except Exception:
        return ""

def _hamming(h1: str, h2: str) -> int:
    return sum(a != b for a, b in zip(h1, h2))

def _tile_hashes(img, tile: int = 64, step: int = 32) -> list[str]:
    """Overlapping tile perceptual hashes for a page image."""
    w, h = img.size
    out = []
    for y in range(0, h - tile + 1, step):
        for x in range(0, w - tile + 1, step):
            h_ = _phash(img.crop((x, y, x+tile, y+tile)), size=8)
            if h_: out.append(h_)
    return out

def visual_similarity(pages1: list, pages2: list) -> tuple[float, int, int]:
    """Returns (score 0-1, matching_full_pages, matching_tile_pairs)."""
    if not pages1 or not pages2: return 0.0, 0, 0

    FULL_T = int(16*16 * 0.12)   # 12% bit-diff tolerance for full pages
    TILE_T = int(8 * 8 * 0.15)   # 15% for tiles

    imgs1 = [img for img, _ in pages1]
    imgs2 = [img for img, _ in pages2]

    # Level A: full-page hash
    ph1 = [_phash(img, 16) for img in imgs1]
    ph2 = [_phash(img, 16) for img in imgs2]
    matched1, matched2 = set(), set()
    for i, h1 in enumerate(ph1):
        if not h1: continue
        for j, h2 in enumerate(ph2):
            if not h2: continue
            if _hamming(h1, h2) <= FULL_T:
                matched1.add(i); matched2.add(j)

    # Level B: tile hash on pages not already matched
    tile_matches = 0
    um1 = [i for i in range(len(imgs1)) if i not in matched1]
    um2 = [j for j in range(len(imgs2)) if j not in matched2]
    for i in um1:
        tiles1 = _tile_hashes(imgs1[i])
        for j in um2:
            tiles2_set = set(_tile_hashes(imgs2[j]))
            for t1 in tiles1:
                for t2 in tiles2_set:
                    if _hamming(t1, t2) <= TILE_T:
                        tile_matches += 1
                        break

    pg  = len(matched1)
    tot = max(len(imgs1), len(imgs2))
    page_score = pg / tot if tot else 0.0
    tile_score = min(tile_matches / max(tot * 5, 1), 1.0)
    return 0.7 * page_score + 0.3 * tile_score, pg, tile_matches


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 5 — TEXT SIMILARITY
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

def _norm(text): return re.sub(r"\s+"," ", re.sub(r"[^a-z0-9\s]"," ", text.lower())).strip()
def _tok(text, rm=True):
    w = _norm(text).split()
    return [x for x in w if x not in STOPWORDS and len(x)>2] if rm else w

def _cosine(t1, t2) -> float:
    c1, c2 = Counter(t1), Counter(t2)
    vocab = set(c1)|set(c2)
    if not vocab: return 0.0
    dot  = sum(c1[w]*c2[w] for w in vocab)
    m1   = math.sqrt(sum(v**2 for v in c1.values()))
    m2   = math.sqrt(sum(v**2 for v in c2.values()))
    return dot/(m1*m2) if m1 and m2 else 0.0

def _jaccard(s1, s2) -> float:
    if not s1 and not s2: return 0.0
    return len(s1&s2)/len(s1|s2)

def _lcs(t1, t2, size=150) -> float:
    def ch(s): return {s[i:i+size] for i in range(0, max(0,len(s)-size+1), size//2)}
    c1,c2 = ch(t1),ch(t2)
    if not c1 and not c2: return 0.0
    return len(c1&c2)/max(len(c1),len(c2))

def text_similarity(text1: str, text2: str) -> dict:
    t1,t2   = _tok(text1), _tok(text2)
    r1,r2   = _tok(text1,False), _tok(text2,False)
    n1,n2   = _norm(text1), _norm(text2)
    s = {
        "cosine":        _cosine(t1,t2),
        "jaccard":       _jaccard(set(t1),set(t2)),
        "bigram_dice":   _ngram(t1,t2,2),
        "trigram_dice":  _ngram(t1,t2,3),
        "fourgram_dice": _ngram(r1,r2,4),
        "lcs_chunk":     _lcs(n1,n2),
    }
    w = {"cosine":0.20,"jaccard":0.10,"bigram_dice":0.15,
         "trigram_dice":0.25,"fourgram_dice":0.20,"lcs_chunk":0.10}
    s["composite"] = sum(s[k]*w[k] for k in w)
    return s


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 6 — STRUCTURE SIMILARITY
# ══════════════════════════════════════════════════════════════════════════════

HEADING_RE = re.compile(
    r"^(?:\d+[\.\d]*\.?\s+[A-Z].{2,80}|[A-Z][A-Z\s]{3,50}|#{1,4}\s+.{3,80})$",
    re.MULTILINE,
)
def _headings(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if HEADING_RE.match(line):
            h = re.sub(r"[^a-z0-9\s]","", re.sub(r"^[#\d\.\s]+","",line).strip().lower()).strip()
            if 3 <= len(h.split()) <= 12: out.append(h)
    return out

def structure_similarity(t1, t2):
    h1, h2 = _headings(t1), _headings(t2)
    if not h1 or not h2: return 0.0, []
    matches, used2 = [], set()
    for head1 in h1:
        tok1 = set(head1.split())
        bs, bj, bh = 0.0, -1, ""
        for j, head2 in enumerate(h2):
            if j in used2: continue
            s = _jaccard(tok1, set(head2.split()))
            if s > bs: bs, bj, bh = s, j, head2
        if bs >= 0.5: matches.append((head1, bh)); used2.add(bj)
    return len(matches)/max(len(h1),len(h2)), matches[:10]


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 7 — SENTENCE MATCHING
# ══════════════════════════════════════════════════════════════════════════════

def matching_sentences(t1, t2, threshold=0.75):
    def split(t):
        return [p.strip() for p in re.split(r'(?<=[.!?])\s+', t.strip()) if len(p.split())>=8]
    results = []
    for s1 in split(t1):
        tok1 = set(_tok(s1))
        for s2 in split(t2):
            j = _jaccard(tok1, set(_tok(s2)))
            if j >= threshold: results.append((s1,s2,j))
    results.sort(key=lambda x: -x[2])
    seen, out = set(), []
    for m in results:
        if m[0] not in seen: seen.add(m[0]); out.append(m)
    return out[:15]


# ══════════════════════════════════════════════════════════════════════════════
# COMPOSITE SCORE
# ══════════════════════════════════════════════════════════════════════════════

def composite(text_s, code_s, has_code, vis_s, struct_s) -> float:
    if has_code:
        w = {"t":0.45,"c":0.25,"v":0.15,"s":0.15}
    else:
        w = {"t":0.55,"c":0.00,"v":0.25,"s":0.20}
    return text_s*w["t"] + code_s*w["c"] + vis_s*w["v"] + struct_s*w["s"]


# ══════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════

def bar(value, width=36):
    filled = int(round(value*width))
    col = "red" if value>=0.7 else "yellow" if value>=0.45 else "green"
    return c(col,"█"*filled) + c("dim","░"*(width-filled))

def verdict(score):
    if score>=0.70: return "HIGH SIMILARITY — likely plagiarism",         "red"
    if score>=0.45: return "MODERATE SIMILARITY — manual review advised", "yellow"
    if score>=0.20: return "LOW SIMILARITY — some shared content",        "cyan"
    return                 "MINIMAL SIMILARITY — likely original work",   "green"

def sec(title, W=67):
    print(c("bold", f"\n  {title}"))
    print(c("dim",  "  "+"─"*(W-2)))

def print_report(p1, p2, wc, ocr_flags,
                 t_scores, sent_matches,
                 c_score, code_blocks,
                 v_score, v_pages, v_tiles, pg_counts,
                 s_score, s_matches, score):
    W = 67
    print()
    print(c("bold","═"*W))
    print(c("bold","        ASSIGNMENT PLAGIARISM CHECKER — REPORT"))
    print(c("bold","═"*W))
    for i,(path,words,used_ocr) in enumerate(zip([p1,p2],wc,ocr_flags),1):
        tag = c("cyan"," [+OCR]") if used_ocr else ""
        print(f"  File {i} : {os.path.basename(path)}{tag}  ({words:,} words)")

    label, col = verdict(score)
    print()
    print(c("bold","  OVERALL SIMILARITY SCORE"))
    print(f"  {bar(score)}  {c(col, f'{score*100:.1f}%')}")
    print(f"\n  Verdict: {c(col, c('bold', label))}")

    has_code = len(code_blocks[0])>0 or len(code_blocks[1])>0
    sec("DIMENSION SUMMARY", W)
    for name, sc, active in [
        ("📝 Text",       t_scores["composite"], True),
        ("💻 Code",       c_score,               has_code),
        ("🖼  Visuals",   v_score,               pg_counts[0]>0),
        ("🏗  Structure", s_score,               True),
    ]:
        note = "" if active else c("dim","  (not detected)")
        print(f"  {name:<15}  {bar(sc,20)}  {sc*100:5.1f}%{note}")

    sec("TEXT METRIC BREAKDOWN", W)
    for key, lbl in [
        ("cosine",        "Cosine Similarity (TF-weighted)"),
        ("jaccard",       "Jaccard Index (vocabulary overlap)"),
        ("bigram_dice",   "Bigram Dice (2-word phrases)"),
        ("trigram_dice",  "Trigram Dice (3-word phrases)"),
        ("fourgram_dice", "4-gram Dice (4-word phrases)"),
        ("lcs_chunk",     "Chunk LCS (verbatim passage overlap)"),
    ]:
        v = t_scores[key]
        print(f"  {lbl:<44}  {bar(v,16)}  {v*100:5.1f}%")

    sec("CODE ANALYSIS", W)
    nb1,nb2 = len(code_blocks[0]),len(code_blocks[1])
    if nb1==0 and nb2==0:
        print(c("dim","  No code segments detected in either document."))
    else:
        print(f"  Code segments — Doc1: {nb1},  Doc2: {nb2}")
        print(f"  AST-normalised similarity:  {bar(c_score,20)}  {c_score*100:.1f}%")
        if   c_score>=0.70: print(c("red",   "  ⚠  High code similarity — likely code copying."))
        elif c_score>=0.45: print(c("yellow","  ⚠  Moderate code similarity — review recommended."))

    sec("VISUAL ANALYSIS", W)
    p1c,p2c = pg_counts
    if p1c==0 and p2c==0:
        print(c("dim","  Could not rasterize pages."))
    else:
        print(f"  Pages rasterized — Doc1: {p1c},  Doc2: {p2c}")
        print(f"  Matching full pages:  {v_pages}")
        print(f"  Matching image tiles: {v_tiles}  (copied figures / diagrams)")
        print(f"  Visual similarity:  {bar(v_score,20)}  {v_score*100:.1f}%")
        if   v_score>=0.50: print(c("red",   "  ⚠  High visual overlap — figures or pages may be copied."))
        elif v_score>=0.20: print(c("yellow","  ⚠  Some visual overlap — check diagrams and figures."))

    sec("STRUCTURE ANALYSIS", W)
    if not s_matches:
        msg = "No headings detected — structure comparison unavailable." if s_score==0.0 else "No closely matching headings found."
        print(c("dim", f"  {msg}"))
    else:
        print(f"  Heading similarity: {bar(s_score,20)}  {s_score*100:.1f}%")
        print(f"  Matching headings ({len(s_matches)}):")
        for h1,h2 in s_matches:
            print(f"    {c('dim','•')} \"{h1}\"  {'=' if h1==h2 else '≈'}  \"{h2}\"")

    sec("HIGHLY SIMILAR SENTENCE PAIRS", W)
    if not sent_matches:
        print(c("green","  No highly similar sentence pairs found."))
    else:
        for i,(s1,s2,sc) in enumerate(sent_matches,1):
            col2 = "red" if sc>=0.9 else "yellow"
            print(f"\n  {c('bold',f'[{i}]')}  Similarity: {c(col2,f'{sc*100:.0f}%')}")
            print(f"  {c('dim','  Doc1:')} {s1[:200]}{'…' if len(s1)>200 else ''}")
            print(f"  {c('dim','  Doc2:')} {s2[:200]}{'…' if len(s2)>200 else ''}")

    print()
    print(c("bold","═"*W))
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
  plagcheck essay1.pdf essay2.pdf --no-visuals
  plagcheck essay1.pdf essay2.pdf --sentence-threshold 0.85
        """,
    )
    parser.add_argument("pdf1")
    parser.add_argument("pdf2")
    parser.add_argument("--no-ocr",       action="store_true", help="Skip OCR (easyocr)")
    parser.add_argument("--no-visuals",   action="store_true", help="Skip visual comparison")
    parser.add_argument("--no-sentences", action="store_true", help="Skip sentence matching")
    parser.add_argument("--sentence-threshold", type=float, default=0.75, metavar="T")
    args = parser.parse_args()

    for p in [args.pdf1, args.pdf2]:
        if not os.path.isfile(p): die(f"File not found: {p}")

    print(c("cyan","\n  Rasterizing pages…"))
    pages1 = rasterize_pdf(args.pdf1, dpi=150)
    pages2 = rasterize_pdf(args.pdf2, dpi=150)
    print(f"  → Doc 1: {len(pages1)} pages")
    print(f"  → Doc 2: {len(pages2)} pages")

    print(c("cyan","  Extracting text…"))
    text1, ocr1 = extract_all_text(args.pdf1, pages1, not args.no_ocr)
    text2, ocr2 = extract_all_text(args.pdf2, pages2, not args.no_ocr)
    wc1, wc2 = len(text1.split()), len(text2.split())
    print(f"  → Doc 1: {wc1:,} words {'[+OCR]' if ocr1 else ''}")
    print(f"  → Doc 2: {wc2:,} words {'[+OCR]' if ocr2 else ''}")
    if wc1<20 or wc2<20: warn("Very little text extracted — results may be unreliable.")

    print(c("cyan","  Computing text similarity…"))
    t_scores = text_similarity(text1, text2)

    sent_matches = []
    if not args.no_sentences:
        print(c("cyan","  Scanning for matching sentences…"))
        sent_matches = matching_sentences(text1, text2, args.sentence_threshold)

    print(c("cyan","  Analysing code…"))
    blocks1 = extract_code_blocks(text1)
    blocks2 = extract_code_blocks(text2)
    c_score = code_similarity(blocks1, blocks2)
    print(f"  → Code segments — Doc1: {len(blocks1)}, Doc2: {len(blocks2)}")

    v_score, v_pages, v_tiles = 0.0, 0, 0
    if not args.no_visuals:
        print(c("cyan","  Comparing visuals…"))
        v_score, v_pages, v_tiles = visual_similarity(pages1, pages2)

    print(c("cyan","  Analysing structure…"))
    s_score, s_matches = structure_similarity(text1, text2)

    has_code = len(blocks1)>0 or len(blocks2)>0
    score = composite(t_scores["composite"], c_score, has_code, v_score, s_score)

    print_report(
        args.pdf1, args.pdf2,
        (wc1, wc2), (ocr1, ocr2),
        t_scores, sent_matches,
        c_score, (blocks1, blocks2),
        v_score, v_pages, v_tiles, (len(pages1), len(pages2)),
        s_score, s_matches,
        score,
    )

if __name__ == "__main__":
    main()
