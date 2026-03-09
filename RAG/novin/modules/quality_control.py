import re
from typing import List, Dict, Tuple
from bs4 import BeautifulSoup
REQUIRED_PRESERVED_TERMS = ["ECG"]

WARNING_TRIGGERS = ["WARNING", "CAUTION", "DANGER", "DO NOT", "MUST NOT"]
MIN_LENGTH_RATIO = 0.4
MAX_LENGTH_RATIO = 3.5


def check_html_structure(original_html: str, translated_html: str) -> List[str]:
    """Check that HTML tag structure is preserved."""
    issues = []

    orig_tags = re.findall(r"<(/?\w+)", original_html)
    trans_tags = re.findall(r"<(/?\w+)", translated_html)

    orig_set = set(orig_tags)
    trans_set = set(trans_tags)

    missing = orig_set - trans_set
    if missing:
        issues.append(f"Missing HTML tags: {', '.join(missing)}")

    orig_count = len(orig_tags)
    trans_count = len(trans_tags)
    if abs(orig_count - trans_count) > 2:
        issues.append(f"Tag count mismatch: original={orig_count}, translated={trans_count}")

    return issues


def check_preserved_terms(original_text: str, translated_text: str) -> List[str]:
    """Check that terms marked as preserve appear unchanged in translation."""
    issues = []
    for term in REQUIRED_PRESERVED_TERMS:
        if term.lower() in original_text.lower():
            if term not in translated_text:
                issues.append(f'Preserved term "{term}" missing from translation')
    return issues


def check_warning_integrity(chunk: Dict) -> List[str]:
    """For warning chunks, verify warning indicators survived."""
    issues = []
    if chunk["chunk_type"] != "warning":
        return issues

    translated_text = BeautifulSoup(
        chunk.get("translated_html", ""), "lxml"
    ).get_text()

    has_warning_indicator = any(
        w.lower() in translated_text.lower()
        for w in ["warning", "caution", "danger", "achtung", "avertissement",
                  "advertencia", "avvertenza", "waarschuwing", "varning",
                  "advarsel", "varoitus", "attention", "cuidado", "dikkat",
                  "προειδοποίηση", "警告", "주의", "تحذير"]
    )
    if not has_warning_indicator:
        issues.append("WARNING chunk may have lost its warning indicator after translation")

    return issues


def check_length_ratio(original_text: str, translated_text: str) -> List[str]:
    """Flag suspiciously short or long translations."""
    issues = []
    if not original_text.strip():
        return issues
    ratio = len(translated_text) / max(len(original_text), 1)
    if ratio < MIN_LENGTH_RATIO:
        issues.append(f"Translation suspiciously short (ratio={ratio:.2f}). Possible truncation.")
    if ratio > MAX_LENGTH_RATIO:
        issues.append(f"Translation suspiciously long (ratio={ratio:.2f}). Possible repetition.")
    return issues


def check_empty_translation(translated_html: str, original_text: str) -> List[str]:
    """Check for empty or near-empty translations."""
    issues = []
    if not original_text.strip():
        return issues
    if "<img" in translated_html:
        return issues
    translated_text = BeautifulSoup(translated_html, "lxml").get_text(strip=True)
    if not translated_text:
        issues.append("Translation is empty — original content lost")
    return issues


def validate_chunk(chunk: Dict) -> Dict:
    """
    Run all QC checks on a single translated chunk.
    Returns the chunk with added 'qc_issues' and 'qc_passed' fields.
    """
    original_text = chunk.get("text", "")
    translated_html = chunk.get("translated_html", "")
    original_html = chunk.get("html", "")
    translated_text = BeautifulSoup(translated_html, "lxml").get_text(strip=True)

    all_issues = []
    all_issues += check_html_structure(original_html, translated_html)
    all_issues += check_preserved_terms(original_text, translated_text)
    all_issues += check_warning_integrity(chunk)
    all_issues += check_length_ratio(original_text, translated_text)
    all_issues += check_empty_translation(translated_html, original_text)

    return {
        **chunk,
        "qc_issues": all_issues,
        "qc_passed": len(all_issues) == 0,
        "qc_score" : max(0, 100 - len(all_issues) * 20),
    }


def validate_all_chunks(translated_chunks: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    Validate all chunks and return validated list + summary stats.
    """
    validated = [validate_chunk(c) for c in translated_chunks]

    passed = sum(1 for c in validated if c["qc_passed"])
    warning_issues = sum(
        1 for c in validated
        if c["chunk_type"] == "warning" and not c["qc_passed"]
    )
    all_issues_flat = [
        {
            "chunk_index": c["index"],
            "page"       : c.get("page_num", c.get("page_refs", ["?"])[0] if isinstance(c.get("page_refs"), list) else "?"),
            "section"    : c["section_title"],
            "issue"      : issue,
        }
        for c in validated
        for issue in c["qc_issues"]
    ]

    summary = {
        "total_chunks": len(validated),
        "passed": passed,
        "failed": len(validated) - passed,
        "pass_rate": round(passed / max(len(validated), 1) * 100, 1),
        "warning_chunks_with_issues": warning_issues,
        "all_issues": all_issues_flat,
    }

    return validated, summary