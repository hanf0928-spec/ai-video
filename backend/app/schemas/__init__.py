
"""Pydantic schemas for API I/O."""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional, Literal

from pydantic import BaseModel, Field


# ---------- Common ----------
class ResponseModel(BaseModel):
    success: bool = True
    code: str = "OK"
    message: str = ""
    data: Any = None


# ---------- Project ----------
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    style: Optional[str] = None
    settings: dict = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    style: Optional[str] = None
    cover_url: Optional[str] = None
    settings: Optional[dict] = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    cover_url: Optional[str]
    style: Optional[str]
    settings: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------- Episode ----------
class EpisodeCreate(BaseModel):
    project_id: str
    index: int = 1
    title: str
    script: Optional[str] = None


class EpisodeOut(BaseModel):
    id: str
    project_id: str
    index: int
    title: str
    status: str
    script: Optional[str]
    video_url: Optional[str]
    duration: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Shot ----------
class ShotCreate(BaseModel):
    episode_id: str
    index: int = 0
    prompt: Optional[str] = None
    dialogue: Optional[str] = None
    speaker: Optional[str] = None
    emotion: Optional[str] = None
    duration: float = 4.0
    model_backend: Literal["hailuo", "seedance", "comfyui"] = "hailuo"


class ShotUpdate(BaseModel):
    prompt: Optional[str] = None
    dialogue: Optional[str] = None
    speaker: Optional[str] = None
    emotion: Optional[str] = None
    duration: Optional[float] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    model_backend: Optional[str] = None


class ShotOut(BaseModel):
    id: str
    episode_id: str
    index: int
    prompt: Optional[str]
    dialogue: Optional[str]
    speaker: Optional[str]
    emotion: Optional[str]
    duration: float
    image_url: Optional[str]
    video_url: Optional[str]
    audio_url: Optional[str]
    model_backend: str
    status: str

    class Config:
        from_attributes = True


# ---------- Character ----------
class CharacterCreate(BaseModel):
    project_id: str
    name: str
    description: Optional[str] = None
    reference_images: List[str] = Field(default_factory=list)
    voice_id: Optional[str] = None


class CharacterOut(BaseModel):
    id: str
    project_id: str
    name: str
    description: Optional[str]
    reference_images: List[str]
    voice_id: Optional[str]
    lora_path: Optional[str]

    class Config:
        from_attributes = True


# ---------- Scene ----------
class SceneCreate(BaseModel):
    project_id: str
    name: str
    description: Optional[str] = None
    reference_images: List[str] = Field(default_factory=list)
    style_prompt: Optional[str] = None


class SceneOut(BaseModel):
    id: str
    project_id: str
    name: str
    description: Optional[str]
    reference_images: List[str]
    style_prompt: Optional[str]

    class Config:
        from_attributes = True


# ---------- Manga ----------
class MangaUploadOut(BaseModel):
    id: str
    project_id: str
    filename: str
    file_type: str
    page_count: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class MangaPanelOut(BaseModel):
    id: str
    upload_id: str
    page: int
    order: int
    bbox: List[float]
    image_path: str
    ocr_text: Optional[str]
    bubbles: list

    class Config:
        from_attributes = True


# ---------- Job ----------
class JobOut(BaseModel):
    id: str
    type: str
    status: str
    progress: float
    stage: Optional[str]
    message: Optional[str]
    result: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------- Pipeline Requests ----------
class Manga2AnimeRequest(BaseModel):
    project_id: str
    upload_id: str
    style: Optional[str] = Field(None, description="目标动画风格，如 anime/pixar/watercolor")
    video_backend: Literal["hailuo", "seedance"] = "hailuo"
    tts_voice: Optional[str] = None
    enable_bgm: bool = True
    enable_subtitle: bool = True
    shot_duration: float = 4.0
    resolution: str = "1080P"


class GenerateShotRequest(BaseModel):
    shot_id: str
    backend: Literal["hailuo", "seedance", "comfyui"] = "hailuo"
    extra: dict = Field(default_factory=dict)


class GenerateEpisodeRequest(BaseModel):
    episode_id: str
    backend: Literal["hailuo", "seedance"] = "hailuo"
    enable_tts: bool = True
    enable_bgm: bool = True
    enable_subtitle: bool = True


class ScriptGenerateRequest(BaseModel):
    project_id: str
    topic: str = Field(..., description="剧本主题 / 故事大纲")
    episode_count: int = 1
    shots_per_episode: int = 8
    style: Optional[str] = None
