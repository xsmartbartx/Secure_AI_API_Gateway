import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app import policy
from app.db import Policy, get_session
from app.deps import Principal, require

router = APIRouter(prefix="/api/policies")
log = logging.getLogger("gateway.policies")


def _out(p: Policy | None) -> dict:
    if p is None:
        return {"mode": "off", "models": [], "version": 0}
    return {"mode": p.mode, "models": p.config.get("models", []), "version": p.version}


class ModelPolicyIn(BaseModel):
    mode: str
    models: list[str] = Field(..., max_length=200)

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in policy.MODES:
            raise ValueError("mode must be off, monitor or enforce")
        return v

    @model_validator(mode="after")
    def _list(self):
        try:
            self.models = policy.normalise_patterns(self.models)
        except ValueError as e:
            raise ValueError(str(e)) from None
        if self.mode != "off" and not self.models:
            raise ValueError("add at least one model before turning the policy on (an empty list would block every call)")
        return self


class ModelTest(BaseModel):
    model: str = Field(..., min_length=1, max_length=200)


@router.get("")
async def list_policies(p: Principal = Depends(require("viewer")), s: AsyncSession = Depends(get_session)):
    return {"model_allow": _out(await policy.load_model_policy(s, p.org.id))}


@router.put("/model_allow")
async def set_model_policy(body: ModelPolicyIn, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    row = await policy.load_model_policy(s, p.org.id)
    if row is None:
        row = Policy(org_id=p.org.id, type=policy.MODEL_ALLOW, mode=body.mode, config={"models": body.models}, version=1)
        s.add(row)
    else:
        row.mode, row.config, row.version = body.mode, {"models": body.models}, row.version + 1
    await s.commit()
    log.info("model policy changed org=%s actor=%s mode=%s patterns=%d version=%d", p.org.id, p.member.id, row.mode, len(body.models), row.version)
    return _out(row)


@router.post("/model_allow/test")
async def test_model(body: ModelTest, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    """Dry run: would this model be allowed by the saved policy?"""
    row = await policy.load_model_policy(s, p.org.id)
    matched = policy.match(row.config.get("models", []), body.model) if row else None
    mode = row.mode if row else "off"
    return {"allowed": mode == "off" or matched is not None, "matched": matched, "mode": mode}
