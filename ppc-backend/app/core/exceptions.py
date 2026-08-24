from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Optional, Any


class AppException(HTTPException):
    def __init__(self, status_code: int, detail: str, headers: Optional[dict] = None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class NotFoundError(AppException):
    def __init__(self, resource: str = "Resource"):
        super().__init__(status_code=404, detail=f"{resource} not found")


class UnauthorizedError(AppException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(
            status_code=401,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenError(AppException):
    def __init__(self, detail: str = "Not enough permissions"):
        super().__init__(status_code=403, detail=detail)


class ValidationError(AppException):
    def __init__(self, detail: str = "Validation error"):
        super().__init__(status_code=422, detail=detail)


class ConflictError(AppException):
    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(status_code=409, detail=detail)


class FraudDetectedError(AppException):
    def __init__(self, reason: str = "Fraudulent click detected"):
        super().__init__(status_code=403, detail=reason)


class InsufficientBalanceError(AppException):
    def __init__(self):
        super().__init__(status_code=400, detail="Insufficient balance for withdrawal")


# Exception handlers
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail},
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"},
    )
