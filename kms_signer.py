import os
import boto3
from dotenv import load_dotenv
from eth_utils import keccak, to_checksum_address
from pyasn1.codec.der import decoder
from eth_keys import keys

load_dotenv('/opt/bristlecone/bristlecone-logic/.env')

SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_HALF_N = SECP256K1_N // 2

def rlp_encode(input_data):
    """Minimal, self-contained RLP encoder for EIP-1559 transaction fields."""
    if isinstance(input_data, bytes):
        if len(input_data) == 1 and input_data[0] < 0x80:
            return input_data
        elif len(input_data) < 55:
            return bytes([0x80 + len(input_data)]) + input_data
        else:
            len_bytes = len(input_data).to_bytes((len(input_data).bit_length() + 7) // 8, 'big')
            return bytes([0xb7 + len(len_bytes)]) + len_bytes + input_data
    elif isinstance(input_data, list):
        output = b''.join(rlp_encode(item) for item in input_data)
        if len(output) < 55:
            return bytes([0xc0 + len(output)]) + output
        else:
            len_bytes = len(output).to_bytes((len(output).bit_length() + 7) // 8, 'big')
            return bytes([0xf7 + len(len_bytes)]) + len_bytes + output
    elif isinstance(input_data, int):
        if input_data == 0:
            return b'\x80'
        b = input_data.to_bytes((input_data.bit_length() + 7) // 8, 'big')
        return rlp_encode(b)
    elif input_data is None:
        return b'\x80'
    raise TypeError(f"Unsupported RLP type: {type(input_data)}")

def get_kms_address(kms, kms_key_id):
    """Derives expected EVM checksum address from AWS KMS SubjectPublicKeyInfo."""
    pub_res = kms.get_public_key(KeyId=kms_key_id)
    der_bytes = pub_res['PublicKey']
    # Uncompressed secp256k1 key is 65 bytes starting with 0x04 at the end of SubjectPublicKeyInfo
    raw_pub_64 = der_bytes[-64:]
    return to_checksum_address('0x' + keccak(raw_pub_64)[-20:].hex())

def parse_der_signature(sig_bytes):
    """Extracts r and s from DER format and enforces EIP-2 Low-S canonicality."""
    asn1_obj, _ = decoder.decode(sig_bytes)
    r = int(asn1_obj[0])
    s = int(asn1_obj[1])
    
    if s > SECP256K1_HALF_N:
        s = SECP256K1_N - s
        
    return r, s

def get_v_and_recover_address(digest, r, s, expected_address):
    """Finds recovery byte v (0 or 1) and verifies signature against expected address."""
    recovered = []
    for v in [0, 1]:
        sig = keys.Signature(vrs=(v, r, s))
        pub_key = sig.recover_public_key_from_msg_hash(digest)
        addr = pub_key.to_checksum_address()
        recovered.append((v, addr))
        if addr.lower() == expected_address.lower():
            return v, addr
    raise ValueError(
        f"Could not match signature to expected address {expected_address}.\n"
        f"Recovered: v=0 -> {recovered[0][1]}, v=1 -> {recovered[1][1]}"
    )

def sign_eip1559_transaction(tx_fields, kms_key_id, region_name='us-west-2'):
    kms = boto3.client('kms', region_name=region_name)
    expected_address = get_kms_address(kms, kms_key_id)

    to_bytes = bytes.fromhex(tx_fields['to'][2:]) if tx_fields['to'].startswith('0x') else bytes.fromhex(tx_fields['to'])
    
    unsigned_list = [
        tx_fields['chain_id'],
        tx_fields['nonce'],
        tx_fields['max_priority_fee_per_gas'],
        tx_fields['max_fee_per_gas'],
        tx_fields['gas_limit'],
        to_bytes,
        tx_fields['value'],
        tx_fields['data'],
        tx_fields['access_list']
    ]

    unsigned_payload = b'\x02' + rlp_encode(unsigned_list)
    tx_digest = keccak(unsigned_payload)

    kms_response = kms.sign(
        KeyId=kms_key_id,
        Message=tx_digest,
        MessageType='DIGEST',
        SigningAlgorithm='ECDSA_SHA_256'
    )
    
    r, s = parse_der_signature(kms_response['Signature'])
    v, recovered_address = get_v_and_recover_address(tx_digest, r, s, expected_address)

    signed_list = unsigned_list + [
        v,
        r.to_bytes(32, 'big'),
        s.to_bytes(32, 'big')
    ]
    raw_signed_tx = b'\x02' + rlp_encode(signed_list)

    return {
        'raw_transaction': '0x' + raw_signed_tx.hex(),
        'tx_hash': '0x' + keccak(raw_signed_tx).hex(),
        'from_address': recovered_address,
        'r': hex(r),
        's': hex(s),
        'v': v
    }

if __name__ == '__main__':
    print("\n--- Running Offline AWS KMS EIP-1559 Signing Test ---")
    kms_id = os.getenv('AWS_KMS_KEY_ID')
    region = os.getenv('AWS_REGION', 'us-west-2')

    sample_tx = {
        'chain_id': 8453,
        'nonce': 0,
        'max_priority_fee_per_gas': 1000000,      # 0.001 gwei
        'max_fee_per_gas': 100000000,            # 0.1 gwei
        'gas_limit': 21000,                       # Standard transfer
        'to': '0x0000000000000000000000000000000000000000',
        'value': 1000000000000000,                # 0.001 ETH
        'data': b'',
        'access_list': []
    }

    result = sign_eip1559_transaction(sample_tx, kms_id, region)
    
    print(f"Signer Address:   {result['from_address']}")
    print(f"Signature R:      {result['r'][:18]}...")
    print(f"Signature S:      {result['s'][:18]}...")
    print(f"Recovery V:       {result['v']}")
    print(f"Tx Hash:          {result['tx_hash']}")
    print(f"Raw Signed Tx:    {result['raw_transaction'][:30]}...[TRUNCATED]")
    print("\n[SUCCESS] KMS offline signature successfully verified against operational hot wallet!\n")
