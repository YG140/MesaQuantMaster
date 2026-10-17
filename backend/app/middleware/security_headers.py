class SecurityHeadersMiddleware:
    def __init__(self, app, *, hsts_enabled: bool, hsts_max_age_seconds: int):
        self.app = app
        self.hsts_enabled = hsts_enabled
        self.hsts_max_age_seconds = max(0, hsts_max_age_seconds)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def add_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"strict-origin-when-cross-origin"),
                        (b"x-frame-options", b"DENY"),
                        (b"content-security-policy", b"frame-ancestors 'none'"),
                    ]
                )
                # HSTS is enforced by browsers only on HTTPS responses. Sending
                # it whenever enabled also covers TLS-terminating proxies whose
                # upstream ASGI scope still reports HTTP, without trusting
                # potentially spoofed X-Forwarded-* headers.
                if self.hsts_enabled:
                    headers.append(
                        (
                            b"strict-transport-security",
                            f"max-age={self.hsts_max_age_seconds}".encode(),
                        )
                    )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, add_headers)
