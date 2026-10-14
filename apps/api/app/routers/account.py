"""Events from the NEXORA account service (Svix-signed webhooks): keep Gateway data in step with deletions there."""
import base64
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import accounts
from app.config import settings
from app.db import Member, Organization, get_session
from app.errors import GatewayError

router = APIRouter()
TOLERANCE_SECONDS = 300
MAX_BODY = 1_000_000


def verify_svix(body: bytes, headers) -> None:
    if not settings.ACCOUNT_WEBHOOK_SECRET:
        raise GatewayError(503, "webhook_not_configured", "Account webhooks are not configured.")
    msg_id, ts, sigs = headers.get("svix-id", ""), headers.get("svix-timestamp", ""), headers.get("svix-signature", "")
    try:
        if abs(time.time() - int(ts)) > TOLERANCE_SECONDS:
            raise ValueError("stale")
        key = base64.b64decode(settings.ACCOUNT_WEBHOOK_SECRET.removeprefix("whsec_"))
    except ValueError:
        raise GatewayError(400, "bad_signature", "Invalid webhook signature.")
    expected = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    candidates = [part.split(",", 1)[1] for part in sigs.split() if part.startswith("v1,")]
    if not any(hmac.compare_digest(expected, c) for c in candidates):
        raise GatewayError(400, "bad_signature", "Invalid webhook signature.")


@router.post("/webhooks/account")
async def account_webhook(request: Request, s: AsyncSession = Depends(get_session)):
    body = await request.body()
    if len(body) > MAX_BODY:
        raise GatewayError(413, "too_large", "Payload too large.")
    verify_svix(body, request.headers)
    try:
        event = json.loads(body)
        typ, data = event["type"], event.get("data") or {}
    except (ValueError, KeyError, TypeError):
        raise GatewayError(400, "invalid_request", "Malformed event.")

    if typ == "user.deleted" and data.get("id"):
        await accounts.remove_user_everywhere(s, data["id"])
    elif typ == "organization.deleted" and data.get("id"):
        org = (await s.execute(select(Organization).where(Organization.external_org_id == data["id"]))).scalar_one_or_none()
        if org:
            await accounts.cancel_billing(s, org.id, strict=False)
            await accounts.delete_org_data(s, org.id)
    elif typ == "organizationMembership.deleted":
        uid = (data.get("public_user_data") or {}).get("user_id")
        ext_org = (data.get("organization") or {}).get("id")
        org = (await s.execute(select(Organization).where(Organization.external_org_id == ext_org))).scalar_one_or_none() if ext_org else None
        if uid and org:
            await s.execute(delete(Member).where(Member.org_id == org.id, Member.external_user_id == uid))
    await s.commit()
    return {"received": True}
