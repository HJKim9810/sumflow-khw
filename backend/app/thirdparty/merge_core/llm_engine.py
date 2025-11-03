import os, time, textwrap, httpx, logging

log = logging.getLogger(__name__)

# ---------------------------
# ENV & Timeout Helpers
# ---------------------------

def _env_host() -> str:
    return os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")

def _env_model() -> str:
    return os.getenv("OLLAMA_MODEL", "gemma3-summarizer:latest")

def _env_timeout_sec() -> int:
    # 초 단위 환경변수 (기본 300)
    try:
        return int(os.getenv("OLLAMA_TIMEOUT", "300"))
    except Exception:
        return 300

def _httpx_timeout():
    """
    connect=30s, read/write는 OLLAMA_TIMEOUT(초).
    httpx.Timeout을 명시적으로 구성해서 '응답까지 12초' 같은 외부 타임박스 이슈를 구분하기 쉽도록 함.
    """
    t = _env_timeout_sec()
    return httpx.Timeout(timeout=None, connect=30, read=t, write=t, pool=None)

# ---------------------------
# Validation
# ---------------------------

def _is_valid_summary(s: str) -> bool:
    """
    요약 유효성: 빈 값 / 20자 미만 / 영문 에러 토큰 포함 시 실패
    (한국어 '오류' 등은 오탐 방지 위해 미포함)
    """
    if not s:
        return False
    t = s.strip()
    if len(t) < 20:
        return False
    bad = ["error", "failed", "exception", "traceback"]
    return not any(b in t.lower() for b in bad)

# ---------------------------
# Utilities
# ---------------------------

def _clip_for_prompt(src: str, width: int = 8000) -> str:
    """프롬프트에 넣기 전 안전하게 자르기"""
    return textwrap.shorten(src, width=width, placeholder=" ...")

def _clip_for_heavy_input(src: str) -> str:
    """입력이 과도하게 긴 경우 앞/뒤만 남겨 LLM에 전달"""
    if len(src) <= 200_000:
        return src
    return src[:120_000] + "\n...[중략]...\n" + src[-60_000:]

def _extract_chat_content(json_obj: dict) -> str:
    """
    Ollama /api/chat 표준:
      {"message":{"role":"assistant","content":"..."}}
    혹시 모를 호환 포맷(OpenAI choices 유사)도 보정.
    """
    msg = (json_obj.get("message") or {})
    content = (msg.get("content") or "").strip()
    if content:
        return content
    # 호환: choices[0].message.content
    choices = json_obj.get("choices")
    if isinstance(choices, list) and choices:
        m = (choices[0].get("message") or {})
        return (m.get("content") or "").strip()
    return ""

# ---------------------------
# Ollama Calls (chat / generate)
# ---------------------------

def _call_ollama_chat(text: str) -> str:
    """
    Ollama /api/chat 호출 (단발, 스트림 X).
    - 성공 시 content 문자열
    - 실패/예외 시 빈 문자열
    - 상세 로깅 + 12초 고정 패턴 의심 신호 기록
    """
    host = _env_host()
    model = _env_model()
    timeout = _httpx_timeout()

    base_prompt = (
        "아래 문서를 간결하게 한글로 요약해줘.\n"
        "- 문단 3~6줄로 핵심만.\n"
        "- 목록/헤더/부제목 없이 요약 본문만 출력.\n"
    )
    prompt = f"{base_prompt}{_clip_for_prompt(text)}\n"
    data = {"model": model, "messages":[{"role":"user","content":prompt}], "stream": False}

    log.info("[ollama/chat] host=%s model=%s timeout(read)=%ss connect=30s",
             host, model, timeout.read)

    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(f"{host}/api/chat", json=data, headers={"Content-Type":"application/json"})
        elapsed = time.monotonic() - t0

        suspected = "timeboxed_~12s" if 9.0 <= elapsed <= 13.0 else None

        content = ""
        try:
            js = r.json()
            content = _extract_chat_content(js)
        except Exception as jex:
            # JSON 파싱 실패 시 text 그대로
            log.warning("[ollama/chat] JSON parse failed: %s", jex)
            content = (r.text or "").strip()

        log.info(
            "[ollama/chat] status=%s elapsed=%.3fs len=%s suspected=%s head=%r tail=%r",
            getattr(r, "status_code", "?"),
            elapsed,
            len(content) if content else 0,
            suspected,
            content[:160] if content else "",
            content[-160:] if content else "",
        )
        r.raise_for_status()  # HTTP 에러는 여기서 예외 발생
        return content or ""

    except httpx.TimeoutException as tex:
        elapsed = time.monotonic() - t0
        log.error("[ollama/chat] timeout after %.3fs: %s", elapsed, tex)
        return ""
    except httpx.HTTPStatusError as hse:
        elapsed = time.monotonic() - t0
        log.error("[ollama/chat] http status error after %.3fs: %s", elapsed, hse)
        return ""
    except httpx.RequestError as rex:
        elapsed = time.monotonic() - t0
        log.error("[ollama/chat] request error after %.3fs: %s", elapsed, rex)
        return ""

def _call_ollama_generate(text: str) -> str:
    """
    Ollama /api/generate 호출 (백업 경로).
    - 성공 시 response 문자열
    - 실패/예외 시 빈 문자열
    - 상세 로깅 + 12초 고정 패턴 의심 신호 기록
    """
    host = _env_host()
    model = _env_model()
    timeout = _httpx_timeout()

    prompt = f"문서 요약:\n\n{_clip_for_prompt(text)}"
    data = {"model": model, "prompt": prompt, "stream": False}

    log.info("[ollama/generate] host=%s model=%s timeout(read)=%ss connect=30s",
             host, model, timeout.read)

    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(f"{host}/api/generate", json=data, headers={"Content-Type":"application/json"})
        elapsed = time.monotonic() - t0

        suspected = "timeboxed_~12s" if 9.0 <= elapsed <= 13.0 else None

        content = ""
        try:
            js = r.json()
            content = (js.get("response","") or "").strip()
        except Exception as jex:
            log.warning("[ollama/generate] JSON parse failed: %s", jex)
            content = (r.text or "").strip()

        log.info(
            "[ollama/generate] status=%s elapsed=%.3fs len=%s suspected=%s head=%r tail=%r",
            getattr(r, "status_code", "?"),
            elapsed,
            len(content) if content else 0,
            suspected,
            content[:160] if content else "",
            content[-160:] if content else "",
        )
        r.raise_for_status()
        return content or ""

    except httpx.TimeoutException as tex:
        elapsed = time.monotonic() - t0
        log.error("[ollama/generate] timeout after %.3fs: %s", elapsed, tex)
        return ""
    except httpx.HTTPStatusError as hse:
        elapsed = time.monotonic() - t0
        log.error("[ollama/generate] http status error after %.3fs: %s", elapsed, hse)
        return ""
    except httpx.RequestError as rex:
        elapsed = time.monotonic() - t0
        log.error("[ollama/generate] request error after %.3fs: %s", elapsed, rex)
        return ""

# ---------------------------
# Summarize (public)
# ---------------------------

def summarize_with_ollama(text: str, retries: int = 2):
    """
    반환: (summary: str, ok: bool, meta: dict)
      meta 예시:
        {
          "perf": [{"name":"llm","ms": 12034}],
          "llm_meta": {"attempts": 2, "last_reason": "retry_too_short_or_error_token", "elapsed_sum": 12.1},
          "error": "...(있을 경우)"
        }
    - 1차: /chat
    - 유효성 실패 시: /generate
    - 여전히 실패 시: 길이 가이드 강화 후 재시도
    """
    t0 = time.monotonic()
    last_err = None
    attempts = 0
    elapsed_sum = 0.0
    last_reason = None

    # 입력 과다 시 앞/뒤만 남기기
    text = _clip_for_heavy_input(text)

    def _try_chat_then_generate(src: str) -> str:
        """chat 먼저, 실패하면 generate 백업 경로"""
        out = _call_ollama_chat(src)
        if not _is_valid_summary(out):
            out = _call_ollama_generate(src)
        return out or ""

    # 1차 시도
    t1 = time.monotonic()
    summary = _try_chat_then_generate(text)
    elapsed_sum += (time.monotonic() - t1)
    attempts += 1

    if _is_valid_summary(summary):
        ms = int((time.monotonic() - t0) * 1000)
        return summary, True, {
            "perf":[{"name":"llm", "ms": ms}],
            "llm_meta": {"attempts": attempts, "last_reason": None, "elapsed_sum": round(elapsed_sum, 3)}
        }

    last_reason = "too_short_or_error_token" if summary else "empty_or_transport_error"

    # 재시도 루프 (기본 2회 → 총 3번 기회)
    for i in range(retries):
        # 길이 가이드 강하게
        strong_hint = (
            "아래 문서를 간결하게 한글로 요약해줘.\n"
            "- 문단 3~6줄, 최소 200자 이상.\n"
            "- 목록/헤더/부제목 없이 한 단락의 요약만 출력.\n"
        )
        prompt_src = f"{strong_hint}{_clip_for_prompt(text)}\n"

        try:
            t2 = time.monotonic()
            summary2 = _try_chat_then_generate(prompt_src)
            elapsed_sum += (time.monotonic() - t2)
            attempts += 1

            if _is_valid_summary(summary2):
                ms = int((time.monotonic() - t0) * 1000)
                return summary2, True, {
                    "perf":[{"name":"llm", "ms": ms}],
                    "llm_meta": {"attempts": attempts, "last_reason": None, "elapsed_sum": round(elapsed_sum, 3)}
                }

            last_reason = "retry_too_short_or_error_token" if summary2 else "retry_empty_or_transport_error"
            summary = summary2  # 마지막 응답 유지
        except Exception as e:
            last_err = e
            attempts += 1
            # 단순 backoff
            time.sleep(2 * (i + 1))

    ms_total = int((time.monotonic() - t0) * 1000)
    meta = {
        "perf":[{"name":"llm", "ms": ms_total}],
        "llm_meta": {"attempts": attempts, "last_reason": last_reason, "elapsed_sum": round(elapsed_sum, 3)}
    }
    if last_err:
        meta["error"] = str(last_err)

    return "[LLM 오류: 요약 생성 실패]", False, meta
