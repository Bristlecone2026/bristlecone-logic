import os
import time
import json
import urllib.request
from dotenv import load_dotenv
from kms_signer import sign_eip1559_transaction, get_kms_address
import boto3

load_dotenv('/opt/bristlecone/bristlecone-logic/.env')

# RPC Configurations
BASE_RPC_URLS = [
    'https://mainnet.base.org',
    'https://base.llamarpc.com',
    'https://1rpc.io/base'
]

ARC_RPC_URLS = [
    'https://rpc.mainnet.arc.io'
]

# Contracts & Targets
BASE_USDC_CONTRACT = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
DESTINATION_ADDRESS = os.getenv('SWEEP_DESTINATION_ADDRESS', '0x0000000000000000000000000000000000000000')
DRY_RUN_MODE = os.getenv('DRY_RUN_MODE', 'true').lower() in ('true', '1', 'yes')

POLL_INTERVAL_SECONDS = 15

# Thresholds
MIN_BASE_USDC_THRESHOLD = 5_000_000                   # 5.0 USDC (6 decimals)
MIN_ARC_USDC_THRESHOLD = 5_000_000_000_000_000_000    # 5.0 USDC (18 decimals)
MIN_ETH_GAS_RESERVOIR_WEI = 500_000_000_000_000       # 0.0005 ETH warning threshold

def rpc_call(rpc_urls, method, params=[]):
    """Fallback-enabled JSON-RPC client."""
    for rpc in rpc_urls:
        try:
            req = urllib.request.Request(
                rpc,
                data=json.dumps({'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}).encode('utf-8'),
                headers={'Content-Type': 'application/json', 'User-Agent': 'Bristlecone-Sweeper/1.0'}
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=5).read().decode('utf-8'))
            if 'result' in resp:
                return resp['result']
        except Exception:
            continue
    raise ConnectionError(f"All RPC endpoints failed for {rpc_urls}")

def get_gas_estimates(rpc_urls):
    """Fetches base fee and estimates EIP-1559 gas params."""
    latest_block = rpc_call(rpc_urls, 'eth_getBlockByNumber', ['latest', False])
    base_fee = int(latest_block['baseFeePerGas'], 16)
    max_priority_fee = 50_000_000  # 0.05 gwei
    max_fee = (base_fee * 2) + max_priority_fee
    return max_priority_fee, max_fee

def encode_erc20_transfer(to_address, amount_raw):
    """Encodes ERC-20 transfer(address,uint256) call data."""
    padded_to = to_address[2:].lower().zfill(64)
    padded_amount = hex(amount_raw)[2:].zfill(64)
    return bytes.fromhex('a9059cbb' + padded_to + padded_amount)

def sweep_base(hot_wallet, kms_id, region):
    """Checks and sweeps ERC-20 USDC on Base L2."""
    eth_bal_hex = rpc_call(BASE_RPC_URLS, 'eth_getBalance', [hot_wallet, 'latest'])
    eth_bal_wei = int(eth_bal_hex, 16)

    padded_addr = hot_wallet[2:].lower().zfill(64)
    data = '0x70a08231' + padded_addr
    res = rpc_call(BASE_RPC_URLS, 'eth_call', [{'to': BASE_USDC_CONTRACT, 'data': data}, 'latest'])
    usdc_raw = int(res, 16)
    usdc_balance = usdc_raw / 1e6

    print(f"[{time.strftime('%H:%M:%S')}] [Base L2] USDC: {usdc_balance:.2f} | ETH Gas: {eth_bal_wei / 1e18:.6f}")

    if usdc_raw >= MIN_BASE_USDC_THRESHOLD:
        print(f" -> [Base L2] Threshold reached ({usdc_balance:.2f} >= 5.0 USDC)")
        gas_limit = 65000
        max_priority_fee, max_fee = get_gas_estimates(BASE_RPC_URLS)
        estimated_gas_cost = gas_limit * max_fee

        if eth_bal_wei < estimated_gas_cost:
            print(" [Base L2 ERROR] Insufficient ETH for gas. Skipping sweep.")
            return

        nonce_hex = rpc_call(BASE_RPC_URLS, 'eth_getTransactionCount', [hot_wallet, 'latest'])
        nonce = int(nonce_hex, 16)
        transfer_data = encode_erc20_transfer(DESTINATION_ADDRESS, usdc_raw)

        tx_payload = {
            'chain_id': 8453,
            'nonce': nonce,
            'max_priority_fee_per_gas': max_priority_fee,
            'max_fee_per_gas': max_fee,
            'gas_limit': gas_limit,
            'to': BASE_USDC_CONTRACT,
            'value': 0,
            'data': transfer_data,
            'access_list': []
        }

        signed_tx = sign_eip1559_transaction(tx_payload, kms_id, region)
        if DRY_RUN_MODE:
            print(f" [Base L2 DRY RUN] Signed Tx: {signed_tx['tx_hash']} -> Sweep {usdc_balance:.2f} USDC to {DESTINATION_ADDRESS}")
        else:
            tx_hash = rpc_call(BASE_RPC_URLS, 'eth_sendRawTransaction', [signed_tx['raw_transaction']])
            print(f" [Base L2 LIVE] Broadcasted sweep: {tx_hash}")

def sweep_arc(hot_wallet, kms_id, region):
    """Checks and sweeps native gas USDC on Arc L1."""
    bal_hex = rpc_call(ARC_RPC_URLS, 'eth_getBalance', [hot_wallet, 'latest'])
    bal_wei = int(bal_hex, 16)
    arc_balance = bal_wei / 1e18

    print(f"[{time.strftime('%H:%M:%S')}] [Arc L1]  Native USDC: {arc_balance:.4f}")

    if bal_wei >= MIN_ARC_USDC_THRESHOLD:
        print(f" -> [Arc L1] Threshold reached ({arc_balance:.4f} >= 5.0 USDC)")
        gas_limit = 21000
        max_priority_fee, max_fee = get_gas_estimates(ARC_RPC_URLS)
        gas_cost = gas_limit * max_fee

        if bal_wei <= gas_cost:
            print(" [Arc L1 ERROR] Balance cannot cover transaction gas fee.")
            return

        sweep_value = bal_wei - gas_cost
        nonce_hex = rpc_call(ARC_RPC_URLS, 'eth_getTransactionCount', [hot_wallet, 'latest'])
        nonce = int(nonce_hex, 16)

        tx_payload = {
            'chain_id': 5042,
            'nonce': nonce,
            'max_priority_fee_per_gas': max_priority_fee,
            'max_fee_per_gas': max_fee,
            'gas_limit': gas_limit,
            'to': DESTINATION_ADDRESS,
            'value': sweep_value,
            'data': b'',
            'access_list': []
        }

        signed_tx = sign_eip1559_transaction(tx_payload, kms_id, region)
        if DRY_RUN_MODE:
            print(f" [Arc L1 DRY RUN] Signed Tx: {signed_tx['tx_hash']} -> Sweep {sweep_value / 1e18:.4f} USDC to {DESTINATION_ADDRESS}")
        else:
            tx_hash = rpc_call(ARC_RPC_URLS, 'eth_sendRawTransaction', [signed_tx['raw_transaction']])
            print(f" [Arc L1 LIVE] Broadcasted sweep: {tx_hash}")

def run_sweeper_loop():
    kms_id = os.getenv('AWS_KMS_KEY_ID')
    region = os.getenv('AWS_REGION', 'us-west-2')
    kms = boto3.client('kms', region_name=region)
    hot_wallet = get_kms_address(kms, kms_id)

    print("=== Bristlecone Multi-Rail USDC Sweeper Daemon Initialized ===")
    print(f"Hot Wallet:       {hot_wallet}")
    print(f"Destination:      {DESTINATION_ADDRESS}")
    print(f"Dry Run Mode:     {DRY_RUN_MODE}")
    print(f"Base Threshold:   {MIN_BASE_USDC_THRESHOLD / 1e6:.2f} USDC (ERC-20)")
    print(f"Arc Threshold:    {MIN_ARC_USDC_THRESHOLD / 1e18:.2f} USDC (Native)")
    print("==============================================================\n")

    while True:
        try:
            sweep_base(hot_wallet, kms_id, region)
        except Exception as e:
            print(f" [Base L2 ERROR] {e}")

        try:
            sweep_arc(hot_wallet, kms_id, region)
        except Exception as e:
            print(f" [Arc L1 ERROR] {e}")

        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == '__main__':
    run_sweeper_loop()
