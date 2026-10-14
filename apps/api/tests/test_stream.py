import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gateway.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import json
import time

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.adapters.anthropic_adapter import AnthropicAdapter
from app.adapters.openai_adapter import OpenAIAdapter
from app.config import settings
from app.db import ApiKey, Base, RequestLog, SessionLocal, engine
from app.errors import GatewayError
from app.main import app
from app.routers import data
from app.schemas import StreamEvent, UnifiedChatRequest

DEV = {"x-dev-org": "org_s", "x-dev-user": "sam"}
BODY = {"stream": True, "messages": [{"role": "user", "content": "hello streaming world"}]}


@pytest.fixture(autouse=True)
async def fresh():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def key(client, rpm=60):
    r = await client.post("/api/keys", json={"name": "s", "rpm_limit": rpm}, headers=DEV)
    return {"authorization": f"Bearer {r.json()['secret']}"}


def parse(text):
    out = []
    for block in text.strip().split("\n\n"):
        assert block.startswith("data: "), block
        d = block[6:]
        out.append(d if d == "[DONE]" else json.loads(d))
    return out


async def logs(client):
    return (await client.get("/api/logs", headers=DEV)).json()["items"]


async def test_stream_shape_and_logging(client):
    r = await client.post("/v1/chat", json=BODY, headers=await key(client))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["x-nexora-request-id"].startswith("req_")
    ev = parse(r.text)
    assert ev[-1] == "[DONE]"
    assert ev[0]["choices"][0]["delta"] == {"role": "assistant"}
    text = "".join(e["choices"][0]["delta"].get("content", "") for e in ev[:-1])
    assert text == "[mock] hello streaming world"
    final = ev[-2]
    assert final["choices"][0]["finish_reason"] == "stop" and final["usage"]["total_tokens"] > 0
    assert all(e["object"] == "chat.completion.chunk" for e in ev[:-1])
    row = (await logs(client))[0]
    assert row["decision"] == "allow" and row["status_code"] == 200 and row["tokens_in"] > 0 and row["tokens_out"] > 0


async def test_openai_route_streams_same_format(client):
    r = await client.post("/v1/chat/completions", json=BODY, headers=await key(client))
    assert parse(r.text)[-1] == "[DONE]" and len(await logs(client)) == 1


async def test_preflight_errors_are_plain_json(client):
    r = await client.post("/v1/chat", json=BODY, headers={"authorization": "Bearer nx_live_nope"})
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/json")
    h = await key(client, rpm=1)
    assert (await client.post("/v1/chat", json=BODY, headers=h)).status_code == 200
    r = await client.post("/v1/chat", json=BODY, headers=h)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"


async def test_quota_counts_streams(client):
    h = await key(client)
    async with SessionLocal() as s:
        from app.db import Organization
        o = (await s.execute(select(Organization))).scalar_one(); o.monthly_call_quota = 1; await s.commit()
    assert (await client.post("/v1/chat", json=BODY, headers=h)).status_code == 200
    r = await client.post("/v1/chat", json=BODY, headers=h)
    assert r.status_code == 429 and r.json()["error"]["code"] == "quota_exceeded"


async def test_upstream_refusal_before_first_byte_is_http_error(client):
    body = {**BODY, "provider": "openai"}  # no OPENAI key configured
    r = await client.post("/v1/chat", json=body, headers=await key(client))
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream_not_configured"
    row = (await logs(client))[0]
    assert row["decision"] == "error" and row["status_code"] == 502


async def test_mid_stream_failure_is_reported_in_band(client, monkeypatch):
    async def broken(self, request, credential=None):
        yield StreamEvent(type="delta", text="partial")
        raise GatewayError(502, "upstream_error", "provider died")
    monkeypatch.setattr(type(data.ADAPTERS["mock"]), "stream_chat", broken)
    r = await client.post("/v1/chat", json=BODY, headers=await key(client))
    assert r.status_code == 200
    ev = parse(r.text)
    assert ev[-1]["error"]["code"] == "upstream_error" and "[DONE]" not in ev
    row = (await logs(client))[0]
    assert row["decision"] == "error" and row["status_code"] == 502 and row["tokens_out"] >= 1


async def test_client_disconnect_still_logs_once(client):
    h = await key(client)
    async with SessionLocal() as s:
        k = (await s.execute(select(ApiKey))).scalar_one()
    req = UnifiedChatRequest(**BODY, model="mock-1")
    log = RequestLog(org_id=k.org_id, key_id=k.id, request_id="req_abort", provider="mock", model="mock-1", status_code=200, decision="allow")

    async def slow():
        for w in ["a", "b", "c", "d"]:
            yield StreamEvent(type="delta", text=w)
    gen = slow()
    first = await gen.__anext__()
    agen = data._sse(first, gen, req, log, k.id, time.monotonic())
    await agen.__anext__(); await agen.__anext__()  # role chunk + first delta
    await agen.aclose()  # what happens when the client disconnects
    rows = await logs(client)
    assert len(rows) == 1 and rows[0]["status_code"] == 499 and rows[0]["tokens_out"] >= 1


async def test_playground_streams(client):
    r = await client.post("/api/playground", json={"prompt": "hi there", "stream": True}, headers=DEV)
    assert r.headers["content-type"].startswith("text/event-stream") and parse(r.text)[-1] == "[DONE]"
    assert (await logs(client))[0]["key_id"] is None


# ---- adapter parsing against canned upstream SSE ----
def sse(*objs, done=False):
    body = "".join(f"data: {json.dumps(o)}\n\n" if isinstance(o, dict) else f"data: {o}\n\n" for o in objs)
    return body


async def collect(adapter, handler):
    adapter.transport = httpx.MockTransport(handler)
    req = UnifiedChatRequest(model="m", messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], stream=True)
    return [e async for e in adapter.stream_chat(req)]


async def test_anthropic_stream_parsing(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "k")
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=sse(
            {"type": "message_start", "message": {"usage": {"input_tokens": 11}}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hel"}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "lo"}},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 7}},
            {"type": "message_stop"}), headers={"content-type": "text/event-stream"})
    ev = await collect(AnthropicAdapter(), handler)
    assert seen["body"]["stream"] is True and seen["body"]["system"] == "s"
    assert "".join(e.text for e in ev if e.type == "delta") == "Hello"
    assert [e.prompt_tokens for e in ev if e.type == "usage"][0] == 11
    assert [e.completion_tokens for e in ev if e.type == "usage"][-1] == 7
    assert [e.finish_reason for e in ev if e.type == "finish"] == ["end_turn"]


async def test_openai_stream_parsing(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "k")

    def handler(request):
        assert json.loads(request.content)["stream_options"] == {"include_usage": True}
        return httpx.Response(200, content=sse(
            {"choices": [{"delta": {"role": "assistant"}}]},
            {"choices": [{"delta": {"content": "Hi"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}, "[DONE]"))
    ev = await collect(OpenAIAdapter(), handler)
    assert "".join(e.text for e in ev if e.type == "delta") == "Hi"
    assert any(e.type == "usage" and e.prompt_tokens == 5 and e.completion_tokens == 2 for e in ev)
    assert any(e.type == "finish" and e.finish_reason == "stop" for e in ev)


async def test_upstream_http_error_raises_before_first_event(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "k")
    with pytest.raises(GatewayError) as e:
        await collect(AnthropicAdapter(), lambda r: httpx.Response(429, json={"error": "slow down"}))
    assert e.value.code == "upstream_error"


async def test_anthropic_in_stream_error_event(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "k")
    with pytest.raises(GatewayError):
        await collect(AnthropicAdapter(), lambda r: httpx.Response(200, content=sse({"type": "error", "error": {"message": "overloaded"}})))
