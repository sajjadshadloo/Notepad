import unicodedata


def is_rtl_char(ch: str) -> bool:
    try:
        bidi = unicodedata.bidirectional(ch)
        return bidi in ('R', 'AL', 'RLE', 'RLO', 'RLI', 'AN')
    except Exception:
        return False


def detect_direction(text: str, default: str = "rtl") -> str:
    rtl_count = 0
    ltr_count = 0
    for ch in text:
        if ch.strip() == '':
            continue
        if is_rtl_char(ch):
            rtl_count += 1
        elif unicodedata.bidirectional(ch) in ('L', 'LRE', 'LRO', 'LRI'):
            ltr_count += 1
    if rtl_count == 0 and ltr_count == 0:
        return default
    return 'rtl' if rtl_count >= ltr_count else 'ltr'
