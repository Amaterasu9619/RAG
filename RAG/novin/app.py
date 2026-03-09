import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import json
import time
import tempfile
import os
from pathlib import Path

st.set_page_config(
    page_title="IFU AI Translator",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}

.stApp {
    background: #0d1117;
    color: #e6edf3;
}

h1, h2, h3 { font-family: 'IBM Plex Mono', monospace; }

.main-header {
    background: linear-gradient(135deg, #1a2332 0%, #0d1f2d 100%);
    border: 1px solid #2D6A4F;
    border-radius: 8px;
    padding: 28px 36px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
}

.main-header::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, #2D6A4F, #0077B6, #6A4C93);
}

.main-header h1 {
    font-family: 'IBM Plex Mono', monospace;
    color: #58a6ff;
    font-size: 1.8rem;
    margin: 0 0 6px 0;
    letter-spacing: -0.5px;
}

.main-header p {
    color: #8b949e;
    font-size: 0.9rem;
    margin: 0;
}

.metric-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 16px;
    text-align: center;
}

.metric-card .val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 2rem;
    font-weight: 600;
    color: #58a6ff;
}

.metric-card .label {
    font-size: 0.75rem;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 4px;
}

.chunk-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 12px 16px;
    margin: 6px 0;
    font-size: 0.85rem;
}

.chunk-warning {
    border-left: 4px solid #e63946;
    background: #1f1115;
}

.chunk-section {
    border-left: 4px solid #58a6ff;
}

.chunk-table {
    border-left: 4px solid #f7b731;
    background: #1a1910;
}

.chunk-body {
    border-left: 4px solid #2D6A4F;
}

.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.7rem;
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 600;
    letter-spacing: 0.5px;
}

.badge-warning { background: #3d1a1c; color: #e63946; }
.badge-section { background: #1a2a3d; color: #58a6ff; }
.badge-table { background: #2d2710; color: #f7b731; }
.badge-body { background: #1a2d1a; color: #3fb950; }

.qc-pass { color: #3fb950; }
.qc-fail { color: #e63946; }

.step-indicator {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    background: #161b22;
    border-radius: 6px;
    margin: 4px 0;
    border: 1px solid #30363d;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
}

.step-indicator.active { border-color: #58a6ff; background: #1a2332; }
.step-indicator.done { border-color: #2D6A4F; background: #1a2d1a; }
.step-indicator.pending { opacity: 0.5; }

[data-testid="stSidebar"] {
    background: #161b22;
    border-right: 1px solid #30363d;
}

.stButton > button {
    background: linear-gradient(135deg, #2D6A4F, #1B4332);
    color: white;
    border: none;
    border-radius: 6px;
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 600;
    padding: 10px 24px;
    width: 100%;
    transition: opacity 0.2s;
}

.stButton > button:hover { opacity: 0.85; }

.stSelectbox, .stTextInput { font-family: 'IBM Plex Mono', monospace; }

div[data-testid="stExpander"] {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
}
</style>
""", unsafe_allow_html=True)



st.markdown("""
<div class="main-header">
  <h1>🏥 IFU AI Translation System</h1>
  <p>Medical device Instructions For Use — AI-powered multilingual translation with quality control</p>
</div>
""", unsafe_allow_html=True)



with st.sidebar:
    st.markdown("### ⚙️ Configuration")

    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        placeholder="sk-ant-...",
        help="Required for Claude translation. Leave empty to use Google Translate.",
    )

    translation_method = st.radio(
        "Translation Engine",
        ["Claude (High Accuracy)", "Google Translate (Fast/Free)"],
        help="Claude uses medical-grade prompting. Google is free but less accurate.",
    )
    use_claude = translation_method.startswith("Claude")

    from modules.translator import LANGUAGE_CODES
    all_languages = list(LANGUAGE_CODES.keys())
    selected_languages = st.multiselect(
        "Target Languages",
        all_languages,
        default=["French", "German", "Spanish"],
        help="Select languages to translate into",
    )

    st.markdown("---")
    st.markdown("### 📊 Pipeline Steps")
    st.markdown("""
    1. **Ingest PDF** — PyMuPDF extraction  
    2. **Convert to HTML** — layout preservation  
    3. **Chunk** — section-aware splitting  
    4. **Translate** — parallel per chunk  
    5. **QC Validate** — safety checks  
    6. **Export PDF** — WeasyPrint / ReportLab
    """)

    st.markdown("---")
    st.markdown("""
    <div style="font-size:0.75rem;color:#8b949e;font-family:'IBM Plex Mono',monospace;">
    Runs locally on macOS<br>
    PyMuPDF · Anthropic · deep-translator<br>
    WeasyPrint · BeautifulSoup
    </div>
    """, unsafe_allow_html=True)



tab1, tab2, tab3 = st.tabs([
    "📄 Translate IFU",
    "🔬 QC Report",
    "📥 Download",
])



with tab1:
    st.markdown("#### Upload IFU Document")

    uploaded_file = st.file_uploader(
        "Upload PDF (readable, no OCR required)",
        type=["pdf"],
        help="Upload an IFU PDF. Scanned docs require OCR (AWS Textract) not included in this local demo.",
    )

    if uploaded_file is not None:

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name

        if not selected_languages:
            st.warning("⚠️ Please select at least one target language in the sidebar.")
        elif use_claude and not api_key:
            st.warning("⚠️ Please enter your Anthropic API key in the sidebar, or switch to Google Translate.")
        else:
            if st.button("🚀 Run Translation Pipeline"):
                progress_area = st.container()

                with progress_area:
                   
                    st.markdown("""<div class="step-indicator active">⏳ Step 1/5 — Ingesting PDF...</div>""", unsafe_allow_html=True)
                    prog = st.progress(0)

                    from modules.pdf_ingestion import ingest_pdf
                   
                    ingested = ingest_pdf(tmp_path, original_filename=uploaded_file.name)
                    st.session_state["ingested"] = ingested

                    prog.progress(20)
                    st.markdown(f"""<div class="step-indicator done">✅ Step 1/5 — Ingested {ingested['page_count']} pages → HTML</div>""", unsafe_allow_html=True)

                    
                    st.markdown("""<div class="step-indicator active">⏳ Step 2/5 — Chunking document...</div>""", unsafe_allow_html=True)

                    from modules.chunker import chunk_html_by_sections, get_chunk_summary
                    chunks = chunk_html_by_sections(ingested["full_html"])
                    summary = get_chunk_summary(chunks)
                    st.session_state["chunks"] = chunks
                    st.session_state["chunk_summary"] = summary

                    prog.progress(35)
                    st.markdown(f"""<div class="step-indicator done">✅ Step 2/5 — {summary['total_chunks']} chunks created ({summary['by_type']})</div>""", unsafe_allow_html=True)

                    
                    all_translated = {}
                    total_langs = len(selected_languages)

                    from modules.translator import translate_chunks, combine_translated_chunks

                    for lang_idx, lang in enumerate(selected_languages):
                        st.markdown(f"""<div class="step-indicator active">⏳ Step 3/5 — Translating to {lang} ({lang_idx+1}/{total_langs})...</div>""", unsafe_allow_html=True)
                        chunk_prog = st.progress(0)

                        def cb(current, total, chunk_info, _p=chunk_prog):
                            _p.progress(int(current / max(total, 1) * 100))

                        translated = translate_chunks(
                            chunks,
                            target_language=lang,
                            method="claude" if use_claude else "google",
                            api_key=api_key if use_claude else None,
                            progress_callback=cb,
                        )
                        combined_html = combine_translated_chunks(translated, ingested["metadata"])
                        all_translated[lang] = {
                            "chunks": translated,
                            "combined_html": combined_html,
                        }

                    st.session_state["all_translated"] = all_translated
                    prog.progress(70)
                    st.markdown(f"""<div class="step-indicator done">✅ Step 3/5 — Translated to {total_langs} languages</div>""", unsafe_allow_html=True)

                    
                    st.markdown("""<div class="step-indicator active">⏳ Step 4/5 — Running quality control...</div>""", unsafe_allow_html=True)

                    from modules.quality_control import validate_all_chunks
                    all_qc = {}
                    for lang, data in all_translated.items():
                        validated_chunks, qc_summary = validate_all_chunks(data["chunks"])
                        all_qc[lang] = {"chunks": validated_chunks, "summary": qc_summary}

                    st.session_state["all_qc"] = all_qc
                    prog.progress(90)
                    st.markdown("""<div class="step-indicator done">✅ Step 4/5 — QC complete</div>""", unsafe_allow_html=True)

                   
                    st.markdown("""<div class="step-indicator active">⏳ Step 5/5 — Exporting PDFs...</div>""", unsafe_allow_html=True)

                    from modules.exporter import export_to_pdf
                    all_pdfs = {}
                    for lang, data in all_translated.items():
                        pdf_bytes = export_to_pdf(data["combined_html"])
                        all_pdfs[lang] = pdf_bytes

                    st.session_state["all_pdfs"] = all_pdfs
                    prog.progress(100)
                    st.markdown("""<div class="step-indicator done">✅ Step 5/5 — Export complete</div>""", unsafe_allow_html=True)
                    st.success("🎉 Pipeline complete! Check the QC Report and Download tabs.")

        
        if "chunks" in st.session_state:
            chunks = st.session_state["chunks"]
            summary = st.session_state["chunk_summary"]

            st.markdown("---")
            st.markdown("#### Chunk Analysis")

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(f'<div class="metric-card"><div class="val">{summary["total_chunks"]}</div><div class="label">Total Chunks</div></div>', unsafe_allow_html=True)
            with c2:
                st.markdown(f'<div class="metric-card"><div class="val">{summary["by_type"].get("warning", 0)}</div><div class="label">Warning Chunks</div></div>', unsafe_allow_html=True)
            with c3:
                st.markdown(f'<div class="metric-card"><div class="val">{summary["by_type"].get("table", 0)}</div><div class="label">Table Chunks</div></div>', unsafe_allow_html=True)
            with c4:
                st.markdown(f'<div class="metric-card"><div class="val">{summary["avg_chars"]}</div><div class="label">Avg Chars/Chunk</div></div>', unsafe_allow_html=True)

            st.markdown("#### Chunks Preview")
            type_colors = {"warning": "chunk-warning", "section": "chunk-section", "table": "chunk-table", "body": "chunk-body"}
            badge_colors = {"warning": "badge-warning", "section": "badge-section", "table": "badge-table", "body": "badge-body"}

            for chunk in chunks[:20]:
                ctype = chunk["chunk_type"]
                card_class = type_colors.get(ctype, "chunk-body")
                badge_class = badge_colors.get(ctype, "badge-body")
                preview = chunk["text"][:120].replace("<", "&lt;").replace(">", "&gt;")
                st.markdown(f"""
                <div class="chunk-card {card_class}">
                  <span class="badge {badge_class}">{ctype.upper()}</span>
                  <span style="color:#8b949e;font-size:0.75rem;margin-left:8px;">#{chunk['index']} · {chunk['section_title'][:40]} · {chunk['char_count']} chars</span>
                  <div style="color:#cdd9e5;margin-top:6px;font-family:'IBM Plex Mono',monospace;font-size:0.8rem;">{preview}…</div>
                </div>
                """, unsafe_allow_html=True)

            if len(chunks) > 20:
                st.caption(f"Showing first 20 of {len(chunks)} chunks")



with tab2:
    if "all_qc" not in st.session_state:
        st.info("Run the translation pipeline first.")
    else:
        all_qc = st.session_state["all_qc"]
        st.markdown("#### Quality Control Report")

        for lang, qc_data in all_qc.items():
            summary = qc_data["summary"]
            pass_rate = summary["pass_rate"]
            color = "#3fb950" if pass_rate >= 90 else "#f7b731" if pass_rate >= 70 else "#e63946"

            with st.expander(f"🌍 {lang} — Pass Rate: {pass_rate}%", expanded=pass_rate < 90):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown(f'<div class="metric-card"><div class="val" style="color:{color}">{pass_rate}%</div><div class="label">Pass Rate</div></div>', unsafe_allow_html=True)
                with c2:
                    st.markdown(f'<div class="metric-card"><div class="val" style="color:#3fb950">{summary["passed"]}</div><div class="label">Passed</div></div>', unsafe_allow_html=True)
                with c3:
                    st.markdown(f'<div class="metric-card"><div class="val" style="color:#e63946">{summary["failed"]}</div><div class="label">Failed</div></div>', unsafe_allow_html=True)
                with c4:
                    st.markdown(f'<div class="metric-card"><div class="val" style="color:#f7b731">{summary["warning_chunks_with_issues"]}</div><div class="label">Warning Issues</div></div>', unsafe_allow_html=True)

                if summary["all_issues"]:
                    st.markdown("**Issues Detected:**")
                    for issue in summary["all_issues"][:15]:
                        pg = issue.get("page", "?")
                        st.markdown(f"""
                        <div style="background:#1f1115;border-left:3px solid #e63946;padding:8px 12px;margin:4px 0;border-radius:4px;font-size:0.82rem;font-family:'IBM Plex Mono',monospace;">
                          <span style="color:#8b949e;">Chunk #{issue['chunk_index']} · Page {pg} · {issue['section'][:30]}</span><br>
                          <span style="color:#e63946;">⚠ {issue['issue']}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.success("✅ All chunks passed quality control.")

with tab3:
    if "all_pdfs" not in st.session_state:
        st.info("Run the translation pipeline first.")
    else:
        all_pdfs = st.session_state["all_pdfs"]
        all_translated = st.session_state["all_translated"]
        ingested = st.session_state["ingested"]

        st.markdown("#### Download Translated Documents")
        st.markdown("Download each translated IFU as PDF or HTML.")

        for lang, pdf_bytes in all_pdfs.items():
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                qc = st.session_state["all_qc"].get(lang, {}).get("summary", {})
                pass_rate = qc.get("pass_rate", "—")
                color = "#3fb950" if isinstance(pass_rate, float) and pass_rate >= 90 else "#f7b731"
                st.markdown(f"""
                <div style="padding:12px 0;">
                  <span style="font-size:1rem;font-weight:600;">{lang}</span>
                  <span style="color:{color};font-family:'IBM Plex Mono',monospace;font-size:0.8rem;margin-left:12px;">QC: {pass_rate}%</span>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                safe_lang = lang.replace(" ", "_").replace("(", "").replace(")", "")
                doc_title = ingested["metadata"]["title"] or "IFU"
                st.download_button(
                    label="⬇ Download PDF",
                    data=pdf_bytes,
                    file_name=f"{doc_title}_{safe_lang}.pdf",
                    mime="application/pdf",
                    key=f"pdf_{lang}",
                )
            with col3:
                html_content = all_translated[lang]["combined_html"]
                st.download_button(
                    label="⬇ Download HTML",
                    data=html_content.encode("utf-8"),
                    file_name=f"{doc_title}_{safe_lang}.html",
                    mime="text/html",
                    key=f"html_{lang}",
                )

        st.markdown("---")
        st.markdown("#### Translation Summary")
        rows = []
        for lang in all_pdfs.keys():
            chunks = st.session_state["all_translated"][lang]["chunks"]
            qc_sum = st.session_state["all_qc"].get(lang, {}).get("summary", {})
            methods = set(c.get("translation_method", "?") for c in chunks)
            rows.append({
                "Language": lang,
                "Chunks": len(chunks),
                "Method": ", ".join(methods),
                "QC Pass Rate": f"{qc_sum.get('pass_rate', '?')}%",
                "Warning Issues": qc_sum.get("warning_chunks_with_issues", 0),
            })

        import pandas as pd
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

if "tmp_path" in dir() and os.path.exists(tmp_path):
    try:
        os.unlink(tmp_path)
    except Exception:
        pass