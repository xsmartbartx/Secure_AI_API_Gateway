import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app import detection, policy
from app.db import Policy, get_session
from app.deps import Principal, require
from app.errors import GatewayError
from app.logsafe import clean, one_of
from app.ratelimit import limiter

POLICY_TYPES = (policy.MODEL_ALLOW, policy.DLP, policy.INJECTION)
router = APIRouter(prefix="/api/policies")
log = logging.getLogger("gateway.policies")


def _mode(v: str) -> str:
    if v not in policy.MODES:
        raise ValueError("mode must be off, monitor or enforce")
    return v


def _model_out(p: Policy | None) -> dict:
    return {"mode": p.mode if p else "off", "models": p.config.get("models", []) if p else [], "version": p.version if p else 0}


def _dlp_out(p: Policy | None) -> dict:
    cfg = p.config if p else {}
    return {"mode": p.mode if p else "off", "detectors": cfg.get("detectors", []), "action": cfg.get("action", "block"),
            "available": list(detection.ALL_DETECTORS), "labels": detection.LABEL, "version": p.version if p else 0}


def _injection_out(p: Policy | None) -> dict:
    return {"mode": p.mode if p else "off", "version": p.version if p else 0}


async def _save(s: AsyncSession, p: Principal, ptype: str, mode: str, config: dict) -> int:
    """Atomic create-or-update (see policy.save_policy); returns the version this save produced."""
    version = await policy.save_policy(s, p.org.id, ptype, mode, config)
    log.info("policy changed org=%s actor=%s type=%s mode=%s version=%d", clean(p.org.id), clean(p.member.id), one_of(ptype, POLICY_TYPES), one_of(mode, policy.MODES), version)  # known names only, never the values
    return version


class ModelPolicyIn(BaseModel):
    mode: str
    models: list[str] = Field(..., max_length=200)

    _check_mode = field_validator("mode")(lambda cls, v: _mode(v))

    @model_validator(mode="after")
    def _list(self):
        try:
            self.models = policy.normalise_patterns(self.models)
        except ValueError as e:
            raise ValueError(str(e)) from None
        if self.mode != "off" and not self.models:
            raise ValueError("add at least one model before turning the policy on (an empty list would block every call)")
        return self


class DlpPolicyIn(BaseModel):
    mode: str
    detectors: list[str] = Field(default_factory=list, max_length=20)
    action: Literal["block", "mask"] = "block"

    _check_mode = field_validator("mode")(lambda cls, v: _mode(v))

    @model_validator(mode="after")
    def _detectors(self):
        unknown = [d for d in self.detectors if d not in detection.ALL_DETECTORS]
        if unknown:
            raise ValueError(f"unknown detector: {unknown[0]}")
        self.detectors = list(dict.fromkeys(self.detectors))
        if self.mode != "off" and not self.detectors:
            raise ValueError("choose at least one kind of data to look for")
        return self


class InjectionPolicyIn(BaseModel):
    mode: str

    _check_mode = field_validator("mode")(lambda cls, v: _mode(v))


class ModelTest(BaseModel):
    model: str = Field(..., min_length=1, max_length=200)


class ScanIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=20_000)


@router.get("")
async def list_policies(p: Principal = Depends(require("viewer")), s: AsyncSession = Depends(get_session)):
    pols = await policy.load_policies(s, p.org.id)
    return {"model_allow": _model_out(pols.get(policy.MODEL_ALLOW)), "dlp": _dlp_out(pols.get(policy.DLP)),
            "injection": _injection_out(pols.get(policy.INJECTION))}


@router.put("/model_allow")
async def set_model_policy(body: ModelPolicyIn, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    version = await _save(s, p, policy.MODEL_ALLOW, body.mode, {"models": body.models})
    return {"mode": body.mode, "models": body.models, "version": version}


@router.put("/dlp")
async def set_dlp_policy(body: DlpPolicyIn, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    cfg = {"detectors": body.detectors, "action": body.action}
    return _dlp_out(Policy(mode=body.mode, config=cfg, version=await _save(s, p, policy.DLP, body.mode, cfg)))


@router.put("/injection")
async def set_injection_policy(body: InjectionPolicyIn, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    return _injection_out(Policy(mode=body.mode, config={}, version=await _save(s, p, policy.INJECTION, body.mode, {})))


@router.post("/model_allow/test")
async def test_model(body: ModelTest, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    """Dry run: would this model be allowed by the saved policy?"""
    row = await policy.load_model_policy(s, p.org.id)
    matched = policy.match(row.config.get("models", []), body.model) if row else None
    mode = row.mode if row else "off"
    # "allowed" means the call would go ahead: only enforce mode stops an unlisted model. Monitor lets it through but flags it.
    return {"allowed": mode != "enforce" or matched is not None, "matched": matched, "mode": mode, "flagged": mode == "monitor" and matched is None}


@router.post("/scan")
async def scan(body: ScanIn, p: Principal = Depends(require("admin"))):
    """Dry run: what would the detectors find in this text? Nothing is stored or logged; the text only passes through this request."""
    ok, retry = await limiter.allow(f"scan:{p.org.id}", 30)
    if not ok:
        raise GatewayError(429, "rate_limited", "Too many scans. Wait a minute.", {"Retry-After": str(retry)})
    result = detection.scan_text(body.text, set(detection.ALL_DETECTORS))
    inj = detection.scan_injection([("user", body.text)])
    return {"findings": [{"kind": f.kind, "label": f.label, "category": f.category, "count": f.count} for f in result.findings],
            "injection": [{"kind": f.kind, "label": f.label, "count": f.count} for f in inj],
            "score": max([result.score] + [f.score for f in inj]), "masked": result.masked}
