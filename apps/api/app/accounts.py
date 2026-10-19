import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import (ApiKey, Member, Organization, Policy, ProviderConnection, RequestLog, SecurityEvent, Subscription, UsageDaily)
from app.errors import GatewayError
from app.logsafe import clean
from app.routers import billing

log = logging.getLogger("gateway.accounts")


async def cancel_billing(s: AsyncSession, org_id: str, strict: bool) -> None:
    """Cancel the org's Stripe subscription before its data goes. strict=True (user-initiated delete) aborts if Stripe fails,
    so nobody keeps being charged for a deleted organization. strict=False (account-service webhook) logs and carries on."""
    sub = await s.get(Subscription, org_id)
    if not (sub and sub.stripe_subscription_id and settings.STRIPE_SECRET_KEY):
        return
    try:
        billing.cancel_subscription_now(sub.stripe_subscription_id)
    except Exception:
        log.exception("could not cancel Stripe subscription for org %s", clean(org_id))
        if strict:
            raise GatewayError(502, "billing_cancel_failed", "We could not cancel your subscription, so nothing was deleted. Try again, or contact support.")


async def delete_org_data(s: AsyncSession, org_id: str) -> None:
    """Hard-delete everything stored for an organization. Explicit, ordered deletes: SQLite does not enforce ON DELETE CASCADE.
    Stripe webhook event ids (no personal data) are kept for idempotency; the Stripe customer record is kept for accounting."""
    await s.execute(delete(SecurityEvent).where(SecurityEvent.org_id == org_id))
    await s.execute(delete(RequestLog).where(RequestLog.org_id == org_id))
    await s.execute(delete(UsageDaily).where(UsageDaily.org_id == org_id))
    await s.execute(delete(Policy).where(Policy.org_id == org_id))
    await s.execute(delete(ProviderConnection).where(ProviderConnection.org_id == org_id))  # the customers' provider keys
    await s.execute(delete(ApiKey).where(ApiKey.org_id == org_id))
    await s.execute(delete(Subscription).where(Subscription.org_id == org_id))
    await s.execute(delete(Member).where(Member.org_id == org_id))
    await s.execute(delete(Organization).where(Organization.id == org_id))
    log.info("deleted organization %s", clean(org_id))


async def remove_user_everywhere(s: AsyncSession, external_user_id: str) -> int:
    """The account service deleted this user: drop their memberships; delete any org left with no members, and their personal workspace."""
    orgs = [m.org_id for m in (await s.execute(select(Member).where(Member.external_user_id == external_user_id))).scalars()]
    personal = (await s.execute(select(Organization.id).where(Organization.external_org_id == external_user_id))).scalars().all()
    await s.execute(delete(Member).where(Member.external_user_id == external_user_id))
    removed = 0
    for org_id in set(orgs) | set(personal):
        left = (await s.execute(select(Member.id).where(Member.org_id == org_id).limit(1))).first()
        if left is None or org_id in personal:
            await cancel_billing(s, org_id, strict=False)
            await delete_org_data(s, org_id)
            removed += 1
    return removed
