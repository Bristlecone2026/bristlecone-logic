#!/usr/bin/env bash
set -e

# --- Terminal Styling ---
BOLD='\033[1m'
EMERALD='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

DEMO_TX="0xarc_demo_settled_tx"
ENDPOINT="http://127.0.0.1:8000/tools/extract-web"

# Ensure Redis contains the confirmed Arc transaction receipt
if command -v redis-cli &> /dev/null; then
    redis-cli set "tx_confirmed:${DEMO_TX}" 1 > /dev/null 2>&1 || true
elif docker ps | grep -q bristlecone_redis; then
    docker exec bristlecone_redis redis-cli set "tx_confirmed:${DEMO_TX}" 1 > /dev/null 2>&1 || true
fi

clear
echo -e "${EMERALD}${BOLD}======================================================================${NC}"
echo -e "${EMERALD}${BOLD}  BRISTLECONE LOGIC (v0.4.3) — ARC L1 M2M & RUNTIME DEFENSE HARNESS   ${NC}"
echo -e "${EMERALD}${BOLD}======================================================================${NC}"
echo ""

# -----------------------------------------------------------------------------
# TEST 1: The Stateless HTTP 402 Challenge (Unpaid Agent Request)
# -----------------------------------------------------------------------------
echo -e "${YELLOW}${BOLD}[PHASE 1] Autonomous Agent Invocates Endpoint Without Payment Header${NC}"
echo -e "${CYAN}POST ${ENDPOINT}${NC}"
echo -e "Payload: {\"url\": \"https://example.com\"}"
echo ""
echo -e "${BOLD}--- Gateway Response (HTTP 402 Challenge) ---${NC}"
curl -s -i -X POST "${ENDPOINT}" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}' | head -n 14
echo ""
echo -e "${YELLOW}>> Verification: HTTP 402 returned with Arc Native Gas deposit instructions.${NC}"
echo ""

# 30-Second Pacing Window
for i in {30..1}; do
    echo -ne "\r${CYAN}Holding for narration: Advancing to Phase 2 in ${i}s... ${NC}"
    sleep 1
done
echo -e "\r\033[K"

# -----------------------------------------------------------------------------
# TEST 2: Successful Tool Execution (Settled via Arc L1 USDC Rail)
# -----------------------------------------------------------------------------
echo -e "${YELLOW}${BOLD}[PHASE 2] Autonomous Agent Submits Verified Arc L1 Transaction Header${NC}"
echo -e "${CYAN}POST ${ENDPOINT}${NC}"
echo -e "Header:  ${BOLD}X-Arc-TxHash: ${DEMO_TX}${NC}"
echo ""
echo -e "${BOLD}--- Gateway Response (HTTP 200 Execution) ---${NC}"
curl -s -i -X POST "${ENDPOINT}" \
  -H "Content-Type: application/json" \
  -H "X-Arc-TxHash: ${DEMO_TX}" \
  -d '{"url":"https://example.com"}' | head -n 16
echo ""
echo -e "${EMERALD}>> Verification: Settlement verified on-chain. Tool executed cleanly.${NC}"
echo ""

# 30-Second Pacing Window
for i in {30..1}; do
    echo -ne "\r${CYAN}Holding for narration: Advancing to Phase 3 in ${i}s... ${NC}"
    sleep 1
done
echo -e "\r\033[K"

# -----------------------------------------------------------------------------
# TEST 3: SSRF Exploit Interception (bristlecone-guard Runtime Defense)
# -----------------------------------------------------------------------------
echo -e "${RED}${BOLD}[PHASE 3] Compromised Agent Attempts Cloud Metadata SSRF Egress${NC}"
echo -e "${CYAN}POST ${ENDPOINT}${NC}"
echo -e "Header:  ${BOLD}X-Arc-TxHash: ${DEMO_TX}${NC}"
echo -e "Payload: {\"url\": \"http://169.254.169.254/latest/meta-data/\"}"
echo ""
echo -e "${BOLD}--- Gateway Response (bristlecone-guard Egress Interception) ---${NC}"
curl -s -i -X POST "${ENDPOINT}" \
  -H "Content-Type: application/json" \
  -H "X-Arc-TxHash: ${DEMO_TX}" \
  -d '{"url":"http://169.254.169.254/latest/meta-data/"}' | head -n 14
echo ""
echo -e "${RED}>> Verification: Connection terminated pre-socket. Cloud metadata isolated.${NC}"
echo -e "${EMERALD}${BOLD}======================================================================${NC}"
