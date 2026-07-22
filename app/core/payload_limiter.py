from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import status

class LimitPayloadSizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_upload_size: int = 1_048_576):  # 1 MB default threshold
        super().__init__(app)
        self.max_upload_size = max_upload_size

    async def dispatch(self, request, call_next):
        # Inspect incoming Content-Length header if present
        content_length = request.headers.get("content-length")
        
        if content_length:
            try:
                if int(content_length) > self.max_upload_size:
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "detail": f"Payload size exceeds maximum limit of {self.max_upload_size} bytes."
                        },
                    )
            except ValueError:
                pass  # Malformed header will be handled by standard web stack

        return await call_next(request)
