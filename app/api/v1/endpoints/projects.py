from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_db
from app.models import Project, User
from app.schemas import ProjectCreate, ProjectResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    proj = Project(
        name=payload.name,
        description=payload.description,
        organization_id=payload.organization_id
    )
    db.add(proj)
    await db.commit()
    await db.refresh(proj)
    return proj

@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Project))
    return result.scalars().all()
