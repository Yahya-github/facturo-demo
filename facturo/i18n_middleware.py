"""Pick the request language from X-Lang (or Accept-Language) for tr().

Pure ASGI, like local_guard.py: the language is set in a context variable
before the app runs and reset afterwards, so concurrent requests never see
each other's language. Threadpool endpoints inherit the context.
"""

from starlette.types import ASGIApp, Receive, Scope, Send

from facturo import i18n


class I18nMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        token = i18n.set_lang(i18n.resolve(headers.get("x-lang"), headers.get("accept-language")))
        try:
            await self.app(scope, receive, send)
        finally:
            i18n.reset_lang(token)
