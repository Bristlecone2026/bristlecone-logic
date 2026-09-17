import asyncio
import time
import random
from typing import List, Callable, Any, Optional
from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider

class CircuitState:
    CLOSED = "CLOSED"       # Healthy: requests flow through active RPC
    OPEN = "OPEN"           # Tripped: failover/backoff in progress
    HALF_OPEN = "HALF_OPEN" # Probing: testing endpoint recovery

class RpcCircuitBreaker:
    def __init__(
        self,
        network_name: str,
        endpoints: List[str],
        failure_threshold: int = 3,
        recovery_time_secs: float = 30.0,
        max_backoff_secs: float = 60.0
    ):
        self.network_name = network_name
        self.endpoints = [ep.strip() for ep in endpoints if ep.strip()]
        if not self.endpoints:
            raise ValueError(f"No RPC endpoints provided for {network_name}")

        self.current_idx = 0
        self.failure_threshold = failure_threshold
        self.recovery_time_secs = recovery_time_secs
        self.max_backoff_secs = max_backoff_secs

        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.last_failure_time = 0.0
        self.backoff_delay = 2.0
        self._w3: Optional[AsyncWeb3] = None
        self._init_w3()

    def _init_w3(self):
        active_url = self.endpoints[self.current_idx]
        self._w3 = AsyncWeb3(AsyncHTTPProvider(active_url, request_kwargs={"timeout": 6.0}))

    @property
    def w3(self) -> AsyncWeb3:
        return self._w3

    @property
    def active_url(self) -> str:
        return self.endpoints[self.current_idx]

    def record_success(self):
        if self.state != CircuitState.CLOSED:
            print(f"[{self.network_name} ResilientRPC] Circuit healed -> State CLOSED on {self.active_url}")
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.backoff_delay = 2.0

    async def record_failure(self, error: Exception, alert_fn: Optional[Callable[[str], Any]] = None):
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        print(f"[{self.network_name} ResilientRPC] Failure {self.consecutive_failures}/{self.failure_threshold} on {self.active_url}: {error}")

        if self.consecutive_failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            old_url = self.active_url
            self.current_idx = (self.current_idx + 1) % len(self.endpoints)
            new_url = self.active_url
            self._init_w3()

            # Add jitter to backoff
            jitter = random.uniform(0.5, 1.5)
            self.backoff_delay = min(self.backoff_delay * 2, self.max_backoff_secs) * jitter

            warn_msg = (
                f"⚠️ **[{self.network_name} RPC Circuit Breaker Tripped]**\n"
                f"• **Failed Node**: `{old_url}`\n"
                f"• **Failing Over To**: `{new_url}`\n"
                f"• **Backoff Delay**: `{self.backoff_delay:.2f}s`"
            )
            print(f"[{self.network_name} ResilientRPC] Circuit OPEN. Rotated to {new_url}. Backoff {self.backoff_delay:.2f}s")
            if alert_fn:
                try:
                    await alert_fn(warn_msg)
                except Exception:
                    pass

        await asyncio.sleep(self.backoff_delay)

    async def execute_with_resilience(self, func: Callable[[AsyncWeb3], Any], alert_fn: Optional[Callable[[str], Any]] = None) -> Any:
        try:
            res = await func(self._w3)
            self.record_success()
            return res
        except Exception as e:
            await self.record_failure(e, alert_fn)
            raise
