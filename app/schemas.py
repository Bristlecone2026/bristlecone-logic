from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict

# System Log
class SystemLogCreate(BaseModel):
    level: str
    message: str
    payload: Optional[Dict[str, Any]] = None

class SystemLogResponse(SystemLogCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Auth & User
class UserCreate(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None
    organization_id: Optional[int] = None

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    organization_id: Optional[int] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None

# Organization
class OrganizationCreate(BaseModel):
    name: str
    slug: str

class OrganizationResponse(OrganizationCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Project
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    organization_id: int

class ProjectResponse(ProjectCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
