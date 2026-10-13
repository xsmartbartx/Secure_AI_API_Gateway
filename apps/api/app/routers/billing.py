import datetime as dt

import stripe
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import Organization, StripeEvent, Subscription, get_session
from app.deps import Principal, require
from app.errors import GatewayError

router = APIRouter()

PLAN_QUOTA = {"free": 100, "starter": 1500}


def _enabled() -> bool:
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_STARTER)


def _require_enabled() -> None:
    if not _enabled():
        raise GatewayError(503, "billing_disabled", "Online billing is not enabled yet.")
    if settings.ENV == "prod" and settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
        raise GatewayError(503, "billing_misconfigured", "Billing is configured with a test key.")
    stripe.api_key = settings.STRIPE_SECRET_KEY


@router.get("/api/billing")
async def billing_state(p: Principal = Depends(require("viewer")), s: AsyncSession = Depends(get_session)):
    sub = await s.get(Subscription, p.org.id)
    return {"enabled": _enabled(), "plan": p.org.plan, "quota": p.org.monthly_call_quota,
            "status": sub.status if sub else "none", "renews": sub.current_period_end if sub else None,
            "can_manage": bool(sub and sub.stripe_customer_id)}


@router.post("/api/billing/checkout")
async def checkout(p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    _require_enabled()
    sub = await s.get(Subscription, p.org.id)
    if sub is None:
        sub = Subscription(org_id=p.org.id, plan="free", status="active")
        s.add(sub)
    if not sub.stripe_customer_id:
        cust = stripe.Customer.create(name=p.org.name, metadata={"org_id": p.org.id})
        sub.stripe_customer_id = cust.id
    await s.commit()
    session = stripe.checkout.Session.create(
        mode="subscription", customer=sub.stripe_customer_id, client_reference_id=p.org.id,
        line_items=[{"price": settings.STRIPE_PRICE_STARTER, "quantity": 1}],
        success_url=f"{settings.APP_URL}/app/billing?checkout=success",
        cancel_url=f"{settings.APP_URL}/app/billing?checkout=cancelled",
        subscription_data={"metadata": {"org_id": p.org.id}},
    )
    return {"url": session.url}


@router.post("/api/billing/portal")
async def portal(p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    _require_enabled()
    sub = await s.get(Subscription, p.org.id)
    if not sub or not sub.stripe_customer_id:
        raise GatewayError(409, "no_customer", "There is no billing account yet. Upgrade first.")
    ps = stripe.billing_portal.Session.create(customer=sub.stripe_customer_id, return_url=f"{settings.APP_URL}/app/billing")
    return {"url": ps.url}


async def _apply(s: AsyncSession, org_id: str, plan: str, status: str, sub_id: str | None, period_end: int | None):
    org = await s.get(Organization, org_id)
    if org is None:
        return
    sub = await s.get(Subscription, org_id) or Subscription(org_id=org_id)
    s.add(sub)
    active = status in ("active", "trialing", "past_due")  # past_due keeps access during Stripe's retry window
    sub.plan, sub.status, sub.stripe_subscription_id = (plan if active else "free"), status, sub_id
    sub.current_period_end = dt.datetime.fromtimestamp(period_end, dt.timezone.utc) if period_end else None
    org.plan = sub.plan
    org.monthly_call_quota = PLAN_QUOTA.get(org.plan, PLAN_QUOTA["free"])


async def _org_for_customer(s: AsyncSession, customer_id: str) -> str | None:
    return (await s.execute(select(Subscription.org_id).where(Subscription.stripe_customer_id == customer_id))).scalar_one_or_none()


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, s: AsyncSession = Depends(get_session)):
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, request.headers.get("stripe-signature", ""), settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        raise GatewayError(400, "bad_signature", "Invalid webhook signature.")

    event = event.to_dict() if hasattr(event, "to_dict") else event
    if await s.get(StripeEvent, event["id"]):
        return {"received": True, "duplicate": True}
    s.add(StripeEvent(id=event["id"]))

    obj, typ = event["data"]["object"], event["type"]
    if typ == "checkout.session.completed" and obj.get("mode") == "subscription":
        org_id = obj.get("client_reference_id")
        if org_id:
            await _apply(s, org_id, "starter", "active", obj.get("subscription"), None)
    elif typ in ("customer.subscription.updated", "customer.subscription.deleted"):
        org_id = (obj.get("metadata") or {}).get("org_id") or await _org_for_customer(s, obj["customer"])
        if org_id:
            status = "canceled" if typ.endswith("deleted") else obj["status"]
            await _apply(s, org_id, "starter", status, obj["id"], obj.get("current_period_end"))
    elif typ == "invoice.payment_failed":
        org_id = await _org_for_customer(s, obj["customer"])
        if org_id and (sub := await s.get(Subscription, org_id)):
            sub.status = "past_due"
    await s.commit()
    return {"received": True}
