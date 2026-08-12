import asyncio

from app.middleware.request_body_limit import RequestBodyLimitMiddleware


def invoke(chunks, *, limit=5, headers=None):
    messages = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]
    sent = []
    called = False

    async def receive():
        return messages.pop(0) if messages else {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        nonlocal called
        called = True
        while (await receive()).get("more_body", False):
            pass
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    scope = {"type": "http", "headers": headers or []}
    asyncio.run(RequestBodyLimitMiddleware(app, limit)(scope, receive, send))
    status = next(
        item["status"] for item in sent if item["type"] == "http.response.start"
    )
    return status, called


def test_content_length_rejects_before_app():
    assert invoke([], headers=[(b"content-length", b"6")]) == (413, False)


def test_streamed_body_is_counted_and_normal_body_passes():
    assert invoke([b"12", b"345"], limit=5)[0] == 200
    assert invoke([b"123", b"456"], limit=5)[0] == 413
