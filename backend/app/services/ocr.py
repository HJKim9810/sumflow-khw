from __future__ import annotations
# merge 엔진(격리 복사본) 사용
from ..thirdparty.merge_core.ocr_engine import extract_text_from_pdf

import os, io, zipfile, shutil,json
from pathlib import Path
from typing import List, Dict, Tuple, Iterator
from datetime import datetime
import fitz  # PyMuPDF
from PIL import Image, ImageOps, ImageFilter
import pytesseract
from pytesseract import Output

# ============================================================
# 설정 로드 (core/config.py 기반)
# ============================================================
try:
    from ..core.config import (
        TESSERACT_CMD,
        TESSDATA_PREFIX,
        OCR_DPI,
        OCR_LANGS,
        OCR_PSM,
        OCR_PREP_MODE,
    )
except Exception:
    TESSERACT_CMD = None
    TESSDATA_PREFIX = None
    OCR_DPI = 300
    OCR_LANGS = ""
    OCR_PSM = "6"
    OCR_PREP_MODE = "quality"

# ============================================================
# Tesseract 설정
# ============================================================
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
elif shutil.which("tesseract"):
    pytesseract.pytesseract.tesseract_cmd = shutil.which("tesseract")
else:
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

if TESSDATA_PREFIX:
    os.environ["TESSDATA_PREFIX"] = TESSDATA_PREFIX

_TEXTLAYER_MIN_CHARS = int(os.getenv("OCR_TEXTLAYER_MIN_CHARS", "60"))
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

# ============================================================
# 내부 유틸
# ============================================================
def _has_traineddata(lang_code: str) -> bool:
    fname = f"{lang_code}.traineddata"
    prefix = (os.environ.get("TESSDATA_PREFIX") or "").rstrip("\\/")
    if prefix and (Path(prefix) / fname).exists():
        return True
    win_default = Path(r"C:\Program Files\Tesseract-OCR\tessdata") / fname
    return win_default.exists()

def _best_langs(spec: str | None) -> str:
    spec = (spec or "").strip()
    if spec:
        return spec
    return "kor+eng" if _has_traineddata("kor") else "eng"

def _pick_mode(mode: str | None) -> str:
    m = (mode or OCR_PREP_MODE or "quality").lower()
    return "fast" if m.startswith("fast") else "quality"

def _tess_cfg(psm: str | int) -> str:
    psm = str(psm).strip() if str(psm).strip().isdigit() else "6"
    return f"--psm {psm} --oem 1 -c preserve_interword_spaces=1"

def _render_pdf_page(page: "fitz.Page", dpi: int) -> Image.Image:
    dpi = max(72, min(600, int(dpi)))
    scale = dpi / 72.0
    m = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=m, alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")

def _preprocess_for_ocr(img: Image.Image, mode: str) -> Image.Image:
    im = ImageOps.exif_transpose(img)
    g = ImageOps.grayscale(im)
    g = ImageOps.autocontrast(g, cutoff=1)
    if mode == "quality":
        g = g.filter(ImageFilter.UnsharpMask(radius=1.0, percent=120, threshold=4))
    return g

def _ocr_pil(pil_img: Image.Image, langs: str, psm: str | int) -> Tuple[Dict, str]:
    cfg = _tess_cfg(psm)
    data = pytesseract.image_to_data(pil_img, lang=langs, config=cfg, output_type=Output.DICT)
    text = pytesseract.image_to_string(pil_img, lang=langs, config=cfg)
    return data, text

# ============================================================
# OCR 핵심
# ============================================================
def ocr_funnel_extract(
    content: bytes,
    filename: str = "file",
    mode: str = "quality",
) -> Tuple[str, int, Dict, List[Dict]]:
    """
    텍스트 레이어 있으면 우선 사용, 부족하면 렌더+Tesseract.
    """
    mode = _pick_mode(mode)
    lang = _best_langs(OCR_LANGS)
    psm = OCR_PSM
    dpi = int(OCR_DPI)

    per_page: List[Dict] = []
    full_texts: List[str] = []
    pages = 0

    is_pdf = filename.lower().endswith(".pdf") or content[:4] == b"%PDF"
    if is_pdf:
        with fitz.open(stream=content, filetype="pdf") as doc:
            for page in doc:
                pages += 1
                layer_text = (page.get_text("text") or "").strip()
                has_text_layer = len(layer_text) >= _TEXTLAYER_MIN_CHARS
                if has_text_layer:
                    text = layer_text
                else:
                    img = _render_pdf_page(page, dpi=dpi)
                    pre = _preprocess_for_ocr(img, mode)
                    _, text = _ocr_pil(pre, langs=lang, psm=psm)
                per_page.append({"index": pages - 1, "has_text": has_text_layer, "text": text})
                full_texts.append(text)
    else:
        pages = 1
        img = Image.open(io.BytesIO(content)).convert("RGB")
        pre = _preprocess_for_ocr(img, mode)
        _, text = _ocr_pil(pre, langs=lang, psm=psm)
        per_page.append({"index": 0, "has_text": False, "text": text})
        full_texts.append(text)

    used_text = sum(1 for p in per_page if (p["text"] or "").strip())
    meta = {
        "mode": mode,
        "dpi": dpi,
        "lang": lang,
        "text_layer_pages": sum(1 for p in per_page if p["has_text"]),
        "coverage": used_text / max(1, pages),
    }
    return "\n".join(full_texts), pages, meta, per_page

# ============================================================
# ZIP 일괄 OCR
# ============================================================
def batch_ocr_zip(zip_bytes: bytes) -> Iterator[Tuple[str, str, int]]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
        for name in z.namelist():
            if name.endswith("/"):
                continue
            base = os.path.basename(name)
            if not base or base.lower() in (".ds_store", "thumbs.db"):
                continue
            data = z.read(name)
            text, pages, *_ = ocr_funnel_extract(data, filename=name, mode="quality")
            yield name, text, pages

def _result_root() -> Path:
    """
    결과물 루트 디렉터리.
    ENV RESULT_ROOT 가 있으면 그 경로 사용, 없으면 ./data/results
    """
    base = os.getenv("RESULT_ROOT", "./data/results")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p

def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")

def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def run_ocr(file_path: Path, file_id: str, *, prep_mode: str | None = None) -> Dict:
    """
    단일 파일(PDF/이미지)에 대해 OCR/텍스트레이어 추출을 수행하고
    결과물을 {RESULT_ROOT}/{file_id}/ 에 저장한다.

    Returns:
        {
          "out_dir": str,   # 결과 디렉터리
          "pages": int,     # 페이지 수
          "meta": dict      # 메타데이터(커버리지 등)
        }
    """
    if not file_path.exists():
        raise FileNotFoundError(f"run_ocr: file not found: {file_path}")

    out_dir = _result_root() / file_id
    pages_dir = out_dir / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)

    data = file_path.read_bytes()
    filename = file_path.name
    is_pdf = filename.lower().endswith(".pdf") or data[:4] == b"%PDF"

    if is_pdf:
        # === merge 코어 OCR 사용 ===
        # returns: (text, meta_merge)  where meta_merge = {"perf":[...], "pages":int, "ocr_stats":{...}}
        text, meta_merge = extract_text_from_pdf(str(file_path))
        pages = int(meta_merge.get("pages") or 0)

        # sumflow 메타 스키마에 맞춰 최소 필드만 매핑 (나머지는 None 허용)
        lang = _best_langs(OCR_LANGS)
        meta = {
            "mode": "merge_core",     # 엔진 식별
            "dpi": int(OCR_DPI),
            "lang": lang,
            "text_layer_pages": None, # merge 메타에 직접 없음
            "coverage": None,         # merge 메타에 직접 없음
        }
        per_page = []  # merge 경로에선 페이지별 텍스트 분리는 제공하지 않음
    else:
        # === 기존 파이프라인 유지 ===
        text, pages, meta, per_page = ocr_funnel_extract(
            data,
            filename=filename,
            mode=(prep_mode or OCR_PREP_MODE or "quality"),
        )


    # 페이지별 개별 저장
    for p in per_page:
        idx = int(p.get("index", 0))
        page_text = p.get("text", "") or ""
        _write_text(pages_dir / f"page_{idx:03d}.txt", page_text)

        # 병합본 저장
    # 읽기 편하도록 페이지 경계 구분선 넣어줌
    if per_page:  # 페이지별 텍스트가 있을 때(기존 경로)
        merged_lines: List[str] = []
        total = max(1, pages)
        for p in per_page:
            idx = int(p.get("index", 0))
            merged_lines.append(f"\n==== [PAGE {idx+1}/{total}] ====\n")
            merged_lines.append(p.get("text", "") or "")
        merged_text = "\n".join(merged_lines).lstrip()
    else:
        # merge 경로: 페이지별 분리 정보가 없으므로 raw text를 그대로 쓴다
        merged_text = (text or "").strip()


    _write_text(out_dir / "merged.txt", merged_text)

    # 메타 저장 (파일 정보 + 파라미터 + 품질 지표)
    meta_out = {
        "file_id": file_id,
        "filename": filename,
        "pages": pages,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "ocr": {
            "mode": meta.get("mode"),
            "dpi": meta.get("dpi"),
            "lang": meta.get("lang"),
            "text_layer_pages": meta.get("text_layer_pages"),
            "coverage": meta.get("coverage"),
            "psm": (OCR_PSM if isinstance(OCR_PSM, str) else str(OCR_PSM)),
        },
        "paths": {
            "out_dir": str(out_dir),
            "merged_txt": "merged.txt",
            "pages_dir": "pages/",
            "summary_dir": "llm/",   # 다음 단계에서 사용 (llm_gpu_task)
            "meta_json": "meta.json",
        },
    }
    _write_json(out_dir / "meta.json", meta_out)

    return {
        "out_dir": str(out_dir),
        "pages": pages,
        "meta": meta_out,
    }
