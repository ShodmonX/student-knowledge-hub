from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    status_code = 400
    error_code = "application_error"

    def __init__(self, message: str, details: Any | None = None) -> None:
        self.message = message
        self.details = details
        super().__init__(message)


class AuthenticationError(AppException):
    status_code = 401
    error_code = "unauthorized"


class PermissionDenied(AppException):
    status_code = 403
    error_code = "forbidden"


class ResourceNotFound(AppException):
    status_code = 404
    error_code = "not_found"


class ConflictError(AppException):
    status_code = 409
    error_code = "conflict"


class ValidationAppError(AppException):
    status_code = 422
    error_code = "validation_error"


class RateLimitExceeded(AppException):
    status_code = 429
    error_code = "rate_limit_exceeded"


class PolicyViolation(AppException):
    status_code = 422
    error_code = "policy_violation"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            },
        )
