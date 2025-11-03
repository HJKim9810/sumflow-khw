
from collections import defaultdict

TAXONOMY = {
  "법률": {
    "공정거래": ["하도급", "기술자료 유용", "재판매가격", "공정위", "담합"],
    "금융규제": ["금융위", "여신", "대출규제", "신용정보", "금감원"],
    "노동": ["근로기준법", "노동청", "임금", "노조", "산재"],
  },
  "행정": {
    "국회/입법": ["개정안", "심사보고서", "국회", "위원회", "의안"],
    "지자체": ["조례", "시의회", "도지사", "지방세"],
  },
  "산업": {
    "제조": ["공장", "부품", "하도급", "납품", "품질검사"],
    "IT/데이터": ["데이터", "개인정보", "AI", "플랫폼", "API"],
  },
}

def parse_category(text: str) -> str:
    text_low = (text or "").lower()
    score = defaultdict(int)

    for big, subs in TAXONOMY.items():
        for small, kws in subs.items():
            for kw in kws:
                if kw.lower() in text_low:
                    score[(big, small)] += 1

    if not score:
        return "일반/기타"

    (big, small), _ = max(score.items(), key=lambda x: x[1])
    return f"{big}/{small}"
