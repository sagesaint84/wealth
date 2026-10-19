"""Compress large static JS/CSS only; no response cache or financial data path."""
from starlette.datastructures import MutableHeaders
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles


class CompressedStaticFiles(StaticFiles):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._gzip = GZipMiddleware(super().__call__, minimum_size=1024, compresslevel=5)

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        encoding = headers.get(b"accept-encoding", b"").decode("latin-1")
        # Respect an explicit gzip refusal; the standard responder otherwise
        # accepts the token even with q=0. Do not alter scope or request headers.
        gzip_allowed = True
        for item in encoding.lower().split(","):
            parts = [part.strip() for part in item.split(";")]
            if parts[0] == "gzip":
                for parameter in parts[1:]:
                    if parameter.startswith("q="):
                        try:
                            gzip_allowed = float(parameter[2:]) > 0
                        except ValueError:
                            gzip_allowed = False
        script_or_style = scope.get("path", "").endswith((".js", ".css"))
        original_send = send
        async def varied_send(message):
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                if "accept-encoding" not in response_headers.get("vary", "").lower().split(", "):
                    response_headers.add_vary_header("Accept-Encoding")
            await original_send(message)
        if script_or_style:
            send = varied_send
        if (scope["type"] == "http" and scope["method"] == "GET"
                and script_or_style
                and b"range" not in headers and gzip_allowed):
            await self._gzip(scope, receive, send)
        else:
            await super().__call__(scope, receive, send)
