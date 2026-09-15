import urllib.request
import json
import os
import struct
import base64
import time
from typing import Dict, Any

from stocks import STOCKS, USDC

HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY", "5439acc7-b513-4fcd-bb51-c3adfe0756ad")
RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

_balance_cache = {}
CACHE_TTL = 30

def get_wallet_token_balances(wallet_address: str) -> Dict[str, float]:
    """
    Fetches real SPL token balances for the provided wallet address via Solana RPC.
    Returns a dictionary mapping tickers (e.g., 'USDC', 'NVDA') to their token amounts (float).
    Caches results for 30 seconds to conserve Helius RPC credits.
    """
    now = time.time()
    if wallet_address in _balance_cache:
        cached_data, timestamp = _balance_cache[wallet_address]
        if now - timestamp < CACHE_TTL:
            return cached_data

    results = {}
    
    # Map mint address -> ticker symbol for quick lookup
    mint_to_ticker = {USDC["mint"]: "USDC"}
    mint_to_decimals = {USDC["mint"]: USDC["decimals"]}
    for ticker, info in STOCKS.items():
        mint_to_ticker[info["mint"]] = ticker
        mint_to_decimals[info["mint"]] = info["decimals"]

    payloads = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet_address,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"}
            ]
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet_address,
                {"programId": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"},
                {"encoding": "jsonParsed"}
            ]
        }
    ]

    try:
        req = urllib.request.Request(
            RPC_URL,
            data=json.dumps(payloads).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            responses = json.loads(response.read().decode("utf-8"))
            
            for data in responses:
                if "result" in data and "value" in data["result"]:
                    accounts = data["result"]["value"]
                    for account in accounts:
                        account_data = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                        mint = account_data.get("mint")
                        
                        if mint in mint_to_ticker:
                            ticker = mint_to_ticker[mint]
                            amount = account_data.get("tokenAmount", {}).get("uiAmount", 0.0)
                            
                            if amount:
                                results[ticker] = results.get(ticker, 0.0) + amount
                            
    except Exception as e:
        print(f"Error fetching RPC balances for {wallet_address}: {e}")
        
    _balance_cache[wallet_address] = (results, time.time())
    return results

def get_recent_onchain_signatures(wallet_address: str, limit: int = 5):
    """Fetches recent finalized transaction signatures for this wallet via Solana RPC."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [wallet_address, {"limit": limit}]
    }
    try:
        req = urllib.request.Request(
            RPC_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
            if "result" in data:
                return [s for s in data["result"] if not s.get("err")]
    except Exception as e:
        print(f"Error fetching onchain signatures for {wallet_address}: {e}")
    return []

