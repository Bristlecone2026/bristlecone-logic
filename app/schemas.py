from datetime import datetime
from pydantic import BaseModel, ConfigDict

class SystemLogCreate(BaseModel):
    event_type: str
    message: str

class SystemLogResponse(SystemLogCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
