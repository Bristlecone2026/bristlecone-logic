from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_db
from app.models import Organization, User
from app.schemas import OrganizationCreate, OrganizationResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/organizations", tags=["Organizations"])

@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    org = Organization(name=payload.name, slug=payload.slug)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org

@router.get("", response_model=List[OrganizationResponse])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Organization))
    return result.scalars().all()
