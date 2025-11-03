# backend/app/core/ocr_engine.py
import time
import re
import fitz
import pytesseract
from PIL import Image, ImageOps, ImageFilter

# --- sumflow 환경 호환 import 어댑터 ---
from app.core.config import (
    OCR_DPI, OCR_LANGS, OCR_PSM, TESSDATA_PREFIX
)
import os

# merge 엔진이 기대하는 별칭값을 sumflow 환경값 기반으로 생성
OCR_TEXTLAYER_FIRST = int(os.getenv("OCR_TEXTLAYER_FIRST", "1"))
OCR_UPSCALE = int(os.getenv("OCR_UPSCALE", "0"))
OCR_DESKEW = int(os.getenv("OCR_DESKEW", "0"))

# sumflow OCR_LANGS(e.g. "kor+eng")를 1차/2차로 분리
_langs = (OCR_LANGS or "kor+eng").split("+", 1)
OCR_LANG = _langs[0]
OCR_LANG_SECONDARY = _langs[1] if len(_langs) > 1 else ""

OCR_USER_DPI = OCR_DPI
OCR_PSM_DEFAULT = OCR_PSM
# ---------------------------------------

HANGUL_RE = re.compile(r"[가-힣]")


def _deskew_like(g: Image.Image) -> Image.Image:
    """
    PIL만으로는 강력한 deskew가 어렵기 때문에, 여기서는 no-op로 둠.
    (추후 ImageMagick 등 외부 호출을 도입하면 교체 가능)
    """
    return g


def _preprocess(img: Image.Image) -> Image.Image:
    """
    흑백 -> 자동대비 -> 임계 -> 미디안 -> (선택) 간이 디스큐 -> (선택) 업스케일
    """
    g = ImageOps.grayscale(img)
    g = ImageOps.autocontrast(g)
    g = g.point(lambda x: 255 if x > 180 else 0)
    g = g.filter(ImageFilter.MedianFilter(size=3))

    if OCR_DESKEW:
        g = _deskew_like(g)

    if OCR_UPSCALE and OCR_UPSCALE > 1.0:
        w, h = g.size
        g = g.resize((int(w * OCR_UPSCALE), int(h * OCR_UPSCALE)))

    return g


def _stats(text: str):
    n = len(text or "")
    h = len(HANGUL_RE.findall(text or ""))
    return {
        "chars": n,
        "hangul_ratio": round((h / n), 3) if n else 0.0,
    }


def _avg_conf(pil_img: Image.Image, lang: str, psm: int) -> float | None:
    """
    pandas 없이 동작하도록 Output.DICT 사용.
    psm을 호출 시점과 일치시키기 위해 config에 반영.
    """
    try:
        data = pytesseract.image_to_data(
            pil_img,
            lang=lang,
            config=f"--oem 1 --psm {psm}",
            output_type=pytesseract.Output.DICT,
        )
        confs = []
        for c in data.get("conf", []):
            try:
                v = float(c)
                if v >= 0:
                    confs.append(v)
            except Exception:
                pass
        if not confs:
            return None
        return round(sum(confs) / len(confs), 2)
    except Exception:
        return None


def _has_sufficient_text_layer(page: fitz.Page, min_chars: int = 40) -> tuple[bool, str]:
    """
    텍스트 레이어가 존재하고 일정 길이 이상이면 (True, text) 반환.
    너무 짧은 잡음은 False.
    """
    try:
        t = page.get_text("text") or ""
        t = t.strip()
        if len(t) >= min_chars:
            return True, t
        return False, ""
    except Exception:
        return False, ""


def extract_text_from_pdf(file_path: str, lang: str | None = None):
    """
    PDF -> (텍스트 레이어 우선) -> 이미지 렌더링 -> OCR
    -> (text, meta) 반환
    meta: { perf: [{name, ms}], pages, ocr_stats{chars, hangul_ratio, avg_conf} }
    """
    t0 = time.perf_counter()
    text_chunks: list[str] = []
    confs: list[float] = []
    perf: list[dict] = []
    pages = 0

    use_lang_primary = lang or OCR_LANG
    use_lang_retry = OCR_LANG_SECONDARY
    psm_primary = OCR_PSM_DEFAULT
    psm_retry = 11 if psm_primary == 6 else 6

    # Tesseract 환경(커스텀 데이터 경로 필요시)
    if TESSDATA_PREFIX:
        os.environ["TESSDATA_PREFIX"] = TESSDATA_PREFIX

    # 0) 텍스트 레이어 우선 추출
    try:
        with fitz.open(file_path) as doc:
            pages = len(doc)
            if OCR_TEXTLAYER_FIRST:
                t_start = time.perf_counter()
                for p in doc:
                    ok, tl = _has_sufficient_text_layer(p)
                    if ok:
                        text_chunks.append(tl)
                perf.append(
                    {
                        "name": "textlayer_extract",
                        "ms": int((time.perf_counter() - t_start) * 1000),
                    }
                )
                if any(t.strip() for t in text_chunks):
                    # 텍스트 레이어만으로 충분
                    text = "\n\n".join(text_chunks).strip()
                    meta = {
                        "perf": perf + [{"name": "ocr", "ms": int((time.perf_counter() - t0) * 1000)}],
                        "pages": pages,
                        "ocr_stats": {**_stats(text), "avg_conf": None},
                    }
                    return text, meta
    except Exception:
        # 텍스트 레이어 단계 오류는 무시하고 OCR로 진행
        pass

    # 1) 1차 OCR: DPI=OCR_USER_DPI, psm=psm_primary, lang=use_lang_primary
    with fitz.open(file_path) as doc:
        t_render0 = time.perf_counter()
        for p in doc:
            pix = p.get_pixmap(dpi=OCR_USER_DPI)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            g = _preprocess(img)
            t_ocr = time.perf_counter()
            text = pytesseract.image_to_string(
                g, lang=use_lang_primary, config=f"--oem 1 --psm {psm_primary}"
            )
            if text and text.strip():
                text_chunks.append(text)
            c = _avg_conf(g, use_lang_primary, psm_primary)
            if c is not None:
                confs.append(c)
        perf.append({"name": f"render+ocr:psm{psm_primary}:{use_lang_primary}", "ms": int((time.perf_counter() - t_render0) * 1000)})

    # 2) 폴백(필요할 때만 1회): 결과가 빈/매우 짧으면 lang/psm 교체
    if not any(t.strip() for t in text_chunks):
        with fitz.open(file_path) as doc:
            t_render1 = time.perf_counter()
            for p in doc:
                pix = p.get_pixmap(dpi=max(240, OCR_USER_DPI))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                g = _preprocess(img)
                text = pytesseract.image_to_string(
                    g, lang=use_lang_retry, config=f"--oem 1 --psm {psm_retry}"
                )
                if text and text.strip():
                    text_chunks.append(text)
                c = _avg_conf(g, use_lang_retry, psm_retry)
                if c is not None:
                    confs.append(c)
            perf.append({"name": f"retry:psm{psm_retry}:{use_lang_retry}", "ms": int((time.perf_counter() - t_render1) * 1000)})

    # 3) 메타 조립
    text = "\n\n".join(text_chunks).strip()
    meta = {
        "perf": perf + [{"name": "ocr", "ms": int((time.perf_counter() - t0) * 1000)}],
        "pages": pages,
        "ocr_stats": {
            **_stats(text),
            "avg_conf": (round(sum(confs) / len(confs), 2) if confs else None),
        },
    }
    return text, meta
