"""Who can do what inside Gateway. Membership itself (invites, removal from the company) lives in the NEXORA account;
Gateway keeps its own role per member and a reversible suspend switch."""
import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Member, Organization, get_session
from app.deps import Principal, require
from app.errors import GatewayError

router = APIRouter(prefix="/api/members")
log = logging.getLogger("gateway.team")


def _out(m: Member, me: str) -> dict:
    return {"id": m.id, "email": m.email, "role": m.role, "status": m.status, "created_at": m.created_at, "is_me": m.id == me}


class MemberPatch(BaseModel):
    role: Literal["owner", "admin", "developer", "viewer"] | None = None
    status: Literal["active", "suspended"] | None = None

    @model_validator(mode="after")
    def _something(self):
        if self.role is None and self.status is None:
            raise ValueError("send a role or a status to change")
        return self


@router.get("")
async def list_members(p: Principal = Depends(require("viewer")), s: AsyncSession = Depends(get_session)):
    rows = (await s.execute(select(Member).where(Member.org_id == p.org.id).order_by(Member.created_at, Member.email))).scalars().all()
    return {"items": [_out(m, p.member.id) for m in rows]}


def _lock_org_stmt(org_id: str):
    """Owner changes are serialised per organization: take a row lock on the org before reading or changing any member."""
    return select(Organization.id).where(Organization.id == org_id).with_for_update()


async def _ensure_active_owner(s: AsyncSession, org_id: str) -> None:
    owners = (await s.execute(select(func.count()).select_from(Member).where(
        Member.org_id == org_id, Member.role == "owner", Member.status == "active"))).scalar_one()
    if owners == 0:
        raise GatewayError(409, "last_owner", "The organization needs at least one active owner.")


@router.patch("/{member_id}")
async def update_member(member_id: str, body: MemberPatch, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    await s.execute(_lock_org_stmt(p.org.id))  # two owners demoting each other at once now run one after the other
    target = await s.get(Member, member_id, populate_existing=True)
    if target is None or target.org_id != p.org.id:
        raise GatewayError(404, "not_found", "Member not found.")
    if target.id == p.member.id:  # nobody locks themselves out or promotes themselves
        raise GatewayError(409, "self_change", "You can't change your own role or access. Ask another owner.")
    if p.role != "owner":
        if target.role in ("owner", "admin"):
            raise GatewayError(403, "forbidden", "Only an owner can change an admin or an owner.")
        if body.role in ("owner", "admin"):
            raise GatewayError(403, "forbidden", "Only an owner can grant the admin or owner role.")

    before = (target.role, target.status)
    if body.role:
        target.role = body.role
    if body.status:
        target.status = body.status
    try:
        await _ensure_active_owner(s, p.org.id)  # counts after the change, inside the lock, so it sees every committed owner change
    except GatewayError:
        await s.rollback()
        raise
    await s.commit()
    log.info("member changed org=%s actor=%s target=%s %s->%s", p.org.id, p.member.id, target.id, before, (target.role, target.status))
    return _out(target, p.member.id)
