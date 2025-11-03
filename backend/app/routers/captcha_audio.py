from fastapi import APIRouter, HTTPException, Response, Query
import io
import re
from gtts import gTTS
from backend.app.services.captcha import captcha_store  

router = APIRouter(prefix="/api/v1/captcha", tags=["Captcha"])

def resolve_captcha_text(captcha_id: str) -> str:
    val = None
    # dict/get 대응
    if isinstance(captcha_store, dict):
        val = captcha_store.get(captcha_id)

    # 타입별 추출
    text = ""
    if isinstance(val, tuple) and len(val) >= 1:
        # (code, expire)
        text = str(val[0])
    elif isinstance(val, dict):
        # 혹시 다른 구조로 저장됐다면 흔한 키 후보에서 추출
        for k in ("text", "answer", "captcha", "code", "value"):
            if k in val and val[k]:
                text = str(val[k])
                break
    elif isinstance(val, (bytes, bytearray)):
        text = val.decode("utf-8", "ignore")
    elif isinstance(val, (str, int, float)):
        text = str(val)

    # 정제: 영문/숫자/한글만 남기고, 캡챠 길이에 맞게 자르기 (기본 5자)
    clean = re.findall(r"[0-9A-Za-z가-힣]", text or "")
    code = "".join(clean)
    code = code[:5]  # 네 캡챠가 6자면 6으로 변경
    return code

@router.get("/audio")
def captcha_audio(captcha_id: str = Query(...)):
    code = resolve_captcha_text(captcha_id)
    if not code or len(code) < 3:
        raise HTTPException(status_code=404, detail="Invalid captcha_id")

    speak = " ".join(list(code))

    buf = io.BytesIO()
    gTTS(text=speak, lang="ko").write_to_fp(buf)
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )