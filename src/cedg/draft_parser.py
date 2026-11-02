"""Draft parser for pointer-constrained writing.

A section draft is only accepted when every citation is a valid evidence ID
(``[Source:E012]``), every number sits inside a registered variable placeholder
(``⟨VAR:name⟩``), and judgment sentences carry ``[INFER]``. Hard violations are
returned as ``errors`` (draft is bounced back for rewriting); soft findings are
``warnings`` (logged, not blocking).
"""
import re
from dataclasses import dataclass, field

# --- token patterns ----------------------------------------------------------

SOURCE_RE = re.compile(r'\[Source:(E\d{3})\]')
VAR_RE = re.compile(r'⟨VAR:([A-Za-z_][\w]*)⟩')
INFER_RE = re.compile(r'\[INFER\]')

# any "[Source: …]" that is NOT a well-formed E-ID citation (e.g. legacy
# "[Source: Wind资讯]" or "[Source:E12]")
SOURCE_ANY_RE = re.compile(r'\[[Ss]ource[：:]\s*([^\]]*)\]')
# any "⟨VAR: …⟩" whose name is not a legal identifier
VAR_ANY_RE = re.compile(r'⟨VAR:([^⟩]*)⟩')

YEAR_RE = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\d)')
# Inline section references ("如 2.3 节所述", "见第3章", "Section 1.2") — NOT decimal
# quantities like 123.4, which must stay flagged as bare numbers.
SECTION_REF_RE = re.compile(
    r'(第\s*\d+(?:\.\d+)*\s*[章节部分])'
    r'|((?<![\w.])\d+(?:\.\d+)+\s*(?:节|章节|小节|[Ss]ection))'
)
LIST_MARKER_RE = re.compile(r'(?m)^\s*(?:[-*+]|\d+[.、)])\s+')
HEADING_NUM_RE = re.compile(r'(?m)^(#{1,6}\s*)\d+(?:\.\d+)*[.、]?\s+')
EID_RE = re.compile(r'E\d{3}')
IMPORT_RE = re.compile(r'@import\s+"[^"]*"')
URL_RE = re.compile(r'https?://\S+')
IMAGE_MD_RE = re.compile(r'!\[[^\]]*\]\([^)]*\)')

# A digit-run that is not part of an ASCII word (E012, GPT4) — CJK-preceded
# digits (营收123.4亿) DO match.
BARE_NUM_RE = re.compile(r'(?<![A-Za-z⟨:])\d[\d,]*\.?\d*%?')

# judgement-flavoured verbs signalling an unsourced opinion
JUDGEMENT_HINTS = (
    '增长', '下滑', '上升', '下降', '领先', '落后', '恶化', '改善', '超预期',
    '不及预期', '回落', '放缓', '加速', '扩张', '收缩', '亏损', '盈利',
    '提升', '下降', '强劲', '疲软', '承压', '突破', '反超',
    'grow', 'decline', 'surge', 'lead', 'exceed', 'deteriorate', 'improve',
)

# Sentence boundaries: fullwidth enders always end a sentence; an ASCII '.'/'!'/'?'
# only when followed by whitespace — so decimals (2.1), filenames (fig.png) and
# citation-internal dots stay intact. Newlines split paragraphs.
SENTENCE_SPLIT_RE = re.compile(r'(?<=[。！？!?．])\s*|(?<=[.!?])\s+|\n+')


@dataclass
class Claim:
    cid: str
    ctype: str            # num / fact / infer
    text: str
    source_eids: list = field(default_factory=list)
    var_names: list = field(default_factory=list)


@dataclass
class ParsedDraft:
    claims: list = field(default_factory=list)
    errors: list = field(default_factory=list)    # hard errors → bounce the draft
    warnings: list = field(default_factory=list)  # soft findings → log only


def _is_noise_fragment(fragment: str) -> bool:
    """Headings, image imports, bare markdown links — not claims."""
    stripped = fragment.strip()
    if not stripped:
        return True
    if stripped.startswith('#'):
        return True
    if '@import' in stripped:
        return True
    if re.fullmatch(r'!\[[^\]]*\]\([^)]*\)', stripped):
        return True
    # fragments made purely of markers (e.g. a lone "[INFER]" after a split)
    if not INFER_RE.sub('', stripped).strip():
        return True
    return False


def _strip_whitelisted(text: str) -> str:
    """Remove tokens that legitimately contain digits before bare-number scan."""
    text = VAR_ANY_RE.sub(' ', text)          # ⟨VAR:…⟩ placeholders (well- or ill-formed)
    text = SOURCE_ANY_RE.sub(' ', text)       # [Source:…] citations
    text = INFER_RE.sub(' ', text)
    text = IMPORT_RE.sub(' ', text)           # @import "fig_2024.png"
    text = IMAGE_MD_RE.sub(' ', text)         # ![alt](path2024.png)
    text = URL_RE.sub(' ', text)              # http://…/2024/…
    text = YEAR_RE.sub(' ', text)             # 2024, 1999 …
    text = SECTION_REF_RE.sub(' ', text)      # 2.3 节 / 第3章 / Section 1.2
    text = HEADING_NUM_RE.sub(r'\1', text)    # "## 1. 标题" → "## 标题"
    text = LIST_MARKER_RE.sub(' ', text)      # "1. ", "- " at line starts
    text = EID_RE.sub(' ', text)              # stray E012 mentions
    return text


def parse_draft(text: str, valid_eids: set, valid_vars: set) -> ParsedDraft:
    """Validate a section draft and split it into typed claims."""
    parsed = ParsedDraft()

    # 1. dangling / malformed pointers --------------------------------------
    for m in SOURCE_ANY_RE.finditer(text):
        inner = m.group(1).strip()
        well_formed = SOURCE_RE.fullmatch(m.group(0))
        if not well_formed:
            parsed.errors.append(
                f"Malformed citation '{m.group(0)}': citations must use the exact "
                f"evidence-ID form [Source:E012] — source names are not allowed."
            )
        elif inner not in valid_eids:
            parsed.errors.append(
                f"Dangling citation '{m.group(0)}': E-ID not in the evidence list "
                f"of the data context."
            )

    for m in VAR_ANY_RE.finditer(text):
        name = m.group(1).strip()
        if not VAR_RE.fullmatch(m.group(0)):
            parsed.errors.append(
                f"Malformed placeholder '{m.group(0)}': variable names must match "
                f"⟨VAR:snake_case⟩."
            )
        elif name not in valid_vars:
            parsed.errors.append(
                f"Dangling placeholder '{m.group(0)}': variable was never registered "
                f"via _set_var in <execute>."
            )

    # 2. bare numbers --------------------------------------------------------
    stripped = _strip_whitelisted(text)
    for m in BARE_NUM_RE.finditer(stripped):
        parsed.errors.append(
            f"Bare number '{m.group(0)}': numbers must be written as "
            f"⟨VAR:name⟩ placeholders registered via _set_var (years and section "
            f"numbers excepted)."
        )

    # 3. claim segmentation ---------------------------------------------------
    claims_src = list(SOURCE_RE.findall(text))
    fragments = [f for f in SENTENCE_SPLIT_RE.split(text) if not _is_noise_fragment(f)]
    for idx, fragment in enumerate(fragments, start=1):
        var_names = VAR_RE.findall(fragment)
        source_eids = SOURCE_RE.findall(fragment)
        if var_names:
            ctype = 'num'
        elif source_eids:
            ctype = 'fact'
        else:
            ctype = 'infer'
        parsed.claims.append(Claim(
            cid=f"C{idx:03d}",
            ctype=ctype,
            text=fragment.strip(),
            source_eids=source_eids,
            var_names=var_names,
        ))

    # 4. unsourced judgements → warnings --------------------------------------
    for claim in parsed.claims:
        if claim.source_eids:
            continue
        lowered = claim.text.lower()
        if any(h in claim.text or h in lowered for h in JUDGEMENT_HINTS):
            parsed.warnings.append(
                f"Unsourced judgement (claim {claim.cid}): '{claim.text[:50]}…' "
                f"has no [Source:E…] support; consider evidence or [INFER]."
            )

    return parsed
