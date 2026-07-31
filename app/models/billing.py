import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class TenantBalance(Base):
    __tablename__ = "tenant_balances"

    tenant_id = Column(String(255), primary_key=True)
    balance_usd = Column(Numeric(12, 6), nullable=False, default=100.000000)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

class ApiUsageLog(Base):
    __tablename__ = "api_usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    api_key_id = Column(UUID(as_uuid=True), nullable=True)
    endpoint = Column(String(255), nullable=False)
    units_consumed = Column(Integer, nullable=False, default=1)
    cost = Column(Numeric(10, 6), nullable=False, default=0.010000)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
