import re
import unicodedata

_BRACKETED_TEXT_RE = re.compile(r"[\[\(（【].*?[\]\)）】]")
_PUNCTUATION_RE = re.compile(r"[^\w가-힣]+", re.UNICODE)


def normalize_answer(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = _BRACKETED_TEXT_RE.sub(" ", normalized)
    normalized = normalized.casefold()
    normalized = _PUNCTUATION_RE.sub(" ", normalized)
    return "".join(normalized.split())
