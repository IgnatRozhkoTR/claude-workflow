"""Internationalization support for workspace messages."""
import json
from pathlib import Path

_cache = {}
_MESSAGES_DIR = Path(__file__).parent.parent / "messages"


def _load(locale):
    path = _MESSAGES_DIR / f"{locale}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def t(key, locale="en", **params):
    """Translate a message key to the given locale with parameter interpolation.

    Falls back to English if key not found in target locale.
    Falls back to the key itself if not found in English either.
    """
    if locale not in _cache:
        _cache[locale] = _load(locale)
    if "en" not in _cache:
        _cache["en"] = _load("en")

    msg = _cache.get(locale, {}).get(key) or _cache.get("en", {}).get(key) or key
    for k, v in params.items():
        msg = msg.replace(f"{{{k}}}", str(v))
    return msg


def reload():
    """Clear cache, forcing reload on next t() call."""
    _cache.clear()
