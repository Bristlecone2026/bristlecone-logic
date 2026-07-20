from typing import Dict, Any
from pydantic import BaseModel


class WalletBalance(BaseModel):
    asset: str
    balance: float
    status: str


class TreasuryLedger:
    def __init__(self):
        # Baseline entity financial safety gates
        self.max_single_tx_usd: float = 50.00
        self.mock_balances: Dict[str, float] = {
            "XRP": 1000.0,
            "USD_MERCURY": 500.00
        }

    def verify_transaction_safety(self, amount_usd: float) -> bool:
        """Financial Safety Gate check per AGENTS.md."""
        if amount_usd > self.max_single_tx_usd:
            return False
        return True

    def get_treasury_summary(self) -> Dict[str, Any]:
        return {
            "entity": "Bristlecone Logic, LLC",
            "treasury_status": "active",
            "safety_gate_limit_usd": self.max_single_tx_usd,
            "balances": self.mock_balances
        }


treasury = TreasuryLedger()
