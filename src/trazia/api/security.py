from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class UploadLimit:
    """Limita el cuerpo multipart incluso si el cliente usa transferencia por fragmentos."""

    def __init__(self, app, limit: int, paths: tuple[str, ...] = ("/documents",)):
        self.app, self.limit, self.paths = app, limit, paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] not in self.paths or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = self.limit + 1
        if length > self.limit:
            return await JSONResponse(
                {"detail": "El cuerpo multipart supera el límite"}, status_code=413
            )(scope, receive, send)
        consumed = 0

        async def limited_receive():
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.limit:
                    raise HTTPException(413, "El cuerpo multipart supera el límite")
            return message

        await self.app(scope, limited_receive, send)
