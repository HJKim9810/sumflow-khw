import re

_DEF = "미분류/기타"
_SEP = re.compile(r"[>\-\|;,·•∙▶▷➡️→]+|\s*/\s*")
_CLEAN = re.compile(r"[()\[\]{}#*「」『』<>]")

def normalize_category(raw: str | None) -> str:
    if not raw:
        return _DEF
    s = _CLEAN.sub("", raw.strip())
    parts = [p.strip() for p in _SEP.split(s) if p.strip()]
    if len(parts) >= 2: return f"{parts[0]}/{parts[1]}"
    if len(parts) == 1: return f"{parts[0]}/기타"
    return _DEF