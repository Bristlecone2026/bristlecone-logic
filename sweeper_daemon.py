import os
import time
import json
import urllib.request
from dotenv import load_dotenv
from kms_signer import sign_eip1559_transaction, get_kms_address
import boto3

load_dotenv('/opt/bristlecone/bristlecone-logic/.env')

# Configuration
BASE_RPC_URLS = [
    'https://mainnet.base.org',
    'https://base.llamarpc.com',
    'https://1rpc.io/base'
]

# Native USDC on Base L2
USDC_CONTRACT_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
DESTINATION_ADDRESS = os.getenv('SWEEP_DESTINATION_ADDRESS', '0x0000000000000000000000000000000000000000')

POLL_INTERVAL_SECONDS = 10
MIN_USDC_SWEEP_THRESHOLD = 5000000  # 5.0 USDC (USDC has 6 decimals)
MIN_ETH_GAS_RESERVOIR_WEI = 500000000000000  # 0.0005 ETH warning threshold
DRY_RUN_MODE = True

def rpc_call(method, params=[]):
    """Fallback-enabled JSON-RPC client."""
    for rpc in BASE_RPC_URLS:
        try:
            req = urllib.request.Request(
                rpc,
                data=json.dumps({'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}).encode('utf-8'),
                headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=5).read().decode('utf-8'))
            if 'result' in resp:
                return resp['result']
        except Exception:
            continue
    raise ConnectionError("All Base RPC endpoints failed.")

def get_gas_estimates():
    """Fetches base fee and estimates EIP-1559 gas params."""
    latest_block = rpc_call('eth_getBlockByNumber', ['latest', False])
    base_fee = int(latest_block['baseFeePerGas'], 16)
    max_priority_fee = 50000000  # 0.05 gwei
    max_fee = (base_fee * 2) + max_priority_fee
    return max_priority_fee, max_fee

def get_usdc_balance(wallet_address):
    """Queries ERC-20 balanceOf(address) on the Base USDC contract."""
    # Selector for balanceOf(address): 0x70a08231
    padded_addr = wallet_address[2:].lower().zfill(64)
    data = '0x70a08231' + padded_addr
    
    res = rpc_call('eth_call', [{'to': USDC_CONTRACT_ADDRESS, 'data': data}, 'latest'])
    return int(res, 16)

def encode_erc20_transfer(to_address, amount_raw):
    """Encodes ERC-20 transfer(address,uint256) call data."""
    # Selector for transfer(address,uint256): 0xa9059cbb
    padded_to = to_address[2:].lower().zfill(64)
    padded_amount = hex(amount_raw)[2:].zfill(64)
    return bytes.fromhex('a9059cbb' + padded_to + padded_amount)

def run_sweeper_loop():
    kms_id = os.getenv('AWS_KMS_KEY_ID')
    region = os.getenv('AWS_REGION', 'us-west-2')
    kms = boto3.client('kms', region_name=region)
    hot_wallet = get_kms_address(kms, kms_id)

    print(f"=== Bristlecone USDC Sweeper Daemon Initialized ===")
    print(f"Hot Wallet:       {hot_wallet}")
    print(f"Token (USDC):     {USDC_CONTRACT_ADDRESS}")
    print(f"Destination:      {DESTINATION_ADDRESS}")
    print(f"Dry Run Mode:     {DRY_RUN_MODE}")
    print(f"Sweep Threshold:  {MIN_USDC_SWEEP_THRESHOLD / 1e6:.2f} USDC")
    print("=====================================================\n")

    while True:
        try:
            # 1. Check ETH Gas Reservoir Balance
            eth_bal_hex = rpc_call('eth_getBalance', [hot_wallet, 'latest'])
            eth_bal_wei = int(eth_bal_hex, 16)
            eth_balance = eth_bal_wei / 1e18

            if eth_bal_wei < MIN_ETH_GAS_RESERVOIR_WEI:
                print(f" [WARNING] Low ETH gas reservoir: {eth_balance:.6f} ETH. Refill needed for L2 gas.")

            # 2. Check USDC Token Balance
            usdc_raw = get_usdc_balance(hot_wallet)
            usdc_balance = usdc_raw / 1e6
            
            nonce_hex = rpc_call('eth_getTransactionCount', [hot_wallet, 'latest'])
            nonce = int(nonce_hex, 16)

            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] USDC Balance: {usdc_balance:.2f} | ETH Gas: {eth_balance:.6f} | Nonce: {nonce}")

            # 3. Trigger Sweep if USDC exceeds threshold
            if usdc_raw >= MIN_USDC_SWEEP_THRESHOLD:
                print(f" -> USDC Threshold triggered! Balance ({usdc_balance:.2f}) >= Min ({MIN_USDC_SWEEP_THRESHOLD / 1e6:.2f})")
                
                # ERC-20 transfer uses ~65,000 gas limit
                gas_limit = 65000
                max_priority_fee, max_fee = get_gas_estimates()
                
                # Verify we have enough ETH to pay gas for this ERC-20 sweep
                estimated_gas_cost = gas_limit * max_fee
                if eth_bal_wei < estimated_gas_cost:
                    print(" [ERROR] Insufficient ETH in reservoir to cover L2 gas fee. Skipping sweep.")
                else:
                    # Construct smart contract call to USDC token contract
                    transfer_data = encode_erc20_transfer(DESTINATION_ADDRESS, usdc_raw)

                    tx_payload = {
                        'chain_id': 8453,
                        'nonce': nonce,
                        'max_priority_fee_per_gas': max_priority_fee,
                        'max_fee_per_gas': max_fee,
                        'gas_limit': gas_limit,
                        'to': USDC_CONTRACT_ADDRESS,  # Target is the USDC contract
                        'value': 0,                   # 0 ETH sent; value is in call data
                        'data': transfer_data,
                        'access_list': []
                    }

                    signed_tx = sign_eip1559_transaction(tx_payload, kms_id, region)
                    
                    if DRY_RUN_MODE:
                        print(f" [DRY RUN SUCCESS] Constructed & signed USDC sweep tx:")
                        print(f"   Tx Hash:     {signed_tx['tx_hash']}")
                        print(f"   Target:      {USDC_CONTRACT_ADDRESS}")
                        print(f"   Amount:      {usdc_balance:.2f} USDC")
                        print(f"   Raw Tx:      {signed_tx['raw_transaction'][:40]}...\n")
                    else:
                        print(" [LIVE BROADCAST] Submitting USDC sweep to network...")
                        tx_hash = rpc_call('eth_sendRawTransaction', [signed_tx['raw_transaction']])
                        print(f" [SUCCESS] Broadcasted! Tx Hash: {tx_hash}\n")

        except Exception as e:
            print(f" [ERROR] Loop exception: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == '__main__':
    run_sweeper_loop()
