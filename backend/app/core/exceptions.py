
"""Unified exception types for the application."""
from __future__ import annotations


class AppError(Exception):
    """Base application error."""

    code: str = "APP_ERROR"
    status: int = 500

    def __init__(self, message: str, *, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status = 404


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    status = 422


class AdapterError(AppError):
    """Raised when an external model adapter fails."""

    code = "ADAPTER_ERROR"
    status = 502


class PipelineError(AppError):
    """Raised when a pipeline stage fails."""

    code = "PIPELINE_ERROR"
    status = 500


class ComfyUIError(AppError):
    code = "COMFYUI_ERROR"
    status = 502
