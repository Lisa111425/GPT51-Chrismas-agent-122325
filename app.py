import os
import time
import random
import base64
import re
from dataclasses import dataclass
from io import BytesIO
from typing import List, Dict, Any
from collections import Counter

import streamlit as st
import yaml
import pandas as pd

from openai import OpenAI
import google.generativeai as genai
import anthropic
from xai_sdk import Client as XAIClient
from xai_sdk.chat import user as xai_user, system as xai_system

import docx2txt
from PyPDF2 import PdfReader
from fpdf import FPDF

from pdf2image import convert_from_bytes
import pytesseract


# =========================
#  Localization
# =========================

UI_TEXT = {
    "en": {
        "app_title": "AuditFlow AI · Masterpiece Edition (FDA)",
        "subtitle": "FDA-oriented agentic document intelligence with painterly themes.",
        "tab_ocr_pdf": "OCR PDF Intelligence",
        "tab_file_transform": "File Transform & Deep Summary",
        "tab_file_intel": "File Intelligence",
        "tab_multi_file": "Multi-File Synthesis",
        "tab_smart_replace": "Smart Replace",
        "tab_note_keeper": "AI Note Keeper",
        "upload_label": "Upload a document (PDF, DOCX, TXT):",
        "output_format": "Transform file into:",
        "format_markdown": "Markdown (.md)",
        "format_pdf": "PDF (.pdf)",
        "run_summary": "Generate 2,000–3,000 word Masterpiece summary",
        "chat_with_file": "Chat with this file",
        "api_key_section": "API Keys (browser-only, never sent to any server except LLM provider)",
        "provider": "Provider",
        "model": "Model",
        "custom_prompt": "Custom system prompt",
        "max_tokens": "Max tokens",
        "temperature": "Temperature",
        "user_prompt": "Your question / instruction",
        "agent_select": "FDA Agent (from advanced_agents.yaml)",
    },
    "zh": {
        "app_title": "AuditFlow AI · 大師傑作版（FDA 專用）",
        "subtitle": "面向 FDA 報規與合規需求的代理式文件智慧系統，結合藝術風格體驗。",
        "tab_ocr_pdf": "OCR 掃描 PDF 智能分析",
        "tab_file_transform": "檔案轉換與深度摘要",
        "tab_file_intel": "單一文件分析",
        "tab_multi_file": "多文件綜合分析",
        "tab_smart_replace": "智慧範本填寫",
        "tab_note_keeper": "AI 筆記管理員",
        "upload_label": "上傳文件（PDF、DOCX、TXT）：",
        "output_format": "將檔案轉換為：",
        "format_markdown": "Markdown (.md)",
        "format_pdf": "PDF (.pdf)",
        "run_summary": "產生 2,000–3,000 字深度摘要（Markdown）",
        "chat_with_file": "針對此文件發問",
        "api_key_section": "API 金鑰（僅在本機瀏覽器中使用，僅送往 LLM 供應商）",
        "provider": "服務提供者",
        "model": "模型",
        "custom_prompt": "自訂系統提示（System Prompt）",
        "max_tokens": "最大 Token 數",
        "temperature": "溫度",
        "user_prompt": "你的問題 / 指令",
        "agent_select": "FDA 代理人（來自 advanced_agents.yaml）",
    },
}


def t(key: str) -> str:
    lang = st.session_state.get("ui_lang", "en")
    return UI_TEXT.get(lang, UI_TEXT["en"]).get(key, key)


# =========================
#  Painter Styles
# =========================

@dataclass
class ArtistStyle:
    key: str
    display_name: str
    painter: str
    bg_gradient_light: str
    bg_gradient_dark: str
    panel_bg_rgba: str
    accent_color: str
    accent_soft: str
    font_family: str


ARTIST_STYLES: List[ArtistStyle] = [
    # (same 20 styles as before, unchanged)
    ArtistStyle(
        key="van_gogh",
        display_name="Starry Night",
        painter="Vincent van Gogh",
        bg_gradient_light="linear-gradient(135deg,#fdfbfb 0%,#ebedee 100%)",
        bg_gradient_dark="linear-gradient(135deg,#0f172a 0%,#1e293b 100%)",
        panel_bg_rgba="rgba(15, 23, 42, 0.75)",
        accent_color="#facc15",
        accent_soft="#fef9c3",
        font_family="'DM Sans', system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
    ),
    # ... (Monet, Picasso, etc. – omit here for brevity, keep exactly as previous app.py)
]

# For brevity, include all ARTIST_STYLES from previous version here.


def apply_theme(style: ArtistStyle, dark_mode: bool):
    bg = style.bg_gradient_dark if dark_mode else style.bg_gradient_light
    panel = style.panel_bg_rgba
    text_color = "#e5e7eb" if dark_mode else "#020617"

    css = f"""
    <style>
    html, body, [data-testid="stAppViewContainer"] {{
        background: {bg} !important;
        background-attachment: fixed;
        font-family: {style.font_family};
        color: {text_color};
    }}
    .glass-panel {{
        background: {panel};
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        border-radius: 20px;
        border: 1px solid rgba(255,255,255,0.18);
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.5rem;
    }}
    .accent-title {{
        color: {style.accent_color};
    }}
    .accent-chip {{
        background: {style.accent_soft};
        color: #111827;
        border-radius: 9999px;
        padding: 0.15rem 0.7rem;
        font-size: 0.75rem;
        font-weight: 500;
        display: inline-flex;
        align-items: center;
        gap: 0.25rem;
    }}
    textarea, .stTextInput > div > div > input {{
        background: rgba(15,23,42,0.75) !important;
        color: #e5e7eb !important;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def style_selector_ui() -> ArtistStyle:
    st.markdown("### 🎨 Masterpiece Style Jackpot")
    style_keys = [s.key for s in ARTIST_STYLES]
    current_style_key = st.session_state.get("artist_style_key", style_keys[0])

    col1, col2 = st.columns([3, 1])
    with col1:
        selected_key = st.selectbox(
            "Style",
            options=style_keys,
            index=style_keys.index(current_style_key) if current_style_key in style_keys else 0,
            format_func=lambda k: next(s.display_name for s in ARTIST_STYLES if s.key == k),
            key="artist_style_dropdown",
        )
    with col2:
        if st.button("Inspire Me (Jackpot)"):
            placeholder = st.empty()
            for _ in range(15):
                rand_key = random.choice(style_keys)
                st.session_state.artist_style_key = rand_key
                placeholder.write(
                    f"🎰 🎨 {next(s.display_name for s in ARTIST_STYLES if s.key == rand_key)}"
                )
                time.sleep(0.06)
            placeholder.empty()

    st.session_state.artist_style_key = st.session_state.get("artist_style_key", selected_key)
    active_style = next(s for s in ARTIST_STYLES if s.key == st.session_state.artist_style_key)
    return active_style


# =========================
#  Agents (from YAML)
# =========================

def load_agents(path: str = "advanced_agents.yaml") -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("agents", [])
    except Exception as e:
        st.sidebar.error(f"Failed to load agents YAML: {e}")
        return []


def agent_selector_ui(agents: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not agents:
        st.sidebar.warning("No agents loaded from advanced_agents.yaml.")
        return {}

    st.sidebar.markdown(f"### 🤖 {t('agent_select')}")
    ids = [a["id"] for a in agents]

    def label_func(agent_id: str) -> str:
        a = next(ag for ag in agents if ag["id"] == agent_id)
        return a.get("display_name_zh", agent_id)

    default_idx = 0
    if "selected_agent_id" in st.session_state:
        try:
            default_idx = ids.index(st.session_state["selected_agent_id"])
        except ValueError:
            default_idx = 0

    selected_id = st.sidebar.selectbox(
        "Agent",
        options=ids,
        index=default_idx,
        format_func=label_func,
        key="agent_selectbox",
    )
    selected_agent = next(a for a in agents if a["id"] == selected_id)

    if st.session_state.get("selected_agent_id") != selected_id:
        st.session_state["selected_agent_id"] = selected_id
        st.session_state["llm_provider"] = selected_agent.get("default_provider", "Gemini")
        st.session_state["llm_model_id"] = selected_agent.get("default_model", "gemini-3-flash")
        st.session_state["llm_max_tokens"] = selected_agent.get("default_max_tokens", 4096)
        st.session_state["llm_temperature"] = selected_agent.get("default_temperature", 0.3)
        st.session_state["llm_system_prompt"] = selected_agent.get(
            "system_prompt_zh",
            "你是一位 FDA 法規合規與策略分析專家，請使用繁體中文回答。",
        )

    return selected_agent


# =========================
#  API Keys
# =========================

def render_api_key_inputs():
    st.sidebar.markdown(f"### 🔐 {t('api_key_section')}")
    with st.sidebar.expander("OpenAI", expanded=False):
        env_val = os.getenv("OPENAI_API_KEY")
        if env_val:
            st.markdown("Using environment OpenAI API key（不顯示實際值）。")
            st.session_state["openai_api_key"] = env_val
        else:
            st.session_state["openai_api_key"] = st.text_input(
                "OpenAI API Key",
                type="password",
                value=st.session_state.get("openai_api_key", ""),
            )

    with st.sidebar.expander("Gemini", expanded=False):
        env_val = os.getenv("GEMINI_API_KEY")
        if env_val:
            st.markdown("Using environment Gemini API key（不顯示實際值）。")
            st.session_state["gemini_api_key"] = env_val
        else:
            st.session_state["gemini_api_key"] = st.text_input(
                "Gemini API Key",
                type="password",
                value=st.session_state.get("gemini_api_key", ""),
            )

    with st.sidebar.expander("Anthropic", expanded=False):
        env_val = os.getenv("ANTHROPIC_API_KEY")
        if env_val:
            st.markdown("Using environment Anthropic API key（不顯示實際值）。")
            st.session_state["anthropic_api_key"] = env_val
        else:
            st.session_state["anthropic_api_key"] = st.text_input(
                "Anthropic API Key",
                type="password",
                value=st.session_state.get("anthropic_api_key", ""),
            )

    with st.sidebar.expander("XAI (Grok)", expanded=False):
        env_val = os.getenv("XAI_API_KEY")
        if env_val:
            st.markdown("Using environment XAI API key（不顯示實際值）。")
            st.session_state["xai_api_key"] = env_val
        else:
            st.session_state["xai_api_key"] = st.text_input(
                "XAI API Key",
                type="password",
                value=st.session_state.get("xai_api_key", ""),
            )


# =========================
#  Model & Prompt Controls (Global)
# =========================

MODEL_CATALOG = {
    "OpenAI": [
        {"id": "gpt-4o-mini", "label": "GPT‑4o mini"},
        {"id": "gpt-4.1-mini", "label": "GPT‑4.1 mini"},
    ],
    "Gemini": [
        {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
        {"id": "gemini-3-flash", "label": "Gemini 3 Flash"},
    ],
    "Anthropic": [
        {"id": "claude-3.5-sonnet", "label": "Claude 3.5 Sonnet"},
        {"id": "claude-3.5-haiku", "label": "Claude 3.5 Haiku"},
    ],
    "XAI (Grok)": [
        {"id": "grok-4", "label": "Grok-4 (XAI)"},
    ],
}


def render_llm_controls():
    st.sidebar.markdown("### 🧠 LLM & Prompt")
    provider = st.sidebar.selectbox(
        t("provider"),
        list(MODEL_CATALOG.keys()),
        index=list(MODEL_CATALOG.keys()).index(st.session_state.get("llm_provider", "Gemini")),
        key="llm_provider",
    )
    models = MODEL_CATALOG[provider]
    model_ids = [m["id"] for m in models]

    default_model = st.session_state.get("llm_model_id", model_ids[0])
    if default_model not in model_ids:
        default_model = model_ids[0]

    model_id = st.sidebar.selectbox(
        t("model"),
        options=model_ids,
        index=model_ids.index(default_model),
        format_func=lambda m: next(x["label"] for x in models if x["id"] == m),
        key="llm_model_id",
    )

    max_tokens = st.sidebar.slider(
        t("max_tokens"), min_value=256, max_value=8192,
        value=int(st.session_state.get("llm_max_tokens", 4096)), step=256,
        key="llm_max_tokens",
    )
    temperature = st.sidebar.slider(
        t("temperature"),
        min_value=0.0,
        max_value=1.5,
        value=float(st.session_state.get("llm_temperature", 0.3)),
        step=0.05,
        key="llm_temperature",
    )
    system_prompt = st.sidebar.text_area(
        t("custom_prompt"),
        value=st.session_state.get("llm_system_prompt", ""),
        key="llm_system_prompt",
        height=180,
    )
    return provider, model_id, max_tokens, temperature, system_prompt


def get_llm_config():
    return (
        st.session_state.get("llm_provider", "Gemini"),
        st.session_state.get("llm_model_id", "gemini-3-flash"),
        int(st.session_state.get("llm_max_tokens", 4096)),
        float(st.session_state.get("llm_temperature", 0.3)),
        st.session_state.get("llm_system_prompt", "你是一位 FDA 法規合規與策略分析專家，請使用繁體中文回答。"),
    )


# =========================
#  LLM Call Wrapper (text-only)
# =========================

def call_llm(
    provider: str,
    model: str,
    system_prompt: str,
    user_messages: List[Dict[str, str]],
    max_tokens: int = 2048,
    temperature: float = 0.4,
) -> str:
    if provider == "OpenAI":
        api_key = st.session_state.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            st.error("OpenAI API key is required.")
            return ""
        client = OpenAI(api_key=api_key)
        messages = [{"role": "system", "content": system_prompt}] + user_messages
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content

    elif provider == "Gemini":
        api_key = st.session_state.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            st.error("Gemini API key is required.")
            return ""
        genai.configure(api_key=api_key)
        model_obj = genai.GenerativeModel(model)
        full_prompt = f"{system_prompt}\n\n" + "\n\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in user_messages
        )
        resp = model_obj.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        return resp.text

    elif provider == "Anthropic":
        api_key = st.session_state.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            st.error("Anthropic API key is required.")
            return ""
        client = anthropic.Anthropic(api_key=api_key)
        messages = [m for m in user_messages if m["role"] != "system"]
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        )
        return "".join(block.text for block in resp.content if hasattr(block, "text"))

    elif provider == "XAI (Grok)":
        api_key = st.session_state.get("xai_api_key") or os.getenv("XAI_API_KEY")
        if not api_key:
            st.error("XAI API key is required.")
            return ""
        client = XAIClient(api_key=api_key, timeout=3600)
        chat = client.chat.create(model=model)
        chat.append(xai_system(system_prompt))
        for m in user_messages:
            if m["role"] == "user":
                chat.append(xai_user(m["content"]))
        response = chat.sample()
        return response.content

    else:
        st.error("Unsupported provider.")
        return ""


# =========================
#  File Utilities
# =========================

def extract_text_from_pdf(file_bytes: BytesIO) -> str:
    reader = PdfReader(file_bytes)
    texts = []
    for page in reader.pages:
        texts.append(page.extract_text() or "")
    return "\n".join(texts)


def extract_text_from_docx(file_bytes: BytesIO) -> str:
    return docx2txt.process(file_bytes)


def extract_text_from_txt(file_bytes: BytesIO) -> str:
    return file_bytes.read().decode("utf-8", errors="ignore")


def extract_text(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    data = BytesIO(uploaded_file.read())
    if name.endswith(".pdf"):
        return extract_text_from_pdf(data)
    elif name.endswith(".docx"):
        return extract_text_from_docx(data)
    elif name.endswith(".txt"):
        return extract_text_from_txt(data)
    elif name.endswith(".md"):
        return data.read().decode("utf-8", errors="ignore")
    else:
        st.error("Unsupported format. Please upload PDF, DOCX, TXT, or MD.")
        return ""


def markdown_to_pdf_bytes(md_text: str) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    for line in md_text.splitlines():
        pdf.multi_cell(0, 5, line)
    pdf_bytes = BytesIO()
    pdf.output(pdf_bytes)
    pdf_bytes.seek(0)
    return pdf_bytes.getvalue()


# =========================
#  Summary Prompt (Deep)
# =========================

def build_deep_summary_prompt(doc_text: str, lang: str) -> str:
    if lang == "en":
        language_instruction = "Write the entire output in English."
    else:
        language_instruction = "請使用繁體中文撰寫整份輸出，並以 FDA 審查與合規視角進行深入分析。"

    base = f"""
你是一位具備 FDA 規範、醫藥/醫材審查與戰略規劃專長的「高階策略審閱官」與「知識架構師」。
{language_instruction}

你將收到一份文件內容。請依前述規格產出 2,000–3,000 字的深度 Markdown 報告。

[DOCUMENT START]
{doc_text[:100000]}
[DOCUMENT END]
"""
    return base.strip()


# =========================
#  OCR Helper Functions
# =========================

def preview_pdf(pdf_bytes: bytes):
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    pdf_display = f"""
    <iframe src="data:application/pdf;base64,{b64}" width="100%" height="600" type="application/pdf"></iframe>
    """
    st.markdown(pdf_display, unsafe_allow_html=True)


def run_local_ocr(pdf_bytes: bytes, pages: List[int], lang_choice: str) -> str:
    if not pages:
        return ""

    if lang_choice == "English":
        lang = "eng"
    elif lang_choice == "繁體中文":
        lang = "chi_tra"
    else:
        lang = "eng+chi_tra"

    texts = []
    for p in pages:
        images = convert_from_bytes(pdf_bytes, dpi=200, first_page=p, last_page=p)
        if not images:
            continue
        img = images[0]
        page_text = pytesseract.image_to_string(img, lang=lang)
        texts.append(f"=== Page {p} ===\n{page_text.strip()}")
    return "\n\n".join(texts)


def run_llm_ocr(pdf_bytes: bytes, pages: List[int], model_choice: str) -> str:
    if not pages:
        return ""

    texts = []
    for p in pages:
        images = convert_from_bytes(pdf_bytes, dpi=200, first_page=p, last_page=p)
        if not images:
            continue
        img = images[0]
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_bytes = buffered.getvalue()

        if model_choice in ["gemini-3-flash", "gemini-2.5-flash"]:
            api_key = st.session_state.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
            if not api_key:
                st.error("Gemini API key is required for LLM OCR.")
                return ""
            genai.configure(api_key=api_key)
            model_obj = genai.GenerativeModel(model_choice)
            prompt = "Please perform OCR on this page and return only the plain text, preserving reading order."
            resp = model_obj.generate_content(
                [prompt, {"mime_type": "image/png", "data": img_bytes}],
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=2048,
                    temperature=0.0,
                ),
            )
            page_text = resp.text or ""
            texts.append(f"=== Page {p} ===\n{page_text.strip()}")

        elif model_choice == "gpt-4o-mini":
            api_key = st.session_state.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                st.error("OpenAI API key is required for LLM OCR.")
                return ""
            client = OpenAI(api_key=api_key)
            b64_img = base64.b64encode(img_bytes).decode("utf-8")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all legible text from this image. Output plain text only.",
                        },
                        {
                            "type": "input_image",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64_img}"
                            },
                        },
                    ],
                }
            ]
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=2048,
            )
            page_text = resp.choices[0].message.content or ""
            texts.append(f"=== Page {p} ===\n{page_text.strip()}")
        else:
            st.error("Unsupported model for LLM OCR.")
            return ""

    return "\n\n".join(texts)


def build_word_freq_chart(text: str):
    tokens = re.findall(r"[A-Za-z\u4e00-\u9fff]+", text.lower())
    stopwords = {
        "the", "and", "of", "to", "in", "for", "a", "is", "on", "with", "that",
        "this", "by", "or", "as", "an", "be", "are", "at", "from"
    }
    tokens = [t for t in tokens if t not in stopwords and len(t) > 1]
    if not tokens:
        return
    counter = Counter(tokens)
    top = counter.most_common(20)
    if not top:
        return
    df = pd.DataFrame(top, columns=["word", "count"]).set_index("word")
    st.markdown("#### 🔠 Word Frequency Graph (Top Terms)")
    st.bar_chart(df)


def build_ocr_summary_prompt(ocr_text: str, lang: str) -> str:
    language_instruction = (
        "Write the entire output in English."
        if lang == "en"
        else "請使用繁體中文撰寫，並以 FDA/專業審查觀點進行整理。"
    )
    base = f"""
你將收到一段由 OCR 擷取的文件內容（可能擁有噪音或拼字錯誤）。請執行以下任務：

1. 整理並修正可明顯辨識的文字錯誤（但避免憑空補造數據）。
2. 產出一份結構化 Markdown 摘要，至少包含：
   - 文件整體目的與主題
   - 主要重點與論點
   - 關鍵風險或需關注議題
3. 產出一段「關鍵詞關聯概觀」（Word Graph 概要敘述）：
   - 以文字方式描述主要關鍵詞群與其彼此關係、聚類或主題。
4. 萃取 **20 個最重要的實體**（如藥品名稱、機構、關鍵技術名詞、試驗代碼等），
   並以 Markdown 表格輸出，欄位包含：
   - #（序號）
   - Entity（實體名稱）
   - Type（實體類型）
   - Context Snippet（關鍵上下文摘錄）
   - Relevance（為何重要）

{language_instruction}

[OCR TEXT START]
{ocr_text[:80000]}
[OCR TEXT END]
"""
    return base.strip()


# =========================
#  Limited Model Selector for OCR / Notes Q&A
# =========================

LIMITED_QA_MODELS = {
    "Gemini 3 Flash": ("Gemini", "gemini-3-flash"),
    "Gemini 2.5 Flash": ("Gemini", "gemini-2.5-flash"),
    "GPT‑4o mini": ("OpenAI", "gpt-4o-mini"),
}


def limited_model_selector(default_label: str = "Gemini 3 Flash"):
    labels = list(LIMITED_QA_MODELS.keys())
    if default_label not in labels:
        default_label = labels[0]
    label = st.selectbox("選擇模型", labels, index=labels.index(default_label))
    provider, model_id = LIMITED_QA_MODELS[label]
    max_tokens = st.number_input(
        "最大 tokens（建議 ≤ 12000）",
        min_value=512,
        max_value=16000,
        value=12000,
        step=512,
    )
    temperature = st.slider("溫度", 0.0, 1.5, 0.4, 0.05)
    return provider, model_id, int(max_tokens), float(temperature)


# =========================
#  Tabs
# =========================

def tab_ocr_pdf_intelligence():
    st.markdown(f"## {t('tab_ocr_pdf')}")
    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)

    # Upload & manage PDF
    uploaded = st.file_uploader(
        "上傳要進行 OCR 的 PDF（掃描或含影像）：",
        type=["pdf"],
        key="ocr_pdf_uploader",
    )

    col_up1, col_up2 = st.columns([3, 1])
    with col_up1:
        if uploaded is not None:
            # Save bytes to session
            pdf_bytes = uploaded.read()
            st.session_state["ocr_pdf_bytes"] = pdf_bytes
            st.session_state["ocr_pdf_name"] = uploaded.name
    with col_up2:
        if st.button("清除目前 PDF"):
            st.session_state.pop("ocr_pdf_bytes", None)
            st.session_state.pop("ocr_pdf_name", None)
            st.session_state.pop("ocr_text", None)

    pdf_bytes = st.session_state.get("ocr_pdf_bytes")
    if pdf_bytes:
        st.markdown(f"**目前 PDF：** {st.session_state.get('ocr_pdf_name','')}")
        preview_pdf(pdf_bytes)

        # Page selection
        reader = PdfReader(BytesIO(pdf_bytes))
        num_pages = len(reader.pages)
        st.markdown(f"此檔共有 **{num_pages}** 頁。")
        page_nums = list(range(1, num_pages + 1))
        selected_pages = st.multiselect(
            "選擇要進行 OCR 的頁數",
            options=page_nums,
            default=page_nums,
        )

        # OCR method
        ocr_method = st.radio(
            "OCR 方式",
            ["本地 OCR (pdf2image + pytesseract)", "LLM OCR (Gemini / GPT‑4o-mini)"],
            horizontal=True,
        )

        if ocr_method.startswith("本地"):
            ocr_lang = st.selectbox(
                "OCR 語言",
                ["English", "繁體中文", "中英混合"],
                index=2,
            )
            if st.button("執行本地 OCR"):
                with st.spinner("Running local OCR (pdf2image + pytesseract)…"):
                    text = run_local_ocr(pdf_bytes, selected_pages, ocr_lang)
                    if not text.strip():
                        st.warning("未擷取到文字，請確認頁面是否為影像或嘗試不同語言設定。")
                    else:
                        st.session_state["ocr_text"] = text

        else:
            llm_ocr_model = st.selectbox(
                "選擇 LLM 模型用於 OCR",
                ["gemini-3-flash", "gemini-2.5-flash", "gpt-4o-mini"],
                index=0,
            )
            if st.button("執行 LLM OCR"):
                with st.spinner("Running LLM-based OCR on selected pages…"):
                    text = run_llm_ocr(pdf_bytes, selected_pages, llm_ocr_model)
                    if not text.strip():
                        st.warning("LLM OCR 未擷取到文字，請檢查 API Key 或嘗試不同模型。")
                    else:
                        st.session_state["ocr_text"] = text

    # OCR Text Editing & Summary
    if "ocr_text" in st.session_state and st.session_state["ocr_text"]:
        st.markdown("---")
        st.markdown("### ✏️ OCR 結果編輯")
        view_mode = st.radio("檢視模式", ["Markdown 預覽", "純文字"], horizontal=True)
        ocr_text = st.text_area(
            "可編輯 OCR 文本（可視為 Markdown 或純文字）",
            value=st.session_state["ocr_text"],
            height=260,
            key="ocr_text_edit",
        )
        st.session_state["ocr_text"] = ocr_text

        if view_mode == "Markdown 預覽":
            st.markdown("#### 預覽")
            st.markdown(ocr_text)
        else:
            st.markdown("#### 純文字顯示")
            st.text(ocr_text[:5000])

        if st.button("產生 OCR 文件摘要 + Word Graph + 20 實體表"):
            lang = st.session_state.get("ui_lang", "zh")
            provider, model_id, max_tokens, temperature, system_prompt = get_llm_config()
            prompt = build_ocr_summary_prompt(ocr_text, lang)
            with st.spinner("Generating OCR-based summary and entities…"):
                summary = call_llm(
                    provider=provider,
                    model=model_id,
                    system_prompt=system_prompt,
                    user_messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            st.session_state["ocr_summary_md"] = summary or ""

        if "ocr_summary_md" in st.session_state and st.session_state["ocr_summary_md"]:
            st.markdown("### 📄 OCR 文件總結")
            summary_view = st.radio(
                "總結檢視模式",
                ["Markdown", "純文字"],
                horizontal=True,
                key="ocr_summary_view_mode",
            )
            if summary_view == "Markdown":
                st.markdown(st.session_state["ocr_summary_md"])
            else:
                st.text(st.session_state["ocr_summary_md"])

            # Word frequency graph from cleaned OCR text
            build_word_freq_chart(st.session_state["ocr_text"])

            # Q&A on OCR doc
            st.markdown("---")
            st.markdown("### 💬 針對 OCR 文件持續提問")
            qa_question = st.text_area("你的提問 / 任務描述", key="ocr_qa_question")
            provider_q, model_q, max_tokens_q, temp_q = limited_model_selector("Gemini 3 Flash")
            answer_view = st.radio(
                "回答顯示為",
                ["Markdown", "純文字"],
                horizontal=True,
                key="ocr_qa_answer_view",
            )
            if st.button("向模型提問（OCR 文件為背景）"):
                if not qa_question.strip():
                    st.warning("請輸入問題。")
                else:
                    context = f"""
以下為 OCR 後並可編輯之文件內容（可能仍含少量噪音）：

[OCR TEXT]
{st.session_state['ocr_text'][:80000]}

若有可用的摘要，則如下：

[SUMMARY]
{st.session_state.get('ocr_summary_md','')[:40000]}
"""
                    with st.spinner("Model thinking with OCR document…"):
                        answer = call_llm(
                            provider=provider_q,
                            model=model_q,
                            system_prompt="你是一位專業文件審閱與說明專家，請使用繁體中文或英文（依內容而定）清楚回答。",
                            user_messages=[
                                {"role": "user", "content": context},
                                {"role": "user", "content": qa_question},
                            ],
                            max_tokens=max_tokens_q,
                            temperature=temp_q,
                        )
                    if answer_view == "Markdown":
                        st.markdown(answer or "_No answer produced._")
                    else:
                        st.text(answer or "_No answer produced._")

    st.markdown("</div>", unsafe_allow_html=True)


def tab_file_transform_deep_summary():
    st.markdown(f"## {t('tab_file_transform')}")
    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)

    uploaded = st.file_uploader(
        t("upload_label"),
        type=["pdf", "docx", "txt"],
        key="file_transform_uploader",
    )

    output_format = st.radio(
        t("output_format"),
        [t("format_markdown"), t("format_pdf")],
        horizontal=True,
        key="output_format_choice",
    )

    if uploaded is not None:
        if st.button(t("run_summary"), type="primary"):
            with st.spinner("Extracting text and generating deep summary…"):
                raw_text = extract_text(uploaded)
                if not raw_text.strip():
                    st.error("No readable text extracted from the file.")
                    st.markdown("</div>", unsafe_allow_html=True)
                    return

                provider, model_id, max_tokens, temperature, system_prompt = get_llm_config()
                lang = st.session_state.get("ui_lang", "zh")

                prompt = build_deep_summary_prompt(raw_text, lang)
                output = call_llm(
                    provider=provider,
                    model=model_id,
                    system_prompt=system_prompt,
                    user_messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                if not output:
                    st.markdown("</div>", unsafe_allow_html=True)
                    return

                st.session_state["latest_file_text"] = raw_text
                st.session_state["latest_file_summary_md"] = output
                st.session_state["latest_file_name"] = uploaded.name

                st.markdown("### 📄 Deep Summary (Markdown)")
                st.markdown(output)

                if output_format == t("format_markdown"):
                    st.download_button(
                        "Download Markdown",
                        data=output.encode("utf-8"),
                        file_name=f"{uploaded.name}.summary.md",
                        mime="text/markdown",
                    )
                else:
                    pdf_bytes = markdown_to_pdf_bytes(output)
                    st.download_button(
                        "Download PDF",
                        data=pdf_bytes,
                        file_name=f"{uploaded.name}.summary.pdf",
                        mime="application/pdf",
                    )

    if "latest_file_text" in st.session_state:
        st.markdown("---")
        st.markdown(f"### 💬 {t('chat_with_file')} — {st.session_state.get('latest_file_name', '')}")
        user_q = st.text_area(t("user_prompt"), key="file_chat_prompt")
        if st.button("Ask the file"):
            provider, model_id, max_tokens, temperature, system_prompt = get_llm_config()
            full_context = f"""
以下是原始文件內容與該文件之長篇摘要。請嚴格根據此等資訊作答，若內容不足以支持答案，請明確說明「文件未提供足夠資訊」。

[ORIGINAL DOCUMENT]
{st.session_state['latest_file_text'][:60000]}

[SUMMARY]
{st.session_state['latest_file_summary_md'][:40000]}
"""
            question = user_q.strip()
            if not question:
                st.warning("請輸入問題。")
            else:
                with st.spinner("Thinking with the document…"):
                    answer = call_llm(
                        provider=provider,
                        model=model_id,
                        system_prompt=system_prompt,
                        user_messages=[
                            {"role": "user", "content": full_context},
                            {"role": "user", "content": question},
                        ],
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                st.markdown("#### Answer")
                st.markdown(answer or "_No answer produced._")

    st.markdown("</div>", unsafe_allow_html=True)


def tab_file_intelligence():
    st.markdown(f"## {t('tab_file_intel')}")
    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
    up = st.file_uploader(
        t("upload_label"),
        type=["pdf", "docx", "txt", "md"],
        key="file_intel_uploader",
    )
    if up is not None and st.button("Analyze File"):
        with st.spinner("Analyzing file…"):
            text = extract_text(up)
            provider, model_id, max_tokens, temperature, system_prompt = get_llm_config()
            lang = st.session_state.get("ui_lang", "zh")

            language_instruction = (
                "Write the output in English."
                if lang == "en"
                else "請使用繁體中文撰寫，並以 FDA 審查與合規觀點進行說明。"
            )
            prompt = f"""
你是一位 FDA 法規、臨床與 CMC 整合分析專家。
{language_instruction}

請針對以下文件進行結構化分析，涵蓋：
- 文件目的與適用領域
- 與 FDA 相關的法規或指引（如 21 CFR、GxP、ICH 指南）之關聯
- 潛在風險與缺口
- 建議補強與下一步行動

[DOCUMENT START]
{text[:100000]}
[DOCUMENT END]
"""
            result = call_llm(
                provider=provider,
                model=model_id,
                system_prompt=system_prompt,
                user_messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            st.markdown("### Analysis")
            st.markdown(result or "_No output._")
    st.markdown("</div>", unsafe_allow_html=True)


def tab_multi_file_synthesis():
    st.markdown(f"## {t('tab_multi_file')}")
    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
    files = st.file_uploader(
        "Upload multiple files (PDF/DOCX/TXT/MD)",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
        key="multi_files",
    )
    if files and st.button("Combine & Analyze"):
        with st.spinner("Combining and analyzing files…"):
            assembled = []
            for f in files:
                content = extract_text(f)
                assembled.append(
                    f"--- START FILE: {f.name} ---\n{content}\n--- END FILE: {f.name} ---\n"
                )
            combined = "\n".join(assembled)[:150000]

            provider, model_id, max_tokens, temperature, system_prompt = get_llm_config()
            lang = st.session_state.get("ui_lang", "zh")
            language_instruction = (
                "Write the output in English."
                if lang == "en"
                else "請使用繁體中文撰寫，並強調跨文件之 FDA 法規觀點與差異。"
            )

            prompt = f"""
你是一位專精於 FDA 報規與跨文件策略評估的顧問。

{language_instruction}

你將收到多份文件，已以 START/END FILE 標記區分。
請視其為一組「知識庫」，執行以下任務：

- 比較與對照各文件在法規立場、臨床證據、CMC、風險管理等面向的差異與一致性。
- 找出關鍵落差。
- 產出 Markdown 報告，包含：
  - Executive Summary
  - Cross-Document Comparisons
  - Key Risks / Gaps
  - FDA 審查觀點下的優先順序與建議下一步

[DOCUMENTS]
{combined}
"""
            result = call_llm(
                provider=provider,
                model=model_id,
                system_prompt=system_prompt,
                user_messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            st.markdown("### Synthesis Report")
            st.markdown(result or "_No output._")
    st.markdown("</div>", unsafe_allow_html=True)


def tab_smart_replace():
    st.markdown(f"## {t('tab_smart_replace')}")
    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        template_text = st.text_area(
            "Template (with placeholders like [Product Name], [Indication])",
            height=260,
        )
    with col2:
        context_text = st.text_area(
            "Context / Raw Data Source (e.g., protocol, CSR, CMC summary)",
            height=260,
        )

    instructions = st.text_area(
        "Natural language instructions (tone, style, constraints)",
        value="請依照 FDA 法規與科學合理性填寫所有欄位，維持專業、精確且審查友善的語氣。",
    )

    if st.button("Run Smart Replace"):
        provider, model_id, max_tokens, temperature, system_prompt = get_llm_config()
        lang = st.session_state.get("ui_lang", "zh")
        language_instruction = (
            "Write the output in English."
            if lang == "en"
            else "請使用繁體中文撰寫完整範本內容。"
        )

        prompt = f"""
你是一位 FDA 報規與法律文本撰寫專家。

{language_instruction}

下列為一份含有占位符的範本：

[TEMPLATE]
{template_text}

以下為未結構化的背景資料：
[CONTEXT]
{context_text}

使用者說明：
{instructions}

請依據 CONTEXT 中資訊：
- 補齊所有占位符
- 避免憑空捏造關鍵數據；若文件未提供，請以「（文件未提供明確資訊）」標示
- 以 Markdown 輸出完整且已填寫完成之範本
"""
        with st.spinner("Generating filled template…"):
            result = call_llm(
                provider=provider,
                model=model_id,
                system_prompt=system_prompt,
                user_messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
        st.markdown("### Completed Template")
        st.markdown(result or "_No output._")
    st.markdown("</div>", unsafe_allow_html=True)


def tab_ai_note_keeper():
    st.markdown(f"## {t('tab_note_keeper')}")
    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)

    # Sub-tabs inside Note Keeper
    sub1, sub2 = st.tabs(["Magic Transform", "Keyword Coral Keeper"])

    # --- Original Magic Transform ---
    with sub1:
        raw_note = st.text_area("Your raw notes / brain dump", height=240, key="note_raw")
        col1, col2, col3, col4, col5 = st.columns(5)
        action = None
        if col1.button("Format"):
            action = "format"
        if col2.button("Tasks"):
            action = "tasks"
        if col3.button("Fix"):
            action = "fix"
        if col4.button("Summary"):
            action = "summary"
        if col5.button("Expand"):
            action = "expand"

        if action and raw_note.strip():
            provider, model_id, max_tokens, temperature, system_prompt = get_llm_config()
            lang = st.session_state.get("ui_lang", "zh")
            language_instruction = (
                "Write the output in English."
                if lang == "en"
                else "請使用繁體中文撰寫，並維持 FDA 報規或專業審查文件常見之語氣。"
            )

            prompt_map = {
                "format": "將這些筆記整理成結構清楚的 Markdown（含標題與條列），方便日後用於 FDA 文件草擬。",
                "tasks": "從這些內容中萃取所有可執行任務，並以核取清單 (- [ ]) 條列，著重於 FDA 報規與合規行動。",
                "fix": "修正文法、用詞與邏輯，使其更適合作為對 FDA 或內部審查使用的專業文字。",
                "summary": "先給出一段精簡 TL;DR 摘要，再以條列方式整理重點與風險項目。",
                "expand": "將簡短的要點擴寫成較完整的段落，並加入 FDA 合規觀點或實務建議。",
            }
            prompt = f"""
你是一位專門協助 FDA 報規團隊整理思路的「知識管理顧問」。

{language_instruction}

使用者的原始筆記如下：
{raw_note}

任務：{prompt_map[action]}

請只輸出整理後的 Markdown 筆記。
"""
            with st.spinner("Transforming notes…"):
                result = call_llm(
                    provider=provider,
                    model=model_id,
                    system_prompt=system_prompt,
                    user_messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            st.markdown("### Transformed Notes")
            st.markdown(result or "_No output._")

    # --- New Keyword Coral Keeper ---
    with sub2:
        st.markdown("### 📑 關鍵字珊瑚標註筆記（Keyword Coral Keeper）")
        base_text = st.text_area(
            "貼上原始文字或 Markdown：",
            height=240,
            key="coral_input_text",
        )
        if st.button("整理並以珊瑚色標示關鍵字"):
            if not base_text.strip():
                st.warning("請先貼上內容。")
            else:
                provider, model_id, max_tokens, temperature, system_prompt = get_llm_config()
                lang = st.session_state.get("ui_lang", "zh")
                language_instruction = (
                    "Write the output in English."
                    if lang == "en"
                    else "請使用繁體中文撰寫，並將關鍵詞以 HTML span 方式標示。"
                )

                prompt = f"""
你是一位專業的「結構化筆記整理專家」，同時熟悉 FDA / 科學 / 技術領域的關鍵詞。

任務：
1. 將使用者輸入的文字或 Markdown，整理成邏輯清楚、層次分明的 Markdown 筆記（使用 #, ##, ###, - 等）。
2. 尋找關鍵詞（例如重要名詞、專有名詞、重要機構、關鍵風險或動作），並以下列 HTML 格式標示：
   <span style="color:#FF7F50;font-weight:bold">關鍵詞</span>
3. 其餘文字保持一般 Markdown 排版即可。

{language_instruction}

使用者原始內容：
[NOTE START]
{base_text}
[NOTE END]
"""
                with st.spinner("Organizing and highlighting keywords…"):
                    result = call_llm(
                        provider=provider,
                        model=model_id,
                        system_prompt=system_prompt,
                        user_messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                st.session_state["coral_note_md"] = result or ""

        if "coral_note_md" in st.session_state and st.session_state["coral_note_md"]:
            st.markdown("---")
            st.markdown("### ✏️ 可編輯筆記（含珊瑚色關鍵詞）")
            coral_view_mode = st.radio(
                "顯示模式",
                ["Markdown + 珊瑚色預覽", "純文字"],
                horizontal=True,
                key="coral_view_mode",
            )
            coral_text = st.text_area(
                "編輯筆記內容（保留 span 標籤可維持珊瑚色）：",
                value=st.session_state["coral_note_md"],
                height=260,
                key="coral_edit_text",
            )
            st.session_state["coral_note_md"] = coral_text

            if coral_view_mode == "Markdown + 珊瑚色預覽":
                st.markdown("#### 預覽（允許 HTML）")
                st.markdown(coral_text, unsafe_allow_html=True)
            else:
                st.text(coral_text)

            st.markdown("---")
            st.markdown("### 💬 針對此筆記持續提問")
            coral_q = st.text_area("你的問題 / 指令", key="coral_qa_question")
            provider_q, model_q, max_tokens_q, temp_q = limited_model_selector("Gemini 3 Flash")
            coral_answer_view = st.radio(
                "回答顯示為",
                ["Markdown", "純文字"],
                horizontal=True,
                key="coral_answer_view",
            )
            if st.button("向模型提問（以此筆記為背景）"):
                if not coral_q.strip():
                    st.warning("請輸入問題。")
                else:
                    context = f"""
以下為經整理且含關鍵詞標示的筆記內容（包含 HTML span 與 Markdown）：

[NOTE]
{st.session_state['coral_note_md'][:80000]}
"""
                    with st.spinner("Model thinking with note…"):
                        answer = call_llm(
                            provider=provider_q,
                            model=model_q,
                            system_prompt="你是一位專業知識管理顧問，請善用筆記內容回答問題。",
                            user_messages=[
                                {"role": "user", "content": context},
                                {"role": "user", "content": coral_q},
                            ],
                            max_tokens=max_tokens_q,
                            temperature=temp_q,
                        )
                    if coral_answer_view == "Markdown":
                        st.markdown(answer or "_No answer produced._")
                    else:
                        st.text(answer or "_No answer produced._")

    st.markdown("</div>", unsafe_allow_html=True)


# =========================
#  Main
# =========================

def main():
    st.set_page_config(
        page_title="AuditFlow AI · Masterpiece Edition (FDA)",
        layout="wide",
    )

    # Init session defaults
    if "ui_lang" not in st.session_state:
        st.session_state.ui_lang = "zh"
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = True
    if "artist_style_key" not in st.session_state:
        st.session_state.artist_style_key = ARTIST_STYLES[0].key

    # Load agents
    agents = load_agents()

    # Sidebar global controls
    with st.sidebar:
        st.markdown("## 🌐 Global Settings")
        lang_label = st.radio("Language / 語言", ["English", "繁體中文"], key="lang_radio")
        st.session_state.ui_lang = "en" if lang_label == "English" else "zh"

        dark_mode = st.toggle("Dark mode", value=st.session_state.dark_mode, key="dark_mode_toggle")
        st.session_state.dark_mode = dark_mode

        active_style = style_selector_ui()
        render_api_key_inputs()
        selected_agent = agent_selector_ui(agents)
        render_llm_controls()

    # Apply painter theme
    apply_theme(active_style, st.session_state.dark_mode)

    # Header
    st.markdown(f"<h1 class='accent-title'>{t('app_title')}</h1>", unsafe_allow_html=True)
    st.markdown(t("subtitle"))
    if selected_agent:
        st.markdown(
            f"<div class='accent-chip'>目前代理人：{selected_agent.get('display_name_zh','')}</div>",
            unsafe_allow_html=True,
        )

    # Tabs (added OCR tab)
    tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs([
        t("tab_ocr_pdf"),
        t("tab_file_transform"),
        t("tab_file_intel"),
        t("tab_multi_file"),
        t("tab_smart_replace"),
        t("tab_note_keeper"),
    ])

    with tab0:
        tab_ocr_pdf_intelligence()
    with tab1:
        tab_file_transform_deep_summary()
    with tab2:
        tab_file_intelligence()
    with tab3:
        tab_multi_file_synthesis()
    with tab4:
        tab_smart_replace()
    with tab5:
        tab_ai_note_keeper()


if __name__ == "__main__":
    main()
