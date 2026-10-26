"""Novel upload + novel analyze routes.

小说深度拆解：文本 → 角色设定 / 剧本结构 / 分镜（时刻/角色衣着/动作/神态/环境/prompt）。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..celery_app import task_novel_analyze
from ..core.config import settings
from ..db import get_db
from ..models.orm import Job, MangaUpload, Project
from ..schemas import (
    NovelAnalyzeRequest,
    MangaUploadOut,
    JobOut,
    ResponseModel,
)


router = APIRouter(prefix="/novel", tags=["novel"])


ALLOWED_EXT = {".txt", ".md"}
MAX_INLINE_TEXT = 200_000  # 直接粘贴文本上限（字符）
MAX_FILE_SIZE = 5 * 1024 * 1024  # 文件上限 5MB


@router.post("/upload", response_model=MangaUploadOut)
def upload_novel(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传 .txt / .md 小说文件（复用 MangaUpload 表，file_type='novel'）。"""
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"仅支持 .txt / .md 文本文件，收到：{ext}")

    upload_dir = settings.UPLOAD_DIR_PATH / project_id / "novel"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dst = upload_dir / (file.filename or f"upload{ext}")
    with dst.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    if dst.stat().st_size > MAX_FILE_SIZE:
        dst.unlink(missing_ok=True)
        raise HTTPException(400, f"文件过大，上限 {MAX_FILE_SIZE // 1024 // 1024}MB")

    record = MangaUpload(
        project_id=project_id,
        filename=dst.name,
        file_path=str(dst),
        file_type="novel",
        status="uploaded",
    )
    db.add(record); db.commit(); db.refresh(record)
    return record


@router.get("/uploads/{project_id}", response_model=list[MangaUploadOut])
def list_novel_uploads(project_id: str, db: Session = Depends(get_db)):
    """只返回 file_type='novel' 的小说上传记录。"""
    return (
        db.query(MangaUpload)
        .filter(MangaUpload.project_id == project_id, MangaUpload.file_type == "novel")
        .all()
    )


@router.post("/analyze", response_model=JobOut)
def analyze_novel(body: NovelAnalyzeRequest, db: Session = Depends(get_db)):
    """小说深度剖析：拆解为角色 / 剧本 / 分镜细节；不生成视频，仅输出 JSON 报告。

    输入两种方式二选一：
      - `novel_text`：直接传正文（适合短篇 / 粘贴）
      - `upload_id`：先用 /novel/upload 上传 .txt，再传此 id（适合长篇）
    """
    # 1. 校验项目
    if not db.get(Project, body.project_id):
        raise HTTPException(404, "project not found")

    # 2. 解析正文内容
    text = (body.novel_text or "").strip()
    if not text and body.upload_id:
        upload = db.get(MangaUpload, body.upload_id)
        if not upload or upload.project_id != body.project_id:
            raise HTTPException(404, "upload not found")
        if upload.file_type != "novel":
            raise HTTPException(400, f"upload 不是小说类型（file_type={upload.file_type}）")
        try:
            text = Path(upload.file_path).read_text(encoding="utf-8", errors="ignore").strip()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"读取小说文件失败：{e}") from e

    if not text:
        raise HTTPException(400, "请提供 novel_text 或 upload_id")
    if len(text) > MAX_INLINE_TEXT:
        raise HTTPException(
            400,
            f"文本过长（{len(text)} 字 > 上限 {MAX_INLINE_TEXT} 字），"
            f"请拆成多次调用，或先 /novel/upload 后传 upload_id",
        )

    # 3. 创建 Job + 投递 celery
    payload = body.model_dump()
    payload["novel_text"] = text  # 规整后的最终文本
    job = Job(
        type="novel_analyze",
        project_id=body.project_id,
        status="pending",
        payload={**payload, "novel_text_len": len(text)},  # 持久化时不存全文（省空间）
    )
    db.add(job); db.commit(); db.refresh(job)

    async_result = task_novel_analyze.delay(job.id, body.project_id, payload)
    job.celery_task_id = async_result.id
    db.add(job); db.commit(); db.refresh(job)
    return job


@router.delete("/uploads/{upload_id}", response_model=ResponseModel)
def delete_novel_upload(upload_id: str, db: Session = Depends(get_db)):
    u = db.get(MangaUpload, upload_id)
    if not u or u.file_type != "novel":
        raise HTTPException(404, "novel upload not found")
    try:
        Path(u.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(u); db.commit()
    return ResponseModel(message="deleted")
