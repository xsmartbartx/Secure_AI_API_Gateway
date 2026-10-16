"""Per-organization policies applied to every call before it is sent upstream."""
import fnmatch
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def load_model_policy(s: AsyncSession, org_id: str) -> Policy | None:
    return (await s.execute(select(Policy).where(Policy.org_id == org_id, Policy.type == MODEL_ALLOW))).scalar_one_or_none()


async def check_model(s: AsyncSession, org_id: str, model: str) -> Verdict:
    pol = await load_model_policy(s, org_id)
    if pol is None or pol.mode == "off":
        return Verdict("allow")
    if match(pol.config.get("models", []), model):
        return Verdict("allow")
    return Verdict("block" if pol.mode == "enforce" else "flag", MODEL_ALLOW)
