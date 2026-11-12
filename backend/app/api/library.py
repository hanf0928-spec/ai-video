
"""Characters & scenes routes."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db import get_db
from ..models.orm import Character, Scene
from ..schemas import (
    CharacterCreate, CharacterOut,
    SceneCreate, SceneOut,
    ResponseModel,
)


router = APIRouter(tags=["library"])

_ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


# ----- Characters -----
@router.get("/projects/{project_id}/characters", response_model=list[CharacterOut])
def list_characters(project_id: str, db: Session = Depends(get_db)):
    return db.query(Character).filter(Character.project_id == project_id).all()


@router.post("/characters", response_model=CharacterOut)
def create_character(body: CharacterCreate, db: Session = Depends(get_db)):
    c = Character(**body.model_dump())
    db.add(c); db.commit(); db.refresh(c)
    return c


@router.delete("/characters/{character_id}", response_model=ResponseModel)
def delete_character(character_id: str, db: Session = Depends(get_db)):
    c = db.get(Character, character_id)
    if not c:
        raise HTTPException(404, "character not found")
    db.delete(c); db.commit()
    return ResponseModel(message="deleted")


@router.post("/characters/{character_id}/avatar", response_model=CharacterOut)
def upload_character_avatar(
    character_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传角色形象参考图（用于保持角色一致性）。

    生成分镜视频时，若该分镜涉及此角色，会自动把这张图作为参考图
    （海螺03 R2VA role=reference_image）附加到生成请求，约束角色外观一致。
    一个角色只保留一张主形象图，重新上传会覆盖旧图。
    """
    c = db.get(Character, character_id)
    if not c:
        raise HTTPException(404, "character not found")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXT:
        raise HTTPException(400, f"unsupported image type: {ext}（仅支持 png/jpg/jpeg/webp）")

    upload_dir = settings.UPLOAD_DIR_PATH / c.project_id / "characters"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dst = upload_dir / f"{character_id}{ext}"
    with dst.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # 清理同角色下其他扩展名的旧图（避免重复上传不同格式后残留多张）
    for old in upload_dir.glob(f"{character_id}.*"):
        if old.resolve() != dst.resolve():
            old.unlink(missing_ok=True)

    c.reference_images = [str(dst)]
    db.add(c); db.commit(); db.refresh(c)
    return c


@router.delete("/characters/{character_id}/avatar", response_model=CharacterOut)
def delete_character_avatar(character_id: str, db: Session = Depends(get_db)):
    c = db.get(Character, character_id)
    if not c:
        raise HTTPException(404, "character not found")
    for img in (c.reference_images or []):
        try:
            Path(img).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    c.reference_images = []
    db.add(c); db.commit(); db.refresh(c)
    return c


# ----- Scenes -----
@router.get("/projects/{project_id}/scenes", response_model=list[SceneOut])
def list_scenes(project_id: str, db: Session = Depends(get_db)):
    return db.query(Scene).filter(Scene.project_id == project_id).all()


@router.post("/scenes", response_model=SceneOut)
def create_scene(body: SceneCreate, db: Session = Depends(get_db)):
    s = Scene(**body.model_dump())
    db.add(s); db.commit(); db.refresh(s)
    return s


@router.delete("/scenes/{scene_id}", response_model=ResponseModel)
def delete_scene(scene_id: str, db: Session = Depends(get_db)):
    s = db.get(Scene, scene_id)
    if not s:
        raise HTTPException(404, "scene not found")
    db.delete(s); db.commit()
    return ResponseModel(message="deleted")
