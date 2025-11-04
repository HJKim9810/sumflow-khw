# app/services/llm.py — FULL, merge_core 호환(프롬프트/옵션/타임아웃 시그니처 자동 폴백)

from __future__ import annotations

import os
import re
import json
import time
import logging
from typing import Any, Dict, List, Tuple
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.utils.category_name import normalize_category

# merge_core 호출 (시그니처가 환경마다 다를 수 있어 아래에서 호환 처리)
from app.thirdparty.merge_core.llm_engine import summarize_with_ollama  # noqa

logger = logging.getLogger("app")

# ===== 설정: core/config.py 우선, 없으면 env 폴백 =====
try:
    from app.core.config import (
        OLLAMA_BASE as _CFG_OLLAMA_BASE,   # 예: "http://127.0.0.1:11434"
        LLM_MODEL as _CFG_LLM_MODEL,       # 예: "llama3" or "gemma3-summarizer"
    )
    try:
        from app.core.config import OLLAMA_TIMEOUT as _CFG_TIMEOUT
    except Exception:
        _CFG_TIMEOUT = None
    try:
        from app.core.config import OLLAMA_OPTIONS as _CFG_OPTIONS  # dict
    except Exception:
        _CFG_OPTIONS = None
    try:
        from app.core.config import SUMM_ENABLED as _CFG_SUMM_ENABLED
    except Exception:
        _CFG_SUMM_ENABLED = None
    try:
        from app.core.config import SUMM_QUICK_THRESHOLD as _CFG_QUICK
    except Exception:
        _CFG_QUICK = None
except Exception:
    _CFG_OLLAMA_BASE = None
    _CFG_LLM_MODEL = None
    _CFG_TIMEOUT = None
    _CFG_OPTIONS = None
    _CFG_SUMM_ENABLED = None
    _CFG_QUICK = None

OLLAMA_BASE = (_CFG_OLLAMA_BASE or os.getenv("OLLAMA_BASE") or os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
LLM_MODEL   = (_CFG_LLM_MODEL   or os.getenv("LLM_MODEL")   or os.getenv("OLLAMA_MODEL") or "llama3")
OLLAMA_TIMEOUT: int = int(_CFG_TIMEOUT or os.getenv("OLLAMA_TIMEOUT", "300"))

def _parse_ollama_options_from_env() -> Dict[str, Any]:
    """OLLAMA_OPTIONS="temperature=0.25,num_predict=512,top_p=0.9" 파싱."""
    raw = (os.getenv("OLLAMA_OPTIONS") or "").strip()
    base: Dict[str, Any] = {"temperature": 0.25, "top_p": 0.9, "num_predict": 512}
    if not raw:
        return base
    for token in raw.split(","):
        token = token.strip()
        if not token or "=" not in token:
            continue
        k, v = token.split("=", 1)
        k, v = k.strip(), v.strip()
        if re.fullmatch(r"-?\d+", v):
            base[k] = int(v)
        elif v.lower() in ("true", "false"):
            base[k] = (v.lower() == "true")
        else:
            try:
                base[k] = float(v)
            except ValueError:
                base[k] = v
    return base

OLLAMA_OPTIONS: Dict[str, Any] = _CFG_OPTIONS or _parse_ollama_options_from_env()

# 토글: 요약 끄기(운영 중 LLM 장애/비용 회피)
SUMM_ENABLED: bool = bool(_CFG_SUMM_ENABLED if _CFG_SUMM_ENABLED is not None
                          else (os.getenv("SUMM_ENABLED", "true").lower() == "true"))

# 짧은 문서 원패스 임계값
SUMM_QUICK_THRESHOLD: int = int(_CFG_QUICK or os.getenv("SUMM_QUICK_THRESHOLD", "2500"))

# ===== HTTP 세션 (속도/안정성) =====
_SESSION = requests.Session()
_ADAPTER = HTTPAdapter(
    pool_connections=16,
    pool_maxsize=16,
    max_retries=Retry(total=2, backoff_factor=0.2, status_forcelist=[502, 503, 504], raise_on_status=False),
)
_SESSION.mount("http://", _ADAPTER)
_SESSION.mount("https://", _ADAPTER)

# ===== 사전 정규화 =====
_ZWS = "\u200b\u200c\u200d\uFEFF"

HEADER_PATTERNS = [
    r"^\s*-\s*\d+\s*-\s*$",               # "- 1 -" 형태 페이지 마커
    r"^\s*Page\s+\d+\s*(of\s+\d+)?\s*$", # "Page 1 (of 6)"
    r"^\s*\d+\s*/\s*\d+\s*$",            # "1/6"
    r"^\s*목\s*차\s*$",
]
INLINE_NOISE = [(r"\s{2,}", " "), (r"[ \t]+(\n)", r"\1")]

def _strip_headers_footers(text: str) -> str:
    lines = (text or "").splitlines()
    keep: List[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            keep.append("")
            continue
        if any(re.match(p, s) for p in HEADER_PATTERNS):
            continue
        keep.append(ln)
    out = "\n".join(keep)
    out = re.sub(rf"[{_ZWS}]", "", out)
    out = re.sub(r"([^\d])-(\s*\n)", r"\1\n", out)
    out = re.sub(r"(?m)^\s*\d+\.\s*", "", out)
    for pat, repl in INLINE_NOISE:
        out = re.sub(pat, repl, out)
    out = re.sub(r"[─━═\-_=]{5,}", "", out)
    return out.strip()

def _preclean(text: str) -> str:
    t = (text or "").replace("\r", "")
    b = len(t)
    t = _strip_headers_footers(t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    a = len(t)
    logger.info(f"[LLM] preclean: len_before={b}, len_after={a}")
    return t

# ===== 프롬프트 =====
SYS_SUMMARY = (
    "You are an expert summarizer for Korean government and legislative documents. "
    "Return Korean if the source is Korean. Produce short, abstract summaries that do not copy long spans of the source. "
    "Do NOT copy any sentence verbatim; limit any direct quote to <= 8 consecutive words. "
    "Be precise about policy changes, legal clauses, thresholds, dates."
)

CATEGORY_GUIDE = """
분류 가이드(예시):
- 정책/법안 / 국회보고
- 정책/법안 / 체계자구검토
- 산업/수산 / 조합·협동조합
- 조직/인사 / 여성참여·할당
- 재정/지원 / 보조·지원제도
문서에 맞춰 [대분류]/[소분류]를 한국어로 간결히 선택하세요.
"""

CHUNK_USER_PROMPT = (
    "아래 텍스트를 3~6개의 핵심 불릿으로 **간결한 추상화 요약**해줘.\n"
    "- 원문 문장 그대로 복사 금지(8단어 연속 금지)\n"
    "- 정책/조문/수치/대상/효과 중심으로 요약\n"
    "- 불릿 1개는 120자 이내\n"
    "- JSON만 반환\n\n"
    "{{\n"
    '  "bullets": ["...", "...", "..."]\n'
    "}}\n\n"
    "텍스트:\n"
    "{body}\n"
)

REDUCE_USER_PROMPT = (
    "여러 조각 요약을 통합해 **문서 전체 요약**을 작성하세요.\n"
    "- 제목 1줄(80자 이내)\n"
    "- bullets 4~8개, 각 120자 이내, 중복·군더더기 제거, 추상화 요약\n"
    "- category/subcategory는 한국어로, 아래 가이드를 참고해 선택\n"
    f"{CATEGORY_GUIDE}\n"
    "- 원문 문장 복사 금지(8단어 연속 금지)\n"
    "- JSON만 반환\n\n"
    "{\n"
    '  "title": "...",\n'
    '  "bullets": ["...", "..."],\n'
    '  "category": "정책/법안",\n'
    '  "subcategory": "국회보고"\n'
    "}\n\n"
    "조각 요약들(JSON 배열):\n"
    "{chunks}\n"
)

# ===== Ollama direct helpers =====
def _ollama_chat(messages: List[Dict[str, str]], timeout_s: int | None = None) -> str:
    url = f"{OLLAMA_BASE}/api/chat"
    payload: Dict[str, Any] = {"model": LLM_MODEL, "messages": messages, "stream": False, "options": OLLAMA_OPTIONS}
    t0 = time.perf_counter()
    try:
        logger.info(f"🧠 LLM call START (chat) model={LLM_MODEL} base={OLLAMA_BASE}")
        resp = _SESSION.post(url, json=payload, timeout=timeout_s or OLLAMA_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("message") or {}).get("content", "") or ""
        dt = int((time.perf_counter() - t0) * 1000)
        logger.info(f"🧠 LLM call DONE (chat) in {dt} ms; len={len(content)}")
        return content
    except Exception as e:
        dt = int((time.perf_counter() - t0) * 1000)
        logger.exception(f"🧠 LLM call ERROR (chat) after {dt} ms: {e}")
        raise RuntimeError(f"Ollama /api/chat failed: {e}") from e

def _ollama_generate(prompt: str, system: str | None = None, timeout_s: int | None = None) -> str:
    url = f"{OLLAMA_BASE}/api/generate"
    payload: Dict[str, Any] = {
        "model": LLM_MODEL, "prompt": prompt, "system": system or "", "stream": False, "options": OLLAMA_OPTIONS
    }
    t0 = time.perf_counter()
    try:
        logger.info(f"🧠 LLM call START (generate) model={LLM_MODEL} base={OLLAMA_BASE}")
        resp = _SESSION.post(url, json=payload, timeout=timeout_s or OLLAMA_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("response", "") or ""
        dt = int((time.perf_counter() - t0) * 1000)
        logger.info(f"🧠 LLM call DONE (generate) in {dt} ms; len={len(content)}")
        return content
    except Exception as e:
        dt = int((time.perf_counter() - t0) * 1000)
        logger.exception(f"🧠 LLM call ERROR (generate) after {dt} ms: {e}")
        raise RuntimeError(f"Ollama /api/generate failed: {e}") from e

# ===== JSON 유틸 =====
def _safe_json_parse(s: str) -> Dict[str, Any]:
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}

def _clip_list_str(xs: List[str], n_max: int, each_len: int) -> List[str]:
    out: List[str] = []
    for x in xs[:n_max]:
        y = (x or "").strip()
        if not y:
            continue
        if len(y) > each_len:
            y = y[:each_len].rstrip() + "…"
        out.append(y)
    return out

def _contains_long_verbatim(bullet: str, source: str, limit_words: int = 8) -> bool:
    bw = re.findall(r"\w+", bullet)
    if len(bw) < limit_words:
        return False
    for i in range(0, len(bw) - limit_words + 1):
        phrase = " ".join(bw[i:i+limit_words])
        if phrase and phrase in source:
            return True
    return False

def _remove_overly_verbatim(bullets: List[str], source: str) -> List[str]:
    cleaned: List[str] = []
    for b in bullets:
        if not _contains_long_verbatim(b, source, limit_words=8):
            cleaned.append(b)
    return cleaned or bullets

def _split_text(text: str, max_chars: int = 1800) -> List[str]:
    s = (text or "").strip()
    if not s:
        return []
    if len(s) <= max_chars:
        return [s]
    parts, buf, acc = [], [], 0
    paras = re.split(r"\n{2,}", s)
    for p in paras:
        p = p.strip()
        if not p:
            continue
        if len(p) > max_chars:
            sents = re.split(r"(?<=[\.!?])\s+|(?<=[다요]\.)\s+", p)
            for sent in sents:
                sent = sent.strip()
                if not sent:
                    continue
                if acc + len(sent) + 1 > max_chars and buf:
                    parts.append("\n".join(buf)); buf, acc = [], 0
                buf.append(sent); acc += len(sent) + 1
        else:
            if acc + len(p) + 2 > max_chars and buf:
                parts.append("\n".join(buf)); buf, acc = [], 0
            buf.append(p); acc += len(p) + 2
    if buf:
        parts.append("\n".join(buf))
    return parts or [s[:max_chars]]

# ===== 규칙 기반 카테고리 보정 =====
def _rule_category(text: str) -> Tuple[str, str]:
    t = (text or "").replace(" ", "")
    if "체계자구검토" in t:
        return ("정책/법안", "체계자구검토")
    if "위원회의결안" in t or "의결안" in t:
        return ("정책/법안", "국회보고")
    if "검토보고서" in t or "검토보고" in t:
        return ("정책/법안", "검토보고")
    if "수산업협동조합법" in t or "협동조합" in t:
        return ("정책/법안", "조합·협동조합")
    if "여성임원" in t or "여성참여" in t or "여성할당" in t:
        return ("조직/인사", "여성참여·할당")
    return ("미분류", "미분류")

# ===== merge_core 호환 호출 래퍼 =====
def _call_summarize_with_ollama(prompt: str, options: Dict[str, Any], timeout_s: int):
    """
    merge_core.llm_engine.summarize_with_ollama 시그니처가 환경마다 상이하여
    여러 형태로 재시도한다.
    시도 순서:
      1) 키워드: (text, model, host, temperature, top_p, num_predict, timeout_s)
      2) 키워드 축소: (text, model, host, timeout_s)
      3) 위치 인자: (text, model, host, timeout_s)
      4) 최소: (text,)
    """
    temp = options.get("temperature")
    top_p = options.get("top_p")
    num_predict = options.get("num_predict")

    # 1) 가장 풍부한 시그니처
    try:
        return summarize_with_ollama(
            prompt,
            model=LLM_MODEL,
            host=OLLAMA_BASE,
            temperature=temp,
            top_p=top_p,
            num_predict=num_predict,
            timeout_s=timeout_s,
        )
    except TypeError as e1:
        logger.warning(f"[LLM] merge_core signature A rejected: {e1}")

        # 2) 축소된 키워드
        try:
            return summarize_with_ollama(
                prompt,
                model=LLM_MODEL,
                host=OLLAMA_BASE,
                timeout_s=timeout_s,
            )
        except TypeError as e2:
            logger.warning(f"[LLM] merge_core signature B rejected: {e2}")

            # 3) 위치 인자
            try:
                return summarize_with_ollama(prompt, LLM_MODEL, OLLAMA_BASE, timeout_s)
            except TypeError as e3:
                logger.warning(f"[LLM] merge_core signature C rejected: {e3}")

                # 4) 최소
                return summarize_with_ollama(prompt)

# ===== 맵-리듀스 요약 =====
def _summarize_chunk(chunk: str) -> List[str]:
    messages = [
        {"role": "system", "content": SYS_SUMMARY},
        {"role": "user", "content": CHUNK_USER_PROMPT.format(body=chunk)},
    ]
    content = _ollama_chat(messages)
    if not content or len(content) < 5:
        logger.warning("[LLM] empty/short chat result; retrying with /api/generate")
        content = _ollama_generate(CHUNK_USER_PROMPT.format(body=chunk), system=SYS_SUMMARY)

    obj = _safe_json_parse(content)
    bullets = obj.get("bullets", [])
    if not isinstance(bullets, list):
        bullets = [str(bullets)]
    bullets = [str(b).strip() for b in bullets if str(b).strip()]
    bullets = _clip_list_str(bullets, n_max=8, each_len=140)
    bullets = _remove_overly_verbatim(bullets, chunk)
    return bullets

def _reduce_summaries(all_bullets: List[List[str]]) -> Dict[str, Any]:
    chunk_objs = [{"bullets": blts} for blts in all_bullets if blts]
    reduce_prompt = REDUCE_USER_PROMPT.format(chunks=json.dumps(chunk_objs, ensure_ascii=False))
    messages = [{"role": "system", "content": SYS_SUMMARY}, {"role": "user", "content": reduce_prompt}]
    content = _ollama_chat(messages)
    if not content or len(content) < 5:
        logger.warning("[LLM] empty/short chat result in reduce; retrying with /api/generate")
        content = _ollama_generate(reduce_prompt, system=SYS_SUMMARY)

    obj = _safe_json_parse(content)
    title = str(obj.get("title", "")).strip()[:120] or "Untitled"
    bullets = obj.get("bullets", [])
    if not isinstance(bullets, list):
        bullets = [str(bullets)]
    bullets = [str(b).strip() for b in bullets if str(b).strip()]
    bullets = _clip_list_str(bullets, n_max=8, each_len=140)
    cat = str(obj.get("category", "")).strip()
    sub = str(obj.get("subcategory", "")).strip()
    return {"title": title, "bullets": bullets, "category": cat or "미분류", "subcategory": sub or "미분류"}

def _fallback_summary(text: str) -> Dict[str, Any]:
    head = (text or "").strip().splitlines()
    title = (head[0] if head else "Untitled").strip()[:120]
    body = " ".join(head[1:])[:600]
    bullets = [body[i:i+100] for i in range(0, len(body), 100)][:5] or [title]
    return {"title": title or "Untitled", "bullets": bullets, "category": "미분류", "subcategory": "미분류"}

# ===== 간단 2줄 요약 =====
_SIMPLE_PROMPT_TPL = """다음 입력문서를 읽고 한국어로만 두 줄로 답하세요.
- 지시문/머리말/따옴표 출력 금지.
- 딱 두 줄:
요약:
카테고리: 대분류/소분류

[입력]
---
{body}
---
"""

def _normalize_category_pair(s: str) -> tuple[str, str]:
    if not s:
        return ("미분류", "기타")
    s = re.sub(r"[()\[\]{}#*「」『』<>]", "", s).strip()
    parts = re.split(r"[>\-\|;,·•∙▶▷➡️→/]", s)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return ("미분류", "기타")
    if len(parts) == 1:
        return (parts[0], "기타")
    return (parts[0], parts[1])

def summarize_text_simple(text: str) -> dict:
    if not SUMM_ENABLED:
        t = (text or "")
        title = (t.strip().splitlines()[0] if t else "Untitled")[:120]
        cat, sub = _rule_category(t)
        return {"title": title, "bullets": [], "category": cat, "subcategory": sub, "raw": ""}

    body = (text or "")[:15000]
    prompt = _SIMPLE_PROMPT_TPL.format(body=body)

    last_err = None
    for _ in range(2):
        try:
            payload = {
                "model": LLM_MODEL, "prompt": prompt, "stream": False,
                "options": {"temperature": 0.0, "num_predict": 512},
            }
            r = _SESSION.post(f"{OLLAMA_BASE}/api/generate", json=payload, timeout=min(600, OLLAMA_TIMEOUT))
            r.raise_for_status()
            raw = (r.json().get("response") or "").strip()
            last = None
            for m in re.finditer(r"^\s*요약\s*:\s*", raw, flags=re.MULTILINE):
                last = m
            summary = raw[last.end():].splitlines()[0].strip() if last else raw.strip()
            m_cat = re.search(r"^\s*카테고리\s*:\s*(.+)$", raw, flags=re.MULTILINE)
            big, small = _normalize_category_pair(m_cat.group(1) if m_cat else "")
            return {"title": summary[:120] or "Untitled", "bullets": [], "category": big or "미분류", "subcategory": small or "기타", "raw": raw}
        except Exception as e:
            last_err = e
            continue
    logger.warning(f"[LLM] summarize_text_simple fallback due to: {last_err}")
    t = (text or "")
    title = (t.strip().splitlines()[0] if t else "Untitled")[:120]
    cat, sub = _rule_category(t)
    return {"title": title, "bullets": [], "category": cat, "subcategory": sub, "raw": ""}

# ===== 파일 요약 API (업로드 파이프라인이 호출) =====
def summarize_to_file(
    input_txt_path: Path,
    summary_out_path: Path,
    *,
    title_hint: str | None = None,
    category: bool = False,
    timeout_s: int = 60
):
    """
    OCR merged.txt를 읽어 요약하고 summary.txt로 저장.
    merge_core.summarize_with_ollama의 반환형이 환경에 따라
    dict 또는 str일 수 있으므로 둘 다 안전하게 처리한다.
    반환: ({"summary": str, "title": str}, normalized_category | None)
    """
    input_txt_path = Path(input_txt_path)
    summary_out_path = Path(summary_out_path)
    summary_out_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_txt_path.exists():
        raise FileNotFoundError(f"input text not found: {input_txt_path}")

    raw_text = input_txt_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not raw_text:
        raise RuntimeError(f"OCR merged text empty: {input_txt_path}")

    # ----- 프롬프트 -----
    prompt = (
        "당신은 문서 요약가입니다.\n"
        "다음 문서를 7~10문장 내로 핵심만 요약하고, 문서를 분류하여 카테고리를 2개 이내로 함께 제시하세요.\n"
        "형식:\n"
        "[제목]\n"
        "<한줄제목>\n\n"
        "[요약]\n"
        "[카테고리]\n"
        "----- 문서 시작 -----\n"
        f"{raw_text[:12000]}\n"
        "----- 문서 끝 -----\n"
    )
    if title_hint:
        prompt = f"(참고 제목 힌트: {title_hint})\n" + prompt

    # ----- merge_core 호출 (여러 시그니처 폴백 포함) -----
    result_raw = _call_summarize_with_ollama(prompt, OLLAMA_OPTIONS, timeout_s)

    # ----- 반환형 안전 처리 -----
    title = ""
    summary = ""
    category = ""

    if isinstance(result_raw, dict):
        # dict 타입: 다양한 키 후보 수용
        summary = (result_raw.get("summary")
                   or result_raw.get("response")
                   or (result_raw.get("message") or {}).get("content")
                   or "").strip()
        title = (result_raw.get("title") or "").strip()
        # dict인데 summary 없으면 str처럼 취급하도록 비워둠
    elif isinstance(result_raw, str):
        # str 타입: 그대로 요약 본문으로 사용
        summary = result_raw.strip()

    # merge_core에서 뭔가 왔지만 summary가 여전히 비면 direct generate 시도
    if not summary:
        try:
            logger.warning("[LLM] merge_core empty → direct /api/generate fallback")
            resp = requests.post(
                f"{OLLAMA_BASE}/api/generate",
                json={"model": LLM_MODEL, "prompt": prompt, "stream": False, "options": OLLAMA_OPTIONS},
                timeout=max(timeout_s, OLLAMA_TIMEOUT),   # 90처럼 짧아 타임아웃 나지 않도록 보정
            )
            resp.raise_for_status()
            summary = (resp.json().get("response") or "").strip()
        except Exception as e:
            logger.exception(f"[LLM] direct fallback failed: {e}")
            summary = ""

    if not summary:
        # 여기서 더 진행하면 DB에 빈 요약이 들어가므로 실패 처리
        raise RuntimeError("LLM returned empty content after merge_core + direct fallback")

    # 제목 보정
    if not title:
        # raw에서 첫 짧은 줄, 없으면 summary 첫 줄, 그래도 없으면 힌트
        raw_lines = (result_raw.get("raw").splitlines() if isinstance(result_raw, dict) and result_raw.get("raw") else [])
        picked = ""
        for ln in raw_lines:
            s = ln.strip()
            if s and len(s) <= 60 and not s.startswith("["):
                picked = s
                break
        if not picked and summary:
            picked = summary.splitlines()[0].strip()
        title = (picked or title_hint or "Untitled")[:120]

    # 파일 기록
    summary_out_path.write_text(summary, encoding="utf-8")

    # 카테고리 추론 (옵션)
    raw_category = None
    if category:
        try:
            from app.thirdparty.merge_core.category_parser import guess_category  # 선택적
            raw_category = guess_category(summary or raw_text)
        except Exception:
            raw_category = None

    raw_category = normalize_category(raw_category) if raw_category else None
    return {"summary": summary, "title": title}, raw_category


# ===== 공개 API =====
def _fallback_summary(text: str) -> Dict[str, Any]:
    head = (text or "").strip().splitlines()
    title = (head[0] if head else "Untitled").strip()[:120]
    body = " ".join(head[1:])[:600]
    bullets = [body[i:i+100] for i in range(0, len(body), 100)][:5] or [title]
    return {"title": title or "Untitled", "bullets": bullets, "category": "미분류", "subcategory": "미분류"}

def summarize_and_categorize(text: str) -> Dict[str, Any]:
    try:
        if not SUMM_ENABLED:
            logger.info("[LLM] SUMM_ENABLED=false → local rule-only path")
            t = (text or "")
            title = (t.strip().splitlines()[0] if t else "Untitled")[:120]
            cat, sub = _rule_category(t)
            return {"title": title, "bullets": [], "category": cat, "subcategory": sub}

        cleaned = _preclean(text)
        if not cleaned and text:
            cleaned = text

        if len(cleaned) <= SUMM_QUICK_THRESHOLD:
            logger.info(f"[LLM] quick path: single-pass summarize (len={len(cleaned)})")
            content = _ollama_chat(
                [{"role": "system", "content": SYS_SUMMARY},
                 {"role": "user", "content": REDUCE_USER_PROMPT.format(
                     chunks=json.dumps([{"bullets": []}], ensure_ascii=False)
                 ) + "\n\n원문 전체 텍스트:\n" + cleaned[:8000]}]
            )
            if not content or len(content) < 5:
                logger.warning("[LLM] quick path empty/short; retrying with /api/generate")
                prompt = REDUCE_USER_PROMPT.format(chunks=json.dumps([{"bullets": []}], ensure_ascii=False)) + "\n\n원문 전체 텍스트:\n" + cleaned[:8000]
                content = _ollama_generate(prompt, system=SYS_SUMMARY)
                if not content or len(content.strip()) < 5:
                    raise RuntimeError("LLM returned empty content after chat/generate")

            obj = _safe_json_parse(content)
            title = (str(obj.get("title", "")) or "Untitled")[:120]
            bullets = obj.get("bullets", [])
            if not isinstance(bullets, list):
                bullets = [str(bullets)]
            bullets = _clip_list_str([str(b).strip() for b in bullets if str(b).strip()], n_max=8, each_len=140)
            cat = (str(obj.get("category", "")) or "").strip()
            sub = (str(obj.get("subcategory", "")) or "").strip()
            if not cat or not sub or cat == "미분류" or sub == "미분류":
                rc, rs = _rule_category(cleaned)
                cat, sub = rc, rs
            return {"title": title, "bullets": bullets, "category": cat or "미분류", "subcategory": sub or "미분류"}

        logger.info(f"[LLM] input lengths: raw={len(text or '')}, cleaned={len(cleaned)}")
        chunks = _split_text(cleaned, max_chars=1800)
        logger.info(f"[LLM] chunk_count={len(chunks)}, chunk_lens={[len(c) for c in chunks[:3]]}{'...' if len(chunks)>3 else ''}")

        if not chunks and cleaned:
            chunks = [cleaned[:1800]]
            logger.warning("[LLM] chunks empty after split; forcing single chunk.")

        if not chunks:
            logger.warning("[LLM] no content after cleaning; using fallback.")
            return _fallback_summary(cleaned)

        all_bullets: List[List[str]] = []
        for idx, ch in enumerate(chunks):
            logger.info(f"[LLM] summarize chunk {idx+1}/{len(chunks)} len={len(ch)}")
            blts = _summarize_chunk(ch)
            logger.info(f"[LLM] chunk {idx+1} bullets={len(blts)}")
            if blts:
                all_bullets.append(blts)

        if not all_bullets:
            logger.warning("[LLM] all chunks empty; using fallback.")
            return _fallback_summary(cleaned)

        if len(all_bullets) <= 2:
            flat = [b for blts in all_bullets for b in blts]
            flat = _clip_list_str(flat, n_max=8, each_len=140)
            rc, rs = _rule_category(cleaned)
            title_guess = (cleaned.splitlines()[0] if cleaned else "Untitled").strip()[:120]
            return {"title": title_guess or "Untitled", "bullets": flat, "category": rc, "subcategory": rs}

        logger.info(f"[LLM] reduce {len(all_bullets)} chunk-summaries")
        result = _reduce_summaries(all_bullets)
        result["bullets"] = _clip_list_str(result.get("bullets", []), n_max=8, each_len=140)
        result["title"] = (result.get("title") or "Untitled")[:120]
        cat, sub = result.get("category") or "", result.get("subcategory") or ""
        if not cat or not sub or cat == "미분류" or sub == "미분류":
            rc, rs = _rule_category(cleaned)
            result["category"] = rc
            result["subcategory"] = rs
        return result

    except Exception as e:
        logger.warning(f"LLM summarize fallback used due to: {e}")
        return _fallback_summary(text)
