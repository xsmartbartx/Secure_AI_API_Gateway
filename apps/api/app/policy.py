"""Per-organization policies applied to every call before it is sent upstream."""
import fnmatch
import re
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import detection
from app.db import Policy

MODEL_ALLOW = "model_allow"
MODES = ("off", "monitor", "enforce")
MAX_PATTERNS, MAX_PATTERN_LEN, MAX_WILDCARDS = 50, 100, 5
_PATTERN = re.compile(r"^[A-Za-z0-9._:/*?-]+$")  # no character classes: patterns stay simple to read and cheap to match


def normalise_patterns(raw: list[str]) -> list[str]:
    """Trim, lowercase, de-duplicate (keeping order) and validate. Raises ValueError with a message for the user."""
    out: list[str] = []
    for item in raw:
        p = item.strip().lower()
        if not p:
            continue
        if len(p) > MAX_PATTERN_LEN:
            raise ValueError(f"'{p[:20]}…' is longer than {MAX_PATTERN_LEN} characters")
        if not _PATTERN.match(p):
            raise ValueError(f"'{p}' has characters other than letters, digits and . _ : / - * ?")
        if p.count("*") > MAX_WILDCARDS:
            raise ValueError(f"'{p}' has more than {MAX_WILDCARDS} wildcards")
        if p not in out:
            out.append(p)
    if len(out) > MAX_PATTERNS:
        raise ValueError(f"at most {MAX_PATTERNS} entries")
    return out


def match(patterns: list[str], model: str) -> str | None:
    m = model.lower()
    return next((p for p in patterns if fnmatch.fnmatchcase(m, p)), None)


@dataclass
class Verdict:
    action: str  # allow | flag | block
    rule: str | None = None


async def save_policy(s: AsyncSession, org_id: str, ptype: str, mode: str, config: dict) -> int:
    """Create or update a policy and return the version this save produced.

    Two admins can save at once, and two first saves can race on the unique (org, type) constraint. The version is therefore
    incremented in SQL (`version = version + 1 ... RETURNING`) so every save gets its own number, and a first save that loses
    the race to create the row simply falls through to an update."""
    def bump():
        return (update(Policy).where(Policy.org_id == org_id, Policy.type == ptype)
                .values(mode=mode, config=config, version=Policy.version + 1).returning(Policy.version))
    version = (await s.execute(bump())).scalar_one_or_none()
    if version is None:
        try:
            async with s.begin_nested():
                s.add(Policy(org_id=org_id, type=ptype, mode=mode, config=config, version=1))
                await s.flush()
            version = 1
        except IntegrityError:  # a concurrent first save created the row between our UPDATE and INSERT
            version = (await s.execute(bump())).scalar_one()
    await s.commit()
    return version


async def load_policies(s: AsyncSession, org_id: str) -> dict[str, Policy]:
    """All of the org's policies in one query, keyed by type."""
    return {p.type: p for p in (await s.execute(select(Policy).where(Policy.org_id == org_id))).scalars()}


async def load_model_policy(s: AsyncSession, org_id: str) -> Policy | None:
    return (await load_policies(s, org_id)).get(MODEL_ALLOW)


def check_model(policies: dict[str, Policy], model: str) -> Verdict:
    pol = policies.get(MODEL_ALLOW)
    if pol is None or pol.mode == "off" or match(pol.config.get("models", []), model):
        return Verdict("allow")
    return Verdict("block" if pol.mode == "enforce" else "flag", MODEL_ALLOW)


# ---------- content policies: sensitive data (dlp) and prompt injection ----------
DLP = "dlp"
INJECTION = "injection"
EVENT_TYPE = {"pii": "dlp_pii", "financial": "dlp_financial", "secret": "dlp_secret", "injection": "prompt_injection"}


def severity(score: int) -> str:
    return "critical" if score >= 85 else "high" if score >= 70 else "medium" if score >= 40 else "low"


@dataclass
class EventSpec:
    type: str
    severity: str
    rule_id: str
    excerpt: str  # what was found and what happened, never the matched text


@dataclass
class ContentVerdict:
    action: str = "allow"                 # allow | flag | block
    events: list[EventSpec] = field(default_factory=list)
    score: int = 0
    masked: list[str] | None = None       # replacement message contents when DLP masks
    message: str = ""                     # user-facing reason when blocked


def _events(findings: list[detection.Finding], outcome: str) -> list[EventSpec]:
    return [EventSpec(EVENT_TYPE[f.category], severity(f.score), f.kind, f"{f.label} x{f.count} ({outcome})") for f in findings]


def _describe(findings: list[detection.Finding]) -> str:
    return ", ".join(sorted({f.label for f in findings}))


def check_content(policies: dict[str, Policy], messages: list[tuple[str, str]]) -> ContentVerdict:
    """Apply the org's DLP and prompt-injection policies to the call's messages."""
    out = ContentVerdict()
    dlp, inj = policies.get(DLP), policies.get(INJECTION)
    if dlp is not None and dlp.mode != "off":
        scan = detection.scan_messages([t for _, t in messages], set(dlp.config.get("detectors", [])))
        masking = dlp.mode == "enforce" and dlp.config.get("action", "block") == "mask"
        if scan.findings and dlp.mode == "enforce" and not masking:
            out.action, out.message = "block", f"This request was blocked by your organization's data policy (found: {_describe(scan.findings)})."
            out.events += _events(scan.findings, "blocked")
        elif scan.findings:
            out.action = "flag"
            out.events += _events(scan.findings, "masked" if masking else "flagged")
            out.masked = scan.masked if masking else None
        elif scan.truncated and dlp.mode == "enforce":  # nothing beyond the scan limit can be vouched for
            out.action, out.message = "block", "This request is too large for your organization's data policy to inspect."
        out.score = max(out.score, scan.score)
    if inj is not None and inj.mode != "off":
        found = detection.scan_injection(messages)
        if found and inj.mode == "enforce":
            out.action, out.message = "block", out.message or "This request was blocked by your organization's prompt-injection policy."
            out.events += _events(found, "blocked")
        elif found:
            out.action = out.action if out.action == "block" else "flag"
            out.events += _events(found, "flagged")
        out.score = max(out.score, max((f.score for f in found), default=0))
    return out
