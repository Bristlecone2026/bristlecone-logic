from decimal import Decimal
from pydantic import BaseModel, Field

class WebhookTopUpPayload(BaseModel):
    event_type: str = Field(..., example="payment.succeeded")
    tenant_id: str = Field(..., example="4c9219ad-db71-4bb2-96ca-c1c109c781eb")
    amount_usd: Decimal = Field(..., gt=0, example=50.00)
    transaction_id: str = Field(..., example="tx_2026_07_31_001")
