from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import shutil
from ..core.config import EXPORT_ROOT
from ..utils.paths import export_zip_path

def build_category_zip_by_documents(batch_id: str, docs: list[dict]) -> Path:
    """
    docs: [{ 'CATEGORY_NAME': '대/소', 'RESULT_FOLDER_ID': 'xxxx',
             'ORIGINAL_FILENAME': 'foo.pdf', 'BASE_DIR': '/abs/outputs/xxxx' }, ...]
    """
    zpath = (EXPORT_ROOT / f"batch_{batch_id}.zip")
    if zpath.exists(): zpath.unlink()

    with ZipFile(zpath, "w", ZIP_DEFLATED) as z:
        for d in docs:
            cat = (d.get("CATEGORY_NAME") or "미분류/기타")
            major, minor = (cat.split("/", 1) + ["기타"])[:2]
            base = Path(d["BASE_DIR"])
            stem = Path(d["ORIGINAL_FILENAME"]).stem

            # ZIP 내부 경로
            dest = Path(major) / minor / stem

            # 포함 파일만 (요구한 최소 산출만)
            for rel in ["original.ext", "merged.txt", "llm/summary.txt", "meta.json", "log.txt"]:
                p = base / rel
                if p.exists():
                    z.write(p, arcname=str(dest/rel))
    return zpath