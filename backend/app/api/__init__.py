
"""API router aggregation."""
from fastapi import APIRouter

from . import projects, episodes, library, manga, generate, jobs, comfy, config


api_router = APIRouter(prefix="/api")
api_router.include_router(projects.router)
api_router.include_router(episodes.router)
api_router.include_router(library.router)
api_router.include_router(manga.router)
api_router.include_router(generate.router)
api_router.include_router(jobs.router)
api_router.include_router(comfy.router)
api_router.include_router(config.router)

__all__ = ["api_router"]
