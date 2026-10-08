
"""Manga upload + manga->anime orchestration routes."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..celery_app import task_manga2anime
from ..core.config import settings
from ..db import get_db
from ..models.orm import Job, MangaUpload, Project
from ..schemas import Manga2AnimeRequest, MangaUploadOut, JobOut, ResponseModel


router = APIRouter(prefix="/manga", tags=["manga"])


ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".zip"}


@router.post("/upload", response_model=MangaUploadOut)
def upload_manga(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"unsupported file type: {ext}")

    upload_dir = settings.UPLOAD_DIR / project_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    dst = upload_dir / (file.filename or f"upload{ext}")
    with dst.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    file_type = "pdf" if ext == ".pdf" else ("zip" if ext == ".zip" else "image")
    record = MangaUpload(
        project_id=project_id,
        filename=dst.name,
        file_path=str(dst),
        file_type=file_type,
        status="uploaded",
    )
    db.add(record); db.commit(); db.refresh(record)
    return record


@router.get("/uploads/{project_id}", response_model=list[MangaUploadOut])
def list_uploads(project_id: str, db: Session = Depends(get_db)):
    return db.query(MangaUpload).filter(MangaUpload.project_id == project_id).all()


@router.post("/convert", response_model=JobOut)
def convert_manga(body: Manga2AnimeRequest, db: Session = Depends(get_db)):
    """Kick off the manga -> anime pipeline as a Celery job."""
    upload = db.get(MangaUpload, body.upload_id)
    if not upload or upload.project_id != body.project_id:
        raise HTTPException(404, "upload not found")

    job = Job(
        type="manga2anime",
        project_id=body.project_id,
        status="pending",
        payload=body.model_dump(),
    )
    db.add(job); db.commit(); db.refresh(job)

    async_result = task_manga2anime.delay(
        job.id, body.upload_id, body.project_id, body.model_dump()
    )
    job.celery_task_id = async_result.id
    db.add(job); db.commit(); db.refresh(job)
    return job


@router.delete("/uploads/{upload_id}", response_model=ResponseModel)
def delete_upload(upload_id: str, db: Session = Depends(get_db)):
    u = db.get(MangaUpload, upload_id)
    if not u:
        raise HTTPException(404, "upload not found")
    try:
        Path(u.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(u); db.commit()
    return ResponseModel(message="deleted")
