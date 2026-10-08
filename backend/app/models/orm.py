
"""SQLAlchemy ORM models for projects / episodes / characters / assets / jobs."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, JSON, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Project(Base):
    """A manga/anime drama project. Top-level container."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cover_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    style: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # anime style preset
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    episodes: Mapped[list["Episode"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    characters: Mapped[list["Character"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    scenes: Mapped[list["Scene"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Episode(Base):
    """A single episode in a project."""

    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft/generating/done/failed
    script: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # LLM 生成的分镜脚本 JSON
    video_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped[Project] = relationship(back_populates="episodes")
    shots: Mapped[list["Shot"]] = relationship(back_populates="episode", cascade="all, delete-orphan")


class Shot(Base):
    """A single shot (storyboard panel) in an episode."""

    __tablename__ = "shots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer, default=0)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dialogue: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    speaker: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    emotion: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    duration: Mapped[float] = mapped_column(Float, default=4.0)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)   # 分镜图
    video_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)   # 片段视频
    audio_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)   # 配音
    source_panel_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # 关联原漫画格
    model_backend: Mapped[str] = mapped_column(String(32), default="hailuo")  # hailuo/seedance/comfyui
    status: Mapped[str] = mapped_column(String(32), default="pending")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    episode: Mapped[Episode] = relationship(back_populates="shots")


class Character(Base):
    """Character consistency: name, reference images, LoRA, voice."""

    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_images: Mapped[list] = mapped_column(JSON, default=list)
    lora_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip_adapter_image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    voice_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cluster_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # 自动识别聚类id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project] = relationship(back_populates="characters")


class Scene(Base):
    """Scene / background consistency."""

    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_images: Mapped[list] = mapped_column(JSON, default=list)
    style_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="scenes")


class MangaUpload(Base):
    """A raw manga upload (PDF / long-strip / multi-image)."""

    __tablename__ = "manga_uploads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(300))
    file_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(20))  # pdf / image / zip
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MangaPanel(Base):
    """Detected panel from manga upload."""

    __tablename__ = "manga_panels"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    upload_id: Mapped[str] = mapped_column(ForeignKey("manga_uploads.id", ondelete="CASCADE"))
    page: Mapped[int] = mapped_column(Integer, default=0)
    order: Mapped[int] = mapped_column(Integer, default=0)  # 阅读顺序
    bbox: Mapped[list] = mapped_column(JSON, default=list)  # [x1,y1,x2,y2]
    image_path: Mapped[str] = mapped_column(String(500))
    ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bubbles: Mapped[list] = mapped_column(JSON, default=list)  # [{bbox,text,speaker}]
    character_ids: Mapped[list] = mapped_column(JSON, default=list)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class Job(Base):
    """Background job tracking (celery task wrapper)."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(50))  # manga2anime / shot_generate / episode_render
    project_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    episode_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/success/failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Asset(Base):
    """Generic asset (image/audio/video/bgm)."""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))  # image/audio/video/bgm/subtitle
    name: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(500))
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    size: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SystemConfig(Base):
    """UI-managed configuration for model providers (api keys / endpoints).

    One row per provider (hailuo / seedance / llm / tts / comfyui).
    The `config` JSON column stores plain fields; sensitive values inside it
    (api_key, group_id, etc.) are encrypted via `utils.crypto.encrypt`.
    """

    __tablename__ = "system_configs"

    provider: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_test_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
