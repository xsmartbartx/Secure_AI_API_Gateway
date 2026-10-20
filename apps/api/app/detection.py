"""Looks for sensitive data and prompt-injection phrases in the text of a call, so an organization's policy can flag, mask or
block it before it reaches a model provider.

These are pattern checks, not a guarantee. Structured values (card numbers, IBANs, PESEL) are validated with their check digits
to keep false positives low; secrets and injection phrases are recognised by their shape or wording and can be missed or
over-matched. Every pattern is bounded so scanning stays linear on hostile input. Matched text is never stored or logged."""
import re
from dataclasses import dataclass, field

MAX_SCAN_CHARS = 2_000_000  # per call; bigger requests cannot be inspected within a sane time

ALL_DETECTORS = ("email", "card", "iban", "pesel", "aws_key", "api_key", "jwt", "private_key")
CATEGORY = {"email": "pii", "pesel": "pii", "card": "financial", "iban": "financial",
            "aws_key": "secret", "api_key": "secret", "jwt": "secret", "private_key": "secret"}
SCORE = {"email": 30, "pesel": 70, "iban": 70, "card": 80, "jwt": 60, "api_key": 85, "aws_key": 85, "private_key": 90}
LABEL = {"email": "email address", "card": "payment card number", "iban": "IBAN", "pesel": "PESEL number", "aws_key": "AWS access key",
         "api_key": "API key", "jwt": "JSON web token", "private_key": "private key"}
INJECTION_LABEL = {"ignore_instructions": "instruction override", "reveal_prompt": "system prompt extraction", "role_override": "role override",
                   "persona_jailbreak": "jailbreak persona", "chat_markup": "chat markup injection"}
INJECTION_SCORE = 70


@dataclass(frozen=True)
class Finding:
    kind: str
    category: str   # pii | financial | secret | injection
    count: int
    score: int

    @property
    def label(self) -> str:
        return LABEL.get(self.kind) or INJECTION_LABEL.get(self.kind, self.kind)


@dataclass
class TextScan:
    findings: list[Finding] = field(default_factory=list)
    masked: str = ""
    score: int = 0


@dataclass
class MessageScan:
    findings: list[Finding]
    masked: list[str]
    score: int
    truncated: bool


# ---------- finders: each returns [(start, end)] ----------
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@(?:[A-Za-z0-9-]{1,63}\.){1,5}[A-Za-z]{2,24}\b")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_IBAN_START = re.compile(r"\b[A-Z]{2}\d{2}(?= ?[A-Z0-9])")
_PESEL = re.compile(r"(?<!\d)\d{11}(?!\d)")
_AWS = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_API = re.compile(r"\b(?:sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,200}|gh[pousr]_[A-Za-z0-9]{36,200}|xox[baprs]-[A-Za-z0-9-]{10,200}"
                  r"|AIza[0-9A-Za-z_-]{35}|[sr]k_(?:live|test)_[A-Za-z0-9]{16,200}|nx_live_[A-Za-z0-9_-]{20,200})")
_JWT = re.compile(r"\bey[A-Za-z0-9_-]{8,300}+\.[A-Za-z0-9_-]{8,2000}+\.[A-Za-z0-9_-]{8,600}+")  # possessive and bounded: linear time
_PEM = re.compile(r"-----BEGIN (?:[A-Z]{2,12} ){0,3}PRIVATE KEY-----")
_IBAN_MAX_STARTS = 2000


def _luhn(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if flip:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        flip = not flip
    return total % 10 == 0


def _find_email(t: str):
    return [m.span() for m in _EMAIL.finditer(t)]


def _find_card(t: str):
    out = []
    for m in _CARD.finditer(t):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and len(set(digits)) > 1 and _luhn(digits):
            out.append(m.span())
    return out


def _iban_ok(compact: str) -> bool:
    if not 15 <= len(compact) <= 34 or not compact.isalnum():
        return False
    moved = compact[4:] + compact[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def _find_iban(t: str):
    out, last_end = [], 0
    for i, m in enumerate(_IBAN_START.finditer(t)):
        if i >= _IBAN_MAX_STARTS:
            break
        start = m.start()
        if start < last_end:
            continue
        window = t[start:start + 50]
        best = 0
        for end in range(len(window), 14, -1):  # the longest prefix that is a valid IBAN (it may be followed by ordinary words)
            if (end == len(window) or not window[end].isalnum()) and _iban_ok(window[:end].replace(" ", "")):
                best = end
                break
        if best:
            out.append((start, start + best))
            last_end = start + best
    return out


def _pesel_ok(s: str) -> bool:
    weights = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    if (10 - sum(int(c) * w for c, w in zip(s, weights)) % 10) % 10 != int(s[10]):
        return False
    month, day = int(s[2:4]) % 20, int(s[4:6])
    return int(s[2:4]) // 20 in (0, 1, 2, 3, 4) and 1 <= month <= 12 and 1 <= day <= 31


def _find_pesel(t: str):
    return [m.span() for m in _PESEL.finditer(t) if _pesel_ok(m.group())]


FINDERS = {"email": _find_email, "card": _find_card, "iban": _find_iban, "pesel": _find_pesel,
           "aws_key": lambda t: [m.span() for m in _AWS.finditer(t)], "api_key": lambda t: [m.span() for m in _API.finditer(t)],
           "jwt": lambda t: [m.span() for m in _JWT.finditer(t)], "private_key": lambda t: [m.span() for m in _PEM.finditer(t)]}


def scan_text(text: str, detectors) -> TextScan:
    """Findings for the enabled detectors plus a copy of the text with every match replaced by [REDACTED:kind]."""
    spans: list[tuple[int, int, str]] = []
    counts: dict[str, int] = {}
    for kind in ALL_DETECTORS:
        if kind in detectors:
            for s, e in FINDERS[kind](text):
                spans.append((s, e, kind))
                counts[kind] = counts.get(kind, 0) + 1
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    pieces, pos, kept = [], 0, []
    for s, e, kind in spans:
        if s < pos:  # overlaps something already masked: one placeholder per region
            counts[kind] -= 1
            continue
        pieces.append(text[pos:s])
        pieces.append(f"[REDACTED:{kind}]")
        pos = e
        kept.append(kind)
    pieces.append(text[pos:])
    findings = [Finding(k, CATEGORY[k], n, SCORE[k]) for k, n in counts.items() if n > 0]
    return TextScan(findings, "".join(pieces), max((f.score for f in findings), default=0))


def scan_messages(contents: list[str], detectors) -> MessageScan:
    """Scan every message (system and history included) up to MAX_SCAN_CHARS in total."""
    budget, totals, masked, truncated = MAX_SCAN_CHARS, {}, [], False
    for text in contents:
        if budget <= 0:
            truncated = True
            masked.append(text)
            continue
        chunk = text[:budget]
        truncated = truncated or len(chunk) < len(text)
        budget -= len(chunk)
        r = scan_text(chunk, detectors)
        masked.append(r.masked + text[len(chunk):])
        for f in r.findings:
            totals[f.kind] = totals.get(f.kind, 0) + f.count
    findings = [Finding(k, CATEGORY[k], n, SCORE[k]) for k, n in totals.items()]
    return MessageScan(findings, masked, max((f.score for f in findings), default=0), truncated)


# ---------- prompt-injection heuristics ----------
_INJECTION = {
    "ignore_instructions": re.compile(r"\b(?:ignore|disregard|forget)\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous\s+|prior\s+|above\s+|earlier\s+)(?:instructions|prompts?|rules|directions)\b", re.I),
    "reveal_prompt": re.compile(r"\b(?:reveal|show|print|repeat|output|display|leak)\s+(?:me\s+)?(?:your\s+|the\s+)?(?:(?:hidden|secret|system|initial|original)\s+){0,2}(?:prompt|instructions)\b", re.I),
    "role_override": re.compile(r"\byou\s+are\s+now\s+(?:in\s+)?(?:dan\b|developer\s+mode|jailbroken|unrestricted|an?\s+unfiltered)", re.I),
    "persona_jailbreak": re.compile(r"\b(?:(?:enter|activate|switch\s+to)\s+(?:dan|developer)\s+mode|do\s+anything\s+now|act\s+as\s+(?:an?\s+)?(?:unrestricted|unfiltered|evil|jailbroken)\s+\w{2,12})", re.I),
    "chat_markup": re.compile(r"<\|im_(?:start|end)\|>"),
}


def scan_injection(messages: list[tuple[str, str]]) -> list[Finding]:
    """Heuristic phrase matching on user and assistant turns. System messages are the organization's own instructions
    and may legitimately contain guard phrases, so they are not scanned."""
    counts: dict[str, int] = {}
    budget = MAX_SCAN_CHARS
    for role, text in messages:
        if role == "system" or budget <= 0:
            continue
        chunk = text[:budget]
        budget -= len(chunk)
        for kind, rx in _INJECTION.items():
            n = len(rx.findall(chunk))
            if n:
                counts[kind] = counts.get(kind, 0) + n
    return [Finding(k, "injection", n, INJECTION_SCORE) for k, n in counts.items()]
