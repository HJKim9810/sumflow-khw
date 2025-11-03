import base64
import io
import random
import string
import time
import uuid
import re
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from fastapi import APIRouter, HTTPException, Response, Query
from pydantic import BaseModel
from gtts import gTTS

router = APIRouter(prefix="/api/v1/captcha", tags=["Captcha"])

# ----------------------------------------
# 1️⃣ CAPTCHA 저장소 (메모리 캐시)
# ----------------------------------------
# 구조: {captcha_id: (code, expire_time)}
captcha_store = {}
CAPTCHA_TTL = 120  # 초 (2분)

# ----------------------------------------
# 2️⃣ CAPTCHA 텍스트 생성
# ----------------------------------------
def generate_code(length=5):
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))

# ----------------------------------------
# 3️⃣ CAPTCHA 이미지 생성
# ----------------------------------------
def generate_captcha_image(code: str):
    width, height = 160, 60
    image = Image.new("RGB", (width, height), (255, 255, 255))
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(image)
    for i, char in enumerate(code):
        x = 20 + i * 25 + random.randint(-5, 5)
        y = random.randint(5, 10)
        draw.text(
            (x, y),
            char,
            fill=(
                random.randint(0, 150),
                random.randint(0, 150),
                random.randint(0, 150),
            ),
            font=font,
        )
    for _ in range(3):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line(
            ((x1, y1), (x2, y2)),
            fill=(
                random.randint(150, 255),
                random.randint(150, 255),
                random.randint(150, 255),
            ),
            width=2,
        )
    image = image.filter(ImageFilter.GaussianBlur(0.8))
    return image

# ----------------------------------------
# 4️⃣ CAPTCHA 생성 API
# ----------------------------------------
@router.get("/")
def get_captcha():
    code = generate_code()
    captcha_id = str(uuid.uuid4())
    expire = time.time() + CAPTCHA_TTL

    captcha_store[captcha_id] = (code, expire)

    image = generate_captcha_image(code)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {"captcha_id": captcha_id, "image_base64": image_base64}

# ----------------------------------------
# 5️⃣ CAPTCHA 검증 API
# ----------------------------------------
class CaptchaVerifyRequest(BaseModel):
    captcha_id: str
    user_input: str

@router.post("/verify")
def verify_captcha(data: CaptchaVerifyRequest):
    record = captcha_store.get(data.captcha_id)
    if not record:
        raise HTTPException(
            status_code=400,
            detail="보안문자 정보가 존재하지 않거나 만료되었습니다. 새로 고침 후 다시 시도해주세요."
        )

    code, expire_time = record
    if time.time() > expire_time:
        del captcha_store[data.captcha_id]
        raise HTTPException(
            status_code=400,
            detail="보안문자 입력 시간이 초과되었습니다. 새로 고침 후 다시 시도해주세요."
        )

    if data.user_input.strip().lower() != code.lower():
        raise HTTPException(
            status_code=400,
            detail="보안문자가 올바르지 않습니다. 다시 입력해주세요."
        )

    del captcha_store[data.captcha_id]
    return {"success": True, "message": "보안문자 인증이 완료되었습니다."}

# ----------------------------------------
# 6️⃣ CAPTCHA 오디오 API (gTTS)
# ----------------------------------------
def _resolve_captcha_text(store: dict, captcha_id: str) -> str:
    """captcha_store에서 (code, expire) 형태를 지원하도록 정제"""
    val = None
    try:
        if isinstance(store, dict):
            val = store.get(captcha_id)
    except Exception:
        val = None

    text = ""
    if isinstance(val, tuple) and len(val) >= 1:
        # (code, expire)
        text = str(val[0])
    elif isinstance(val, dict):
        for k in ("text", "answer", "captcha", "code", "value"):
            if k in val and val[k]:
                text = str(val[k])
                break
    elif isinstance(val, (bytes, bytearray)):
        text = val.decode("utf-8", "ignore")
    elif isinstance(val, (str, int, float)):
        text = str(val)

    # 영문/숫자만 필터링
    clean = re.findall(r"[0-9A-Za-z가-힣]", text or "")
    code = "".join(clean)
    code = code[:5]  # 캡챠 길이에 맞게 조정
    return code

@router.get("/audio")
def captcha_audio(captcha_id: str = Query(...)):
    code = _resolve_captcha_text(captcha_store, captcha_id)
    if not code or len(code) < 3:
        raise HTTPException(status_code=404, detail="Invalid captcha_id")

    speak = " ".join(list(code))  # 각 글자 사이 공백
    buf = io.BytesIO()
    gTTS(text=speak, lang="ko").write_to_fp(buf)
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )