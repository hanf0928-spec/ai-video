
"""Characters & scenes routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.orm import Character, Scene
from ..schemas import (
    CharacterCreate, CharacterOut,
    SceneCreate, SceneOut,
    ResponseModel,
)


router = APIRouter(tags=["library"])


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
