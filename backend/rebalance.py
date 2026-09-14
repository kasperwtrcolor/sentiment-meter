"""
Portfolio State and Sentiment-Driven Rebalance Engine with Real On-Chain Holdings Tracking.
Calculates targets and needed swaps based on actual Solana wallet balances.
"""
import time
import math
from typing import Dict, Any, List
from stocks import STOCKS, USDC
from price_service import fetch_live_stock_prices, get_price
from solana_rpc import get_wallet_token_balances

# Fallback pubkey if none provided
DEFAULT_WALLET_PUBKEY = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"

def get_current_portfolio(wallet_address: str = None) -> Dict[str, Any]:
    """
    Returns live valued portfolio for the connected wallet, reading real on-chain SPL balances.
    """
    wallet = wallet_address or DEFAULT_WALLET_PUBKEY
    
    # Read real on-chain balances (dict of TICKER -> float amount)
    real_balances = get_wallet_token_balances(wallet)
    
    port = {
        "wallet_address": wallet,
        "last_rebalance_ts": int(time.time()),
        "total_value_usd": 0.0,
        "positions": {},
        "history": [] # History comes from DB now
    }
    
    prices = fetch_live_stock_prices()
    total_val = 0.0

    # Initialize all supported assets
    for sym in list(STOCKS.keys()) + ["USDC"]:
        info = STOCKS.get(sym, USDC)
        shares = real_balances.get(sym, 0.0)
        price = prices.get(sym, {}).get("price_usd", 1.0)
        usd_val = round(shares * price, 2)
        total_val += usd_val
        
        port["positions"][sym] = {
            "shares": shares,
            "usd_value": usd_val,
            "current_weight": 0.0,
            "price_usd": price,
            "change_24h_pct": prices.get(sym, {}).get("change_24h_pct", 0.0),
            "mint": info["mint"],
            "logo": info.get("logo"),
            "name": info.get("name"),
            "accent": info.get("accent", "#6366f1")
        }

    port["total_value_usd"] = round(total_val, 2)

    # Calculate actual weights
    if total_val > 0:
        for sym, pos in port["positions"].items():
            pos["current_weight"] = round(pos["usd_value"] / total_val, 4)

    return port

def compute_target_allocation(sentiment_scores: Dict[str, float]) -> Dict[str, float]:
    tickers = list(STOCKS.keys())
    target_weights: Dict[str, float] = {}
    
    usdc_reserve = 0.05
    active_stocks = []
    
    for t in tickers:
        score = sentiment_scores.get(t, 0.0)
        if score < -0.10:
            target_weights[t] = 0.0
            usdc_reserve += 0.15
        else:
            active_stocks.append(t)

    if active_stocks:
        tau = 0.5
        exp_scores = {t: math.exp(sentiment_scores.get(t, 0.0) / tau) for t in active_stocks}
        total_exp = sum(exp_scores.values())
        
        remaining_weight = 1.0 - min(usdc_reserve, 0.60)
        for t in active_stocks:
            target_weights[t] = round((exp_scores[t] / total_exp) * remaining_weight, 3)

    target_weights["USDC"] = round(1.0 - sum(target_weights.values()), 3)
    return target_weights

def run_rebalance(sentiment_scores: Dict[str, float], wallet_address: str = None, threshold: float = 0.03) -> Dict[str, Any]:
    """
    Calculates needed trades for rebalancing cycle for the specified wallet.
    Does not execute swaps (swaps are client-side signed via Jupiter).
    """
    portfolio = get_current_portfolio(wallet_address)
    target_weights = compute_target_allocation(sentiment_scores)
    total_val = portfolio["total_value_usd"]

    trades_needed = []
    
    if total_val == 0:
        return {"success": True, "trades_needed": [], "target_weights": target_weights, "portfolio": portfolio}
    
    for sym, current_pos in portfolio["positions"].items():
        curr_w = current_pos["current_weight"]
        tgt_w = target_weights.get(sym, 0.0)
        delta_w = tgt_w - curr_w

        if delta_w < -threshold and sym != "USDC":
            amount_to_sell_usd = abs(delta_w) * total_val
            trades_needed.append({
                "action": "SELL",
                "symbol": sym,
                "amount_usd": round(amount_to_sell_usd, 2),
                "delta_weight": round(delta_w, 3)
            })

    for sym, current_pos in portfolio["positions"].items():
        curr_w = current_pos["current_weight"]
        tgt_w = target_weights.get(sym, 0.0)
        delta_w = tgt_w - curr_w

        if delta_w > threshold and sym != "USDC":
            amount_to_buy_usd = delta_w * total_val
            trades_needed.append({
                "action": "BUY",
                "symbol": sym,
                "amount_usd": round(amount_to_buy_usd, 2),
                "delta_weight": round(delta_w, 3)
            })

    return {
        "success": True,
        "trades_needed": trades_needed,
        "target_weights": target_weights,
        "portfolio": portfolio
    }
