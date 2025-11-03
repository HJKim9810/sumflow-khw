from pathlib import Path
from typing import Tuple
from core.config import OUTPUT_ROOT, EXPORT_ROOT

EXT_PDF   = {".pdf"}
EXT_IMG   = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
EXT_DOCX  = {".docx"}
EXT_PPTX  = {".pptx"}
EXT_XLSX  = {".xlsx", ".xlsm"}
EXT_HWP   = {".hwp", ".hwpx"}

def classify_ext(p: str) -> str:
    ext = Path(p).suffix.lower()
    if ext in EXT_PDF: return "pdf"
    if ext in EXT_IMG: return "image"
    if ext in EXT_DOCX: return "docx"
    if ext in EXT_PPTX: return "pptx"
    if ext in EXT_XLSX: return "xlsx"
    if ext in EXT_HWP: return "hwp"
    return "unknown"

def file_outdir(file_id: str) -> Path:
    d = OUTPUT_ROOT / file_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def export_zip_path(batch_id: str) -> Path:
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    return EXPORT_ROOT / f"batch_{batch_id}.zip"

def ensure_subdirs(base: Path):
    (base/"llm").mkdir(exist_ok=True)
    return base

def io_targets(base: Path) -> Tuple[Path, Path, Path, Path, Path]:
    # original, merged.txt, summary.txt, meta.json, log.txt
    return (
        base/"original.ext",
        base/"merged.txt",
        base/"llm"/"summary.txt",
        base/"meta.json",
        base/"log.txt",
    )