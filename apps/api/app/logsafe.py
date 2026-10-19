"""Log hygiene. Anything that came from a request or a token goes through clean() before it is written to a log line."""


def clean(value: object, limit: int = 80) -> str:
    """A bounded, single-line form of a value: control characters (including line breaks) become '?', so a crafted value
    cannot forge extra log lines."""
    return "".join(ch if ch.isprintable() else "?" for ch in str(value))[:limit]


def one_of(value: str, allowed: tuple[str, ...]) -> str:
    """`value` as it appears in a closed set (or '?'): what is logged is the constant, never the caller's string."""
    return next((a for a in allowed if a == value), "?")
