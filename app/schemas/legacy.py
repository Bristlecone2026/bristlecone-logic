from pydantic import BaseModel, ConfigDict
from typing import Optional, Any, Dict
from datetime import datetime

# System Logs
class SystemLogBase(BaseModel):
    level: str
    message: str
    payload: Optional[Dict[str, Any]] = None

class SystemLogCreate(SystemLogBase):
    pass

class SystemLogResponse(SystemLogBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Organizations
class OrganizationBase(BaseModel):
    name: str
    slug: Optional[str] = None

class OrganizationCreate(OrganizationBase):
    pass

class OrganizationResponse(OrganizationBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Projects
class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectCreate(ProjectBase):
    organization_id: Optional[int] = None

class ProjectResponse(ProjectBase):
    id: int
    organization_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Users
class UserBase(BaseModel):
    email: str
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str
    organization_id: Optional[int] = None

class UserResponse(UserBase):
    id: int
    organization_id: Optional[int] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Auth Tokens
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    org_id: Optional[int] = None
