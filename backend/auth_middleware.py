"""Central private API authorization middleware for NOVA."""
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


PUBLIC_API_PATHS = {
    "/api/",
    "/api/auth/session",
    "/api/auth/logout",
    "/api/google/callback",
}


class SingleUserAuthorizationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, current_user_loader):
        super().__init__(app)
        self.current_user_loader = current_user_loader

    async def dispatch(self, request, call_next):
        path = request.url.path
        if (
            request.method == "OPTIONS"
            or not path.startswith("/api")
            or path in PUBLIC_API_PATHS
        ):
            return await call_next(request)

        try:
            request.state.authorized_user = await self.current_user_loader(request)
        except HTTPException as exc:
            response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            response.delete_cookie("nova_session", path="/", samesite="lax", secure=True)
            return response
        return await call_next(request)