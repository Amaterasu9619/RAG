import re
import json
import time
from typing import List, Dict, Optional
from deep_translator import GoogleTranslator

MEDICAL_GLOSSARY = {
    "ECG": {"preserve": True, "note": "Electrocardiogram abbreviation, keep as ECG"},
    "electrocardiogram": {"preserve": False, "translations": {}},
    "electrode": {"preserve": False, "translations": {}},
    "cardiac": {"preserve": False, "translations": {}},
    "arrhythmia": {"preserve": False, "translations": {}},
    "monitoring": {"preserve": False, "translations": {}},
    "contraindication": {"preserve": False, "translations": {}},
    "implantable": {"preserve": False, "translations": {}},
    "defibrillator": {"preserve": False, "translations": {}},
    "pacemaker": {"preserve": False, "translations": {}},
    "tachycardia": {"preserve": False, "translations": {}},
    "bradycardia": {"preserve": False, "translations": {}},
}

LANGUAGE_CODES = {
    "French": "fr",
    "German": "de",
    "Spanish": "es",
    "Italian": "it",
    "Portuguese": "pt",
    "Dutch": "nl",
    "Polish": "pl",
    "Swedish": "sv",
    "Danish": "da",
    "Finnish": "fi",
    "Norwegian": "no",
    "Czech": "cs",
    "Slovak": "sk",
    "Hungarian": "hu",
    "Romanian": "ro",
    "Bulgarian": "bg",
    "Croatian": "hr",
    "Greek": "el",
    "Turkish": "tr",
    "Japanese": "ja",
    "Chinese (Simplified)": "zh-CN",
    "Korean": "ko",
    "Arabic": "ar",
    "Hindi": "hi",
}


def build_claude_prompt(chunk: Dict, target_language: str, glossary: Dict) -> str:
    """Build a precise translation prompt for Claude."""
    glossary_notes = []
    for term, info in glossary.items():
        if info.get("preserve"):
            glossary_notes.append(f'- "{term}": Keep exactly as-is (do not translate)')
    glossary_str = "\n".join(glossary_notes) if glossary_notes else "None"

    chunk_type_instructions = ""
    if chunk["chunk_type"] == "warning":
        chunk_type_instructions = (
            "CRITICAL: This is a SAFETY WARNING. Preserve all safety-critical language. "
            "Do not omit or soften any warning content. Maintain the WARNING label in the target language."
        )
    elif chunk["chunk_type"] == "table":
        chunk_type_instructions = (
            "This is a TABLE. Preserve the HTML table structure exactly. Only translate cell content."
        )
    elif chunk["chunk_type"] == "section":
        chunk_type_instructions = "This is a section heading. Translate it accurately."

    return f"""You are a certified medical device document translator specializing in IFU (Instructions For Use) documents.

Translate the following IFU content from English to {target_language}.

RULES:
1. Preserve ALL HTML tags exactly — only translate text content between tags
2. <img> tags must be copied completely unchanged — do NOT translate or alter src, alt, or any attribute
3. Keep these terms unchanged: {glossary_str}
4. Use formal, regulatory-grade language appropriate for medical device documentation
5. Do NOT add, remove, or paraphrase any content — translate faithfully
6. {chunk_type_instructions}
7. Section context: "{chunk['section_title']}"

INPUT HTML:
{chunk['html']}

Return ONLY the translated HTML with no explanation, preamble, or markdown fences."""


def translate_with_claude(
    chunk: Dict,
    target_language: str,
    api_key: str,
    glossary: Dict,
    model: str = "claude-haiku-4-5-20251001",
) -> Dict:
    """Translate a chunk using Claude API."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("The anthropic package is not installed. Run: pip install anthropic")
    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_claude_prompt(chunk, target_language, glossary)

    start = time.time()
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - start

    translated_html = message.content[0].text.strip()
    # Strip any accidental markdown fences
    translated_html = re.sub(r"^```[a-z]*\n?", "", translated_html)
    translated_html = re.sub(r"\n?```$", "", translated_html)

    return {
        **chunk,
        "translated_html": translated_html,
        "target_language": target_language,
        "translation_method": "claude",
        "model_used": model,
        "latency_s": round(elapsed, 2),
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }


def translate_with_google(chunk: Dict, target_language: str) -> Dict:
    """Translate a chunk using Google Translate (deep-translator)."""
    lang_code = LANGUAGE_CODES.get(target_language, "fr")
    html = chunk["html"]
    tag_pattern = re.compile(r"(<[^>]+>)")
    parts = tag_pattern.split(html)

    translated_parts = []
    translator = GoogleTranslator(source="en", target=lang_code)

    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            translated_parts.append(part)
        elif part.strip():
            try:
                translated = translator.translate(part.strip())
                leading = len(part) - len(part.lstrip())
                trailing = len(part) - len(part.rstrip())
                translated_parts.append(
                    part[:leading] + (translated or part.strip()) + part[len(part) - trailing :]
                    if trailing > 0
                    else part[:leading] + (translated or part.strip())
                )
            except Exception:
                translated_parts.append(part)
        else:
            translated_parts.append(part)

    translated_html = "".join(translated_parts)

    return {
        **chunk,
        "translated_html": translated_html,
        "target_language": target_language,
        "translation_method": "google",
        "model_used": "google-translate",
        "latency_s": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def translate_chunks(
    chunks: List[Dict],
    target_language: str,
    method: str = "claude",
    api_key: Optional[str] = None,
    glossary: Optional[Dict] = None,
    progress_callback=None,
) -> List[Dict]:
    if glossary is None:
        glossary = MEDICAL_GLOSSARY

    results = []
    total = len(chunks)

    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(i, total, chunk)

        try:
            if method == "claude" and api_key:
                result = translate_with_claude(chunk, target_language, api_key, glossary)
            else:
                result = translate_with_google(chunk, target_language)
        except Exception as e:
            # Fallback to google on error
            try:
                result = translate_with_google(chunk, target_language)
                result["fallback_error"] = str(e)
            except Exception as e2:
                result = {
                    **chunk,
                    "translated_html": chunk["html"],
                    "target_language": target_language,
                    "translation_method": "failed",
                    "error": str(e2),
                }

        results.append(result)

    if progress_callback:
        progress_callback(total, total, None)

    return results


def combine_translated_chunks(translated_chunks: List[Dict], original_metadata: Dict) -> str:
    if not translated_chunks:
        return ""

    lang  = translated_chunks[0]["target_language"]
    title = original_metadata.get("title", "IFU Document")
    from collections import OrderedDict
    pages: OrderedDict = OrderedDict()
    for chunk in translated_chunks:
        pnum = str(chunk.get("page_num", "1"))
        if pnum not in pages:
            pages[pnum] = []
        pages[pnum].append(chunk)

    body_parts = []
    for pnum, page_chunks in pages.items():
        body_parts.append(f'<div class="page" data-page="{pnum}">')
        for chunk in page_chunks:
            html = chunk.get("translated_html", chunk.get("html", ""))
            body_parts.append(
                f'<div data-index="{chunk["index"]}" data-type="{chunk["chunk_type"]}">' + html + "</div>"
            )
        body_parts.append("</div>") 

    return (
        '<!DOCTYPE html>\n'
        f'<html lang="{LANGUAGE_CODES.get(lang, "en")}">\n'
        f'<head><meta charset="UTF-8"><title>{title} - {lang}</title></head>\n'
        '<body>\n'
        + "\n".join(body_parts)
        + "\n</body>\n</html>"
    )