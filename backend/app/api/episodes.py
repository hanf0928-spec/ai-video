
"""Episodes & shots routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.orm import Episode, Shot
from ..schemas import (
    EpisodeCreate, EpisodeOut,
    ShotCreate, ShotUpdate, ShotOut,
    ResponseModel,
)


router = APIRouter(tags=["episodes"])


# ----- Episodes -----
@router.get("/projects/{project_id}/episodes", response_model=list[EpisodeOut])
def list_episodes(project_id: str, db: Session = Depends(get_db)):
    return db.query(Episode).filter(Episode.project_id == project_id).order_by(Episode.index).all()


@router.post("/episodes", response_model=EpisodeOut)
def create_episode(body: EpisodeCreate, db: Session = Depends(get_db)):
    ep = Episode(**body.model_dump())
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return ep


@router.get("/episodes/{episode_id}", response_model=EpisodeOut)
def get_episode(episode_id: str, db: Session = Depends(get_db)):
    ep = db.get(Episode, episode_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    return ep


@router.delete("/episodes/{episode_id}", response_model=ResponseModel)
def delete_episode(episode_id: str, db: Session = Depends(get_db)):
    ep = db.get(Episode, episode_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    db.delete(ep)
    db.commit()
    return ResponseModel(message="deleted")


# ----- Shots -----
@router.get("/episodes/{episode_id}/shots", response_model=list[ShotOut])
def list_shots(episode_id: str, db: Session = Depends(get_db)):
    return db.query(Shot).filter(Shot.episode_id == episode_id).order_by(Shot.index).all()


@router.post("/shots", response_model=ShotOut)
def create_shot(body: ShotCreate, db: Session = Depends(get_db)):
    shot = Shot(**body.model_dump())
    db.add(shot)
    db.commit()
    db.refresh(shot)
    return shot


@router.patch("/shots/{shot_id}", response_model=ShotOut)
def update_shot(shot_id: str, body: ShotUpdate, db: Session = Depends(get_db)):
    shot = db.get(Shot, shot_id)
    if not shot:
        raise HTTPException(404, "shot not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(shot, k, v)
    db.add(shot)
    db.commit()
    db.refresh(shot)
    return shot


@router.delete("/shots/{shot_id}", response_model=ResponseModel)
def delete_shot(shot_id: str, db: Session = Depends(get_db)):
    shot = db.get(Shot, shot_id)
    if not shot:
        raise HTTPException(404, "shot not found")
    db.delete(shot)
    db.commit()
    return ResponseModel(message="deleted")
