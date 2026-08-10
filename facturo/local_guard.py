"""Make the local API answer only the app's own page.

The server listens on 127.0.0.1, but every web page open in the user's browser
can still send requests there. Two checks close that door:

  * Host must be a loopback name. A page served from a hostile domain that
    later resolves to 127.0.0.1 (DNS rebinding) sends its own domain as Host.
  * A state-changing request that a browser marks as coming from another site
    (Origin header, or Sec-Fetch-Site) is refused. This covers forms and
    fetch() calls, including those sent without a Content-Type header.

Requests with neither header (local scripts, the test suite) are allowed:
browsers always send Origin on cross-origin POST/PUT/PATCH/DELETE.
"""

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
FOREIGN_FETCH_SITES = frozenset({"cross-site", "same-site"})


def _hostname(host_header: str) -> str:
    """'localhost:8000' -> 'localhost'; tolerates a missing port."""
    return host_header.rsplit(":", 1)[0] if host_header.count(":") == 1 else host_header


class LocalGuardMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = headers.get("host", "")
        refusal = None
        if _hostname(host) not in LOCAL_HOSTS:
            refusal = "Hôte non autorisé."
        elif scope["method"] not in SAFE_METHODS:
            origin = headers.get("origin")
            if origin is not None and origin != f"http://{host}":
                refusal = "Requête d'une autre origine refusée."
            elif headers.get("sec-fetch-site") in FOREIGN_FETCH_SITES:
                refusal = "Requête d'un autre site refusée."

        if refusal:
            await PlainTextResponse(refusal, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)
