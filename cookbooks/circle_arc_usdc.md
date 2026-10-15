# Circle & Arc L1 USDC Integration Guide

Bristlecone Logic acts as the inbound payment tollbooth for agentic transactions settling on **Circle Arc L1** and **Base L2** networks via HTTP 402 challenges.

### How the HTTP 402 Paywall Works
1. **The Request:** An autonomous agent invokes a guarded tool (core `/tools/extract-web` or Dendro resin gateway `/v1/tools/extract`).
2. **The Challenge:** The gateway intercepts the call and responds with an **HTTP 402 Payment Required** status code.
3. **The Challenge Headers (`PAYMENT-REQUIRED`):** Includes multi-rail payout addresses, atomic token amounts, and target network IDs (`eip155:5042` for Arc L1 native USDC or `eip155:8453` for Base ERC-20 USDC).
4. **The Settlement:** The agent's embedded wallet broadcasts the transfer on-chain.
5. **The Resubmission:** The agent re-submits the tool request accompanied by the transaction hash header (`X-Payment-TxHash` or `X-Arc-TxHash`).
6. **Execution:** The gateway verifies the transaction hash against Redis and releases the requested data payload instantly.

### Python Verification Sample
```python
import httpx

TOOL_URL = "[https://api.bristleconelogic.com/tools/extract-web](https://api.bristleconelogic.com/tools/extract-web)"

# Step 1: Initial invocation triggers 402 challenge
resp = httpx.post(TOOL_URL, json={"url": "[https://example.com](https://example.com)"})
if resp.status_code == 402:
    challenge = resp.json()
    pay_to = challenge["accepts"][0]["payTo"]
    amount = challenge["accepts"][0]["amount"]
    print(f"Payment Required: Send {amount} atomic units to {pay_to}")
    
    # Step 2: Resubmit after wallet broadcast
    # verified = httpx.post(
    #     TOOL_URL, 
    #     json={"url": "[https://example.com](https://example.com)"}, 
    #     headers={"X-Payment-TxHash": tx_hash}
    # )
    # print(verified.json())
```
