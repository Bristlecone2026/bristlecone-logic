from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_db
from app.models import Project, User
from app.schemas import ProjectCreate, ProjectResponse
from app.api.deps import get_current_user
from app.core.security import verify_api_key

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_context: dict = Depends(verify_api_key)
):
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not assigned to an organization"
        )
    
    proj = Project(
        name=payload.name,
        description=payload.description,
        organization_id=current_user.organization_id
    )
    db.add(proj)
    await db.commit()
    await db.refresh(proj)
    return proj

@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_context: dict = Depends(verify_api_key)
):
    if not current_user.organization_id:
        return []

    result = await db.execute(
        select(Project).where(Project.organization_id == current_user.organization_id)
    )
    return result.scalars().all()
