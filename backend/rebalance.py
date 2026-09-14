"""
Portfolio State and Sentiment-Driven Rebalance Engine with Per-Wallet Holdings Tracking.
Supports bi-directional swaps: USDC <-> xStocks with real-time balance calculations.
"""
import time
import math
from typing import Dict, Any, List
from stocks import STOCKS, USDC
from price_service import fetch_live_stock_prices, get_price
from jupiter_service import execute_swap, DEFAULT_WALLET_PUBKEY

# In-memory per-wallet position tracking (synced from on-chain balances or starting balances)
WALLET_PORTFOLIOS: Dict[str, Dict[str, Any]] = {}

def get_default_positions():
    return {
        "NVDA": {"shares": 14.27, "usd_value": 3000.00, "current_weight": 0.30},
        "TSLA": {"shares": 6.99, "usd_value": 2500.00, "current_weight": 0.25},
        "AAPL": {"shares": 7.51, "usd_value": 2500.00, "current_weight": 0.25},
        "MSFT": {"shares": 2.00, "usd_value": 1000.00, "current_weight": 0.10},
        "GOOGL": {"shares": 0.00, "usd_value": 0.00, "current_weight": 0.00},
        "USDC": {"shares": 2500.00, "usd_value": 2500.00, "current_weight": 0.10},
    }

def get_current_portfolio(wallet_address: str = None) -> Dict[str, Any]:
    """
    Returns live valued portfolio for the connected wallet, recalculating weights at each refresh.
    """
    wallet = wallet_address or DEFAULT_WALLET_PUBKEY
    
    if wallet not in WALLET_PORTFOLIOS:
        WALLET_PORTFOLIOS[wallet] = {
            "wallet_address": wallet,
            "last_rebalance_ts": int(time.time() - 3600),
            "total_value_usd": 11500.00,
            "positions": get_default_positions(),
            "history": []
        }

    port = WALLET_PORTFOLIOS[wallet]
    prices = fetch_live_stock_prices()
    total_val = 0.0

    for sym, pos in port["positions"].items():
        price = prices.get(sym, {}).get("price_usd", 1.0)
        pos["usd_value"] = round(pos["shares"] * price, 2)
        total_val += pos["usd_value"]

    port["total_value_usd"] = round(total_val, 2)

    for sym, pos in port["positions"].items():
        pos["current_weight"] = round(pos["usd_value"] / total_val, 4) if total_val > 0 else 0.0
        pos["price_usd"] = prices.get(sym, {}).get("price_usd", 1.0)
        pos["change_24h_pct"] = prices.get(sym, {}).get("change_24h_pct", 0.0)
        pos["mint"] = STOCKS.get(sym, {}).get("mint", USDC["mint"])
        pos["logo"] = STOCKS.get(sym, {}).get("logo", USDC["logo"])
        pos["name"] = STOCKS.get(sym, {}).get("name", USDC["name"])
        pos["accent"] = STOCKS.get(sym, {}).get("accent", "#6366f1")

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

def execute_direct_stock_swap(wallet_address: str, ticker: str, direction: str, amount_usd: float) -> Dict[str, Any]:
    """
    Executes a direct swap between USDC and a selected stock (BUY or SELL) for the user's wallet.
    - direction: 'BUY' (USDC -> Stock) or 'SELL' (Stock -> USDC)
    """
    port = get_current_portfolio(wallet_address)
    prices = fetch_live_stock_prices()
    
    ticker = ticker.upper()
    if ticker not in STOCKS:
        return {"success": False, "error": f"Invalid stock ticker: {ticker}"}

    stock_price = prices.get(ticker, {}).get("price_usd", 100.0)
    usdc_balance = port["positions"]["USDC"]["usd_value"]
    stock_balance = port["positions"][ticker]["usd_value"]

    if direction == "BUY":
        if amount_usd > usdc_balance:
            return {"success": False, "error": f"Insufficient USDC balance. Have ${usdc_balance:.2f}, requested ${amount_usd:.2f}"}
        
        # Execute Jupiter swap USDC -> Stock
        swap_res = execute_swap(
            from_symbol="USDC",
            to_symbol=ticker,
            from_mint=USDC["mint"],
            to_mint=STOCKS[ticker]["mint"],
            amount_usd=amount_usd,
            unit_price_from=1.0,
            unit_price_to=stock_price
        )

        shares_bought = amount_usd / stock_price
        port["positions"]["USDC"]["shares"] = max(0.0, port["positions"]["USDC"]["shares"] - amount_usd)
        port["positions"][ticker]["shares"] += shares_bought
        port["history"].insert(0, swap_res)
        get_current_portfolio(wallet_address)
        return {"success": True, "swap": swap_res, "portfolio": port}

    elif direction == "SELL":
        if amount_usd > stock_balance:
            return {"success": False, "error": f"Insufficient ${ticker} balance. Have ${stock_balance:.2f}, requested ${amount_usd:.2f}"}

        # Execute Jupiter swap Stock -> USDC
        swap_res = execute_swap(
            from_symbol=ticker,
            to_symbol="USDC",
            from_mint=STOCKS[ticker]["mint"],
            to_mint=USDC["mint"],
            amount_usd=amount_usd,
            unit_price_from=stock_price,
            unit_price_to=1.0
        )

        shares_sold = amount_usd / stock_price
        port["positions"][ticker]["shares"] = max(0.0, port["positions"][ticker]["shares"] - shares_sold)
        port["positions"]["USDC"]["shares"] += amount_usd
        port["history"].insert(0, swap_res)
        get_current_portfolio(wallet_address)
        return {"success": True, "swap": swap_res, "portfolio": port}

    return {"success": False, "error": "Invalid direction. Must be BUY or SELL"}

def run_rebalance(sentiment_scores: Dict[str, float], wallet_address: str = None, threshold: float = 0.03) -> Dict[str, Any]:
    """
    Executes full multi-asset rebalancing cycle for the specified wallet.
    """
    portfolio = get_current_portfolio(wallet_address)
    target_weights = compute_target_allocation(sentiment_scores)
    total_val = portfolio["total_value_usd"]
    prices = fetch_live_stock_prices()

    trades_needed = []
    
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

    executed_swaps = []

    for trade in [t for t in trades_needed if t["action"] == "SELL"]:
        sym = trade["symbol"]
        amt_usd = trade["amount_usd"]
        p_from = prices.get(sym, {}).get("price_usd", 100.0)
        
        swap_res = execute_swap(
            from_symbol=sym,
            to_symbol="USDC",
            from_mint=STOCKS[sym]["mint"],
            to_mint=USDC["mint"],
            amount_usd=amt_usd,
            unit_price_from=p_from,
            unit_price_to=1.0
        )
        
        shares_sold = amt_usd / p_from
        portfolio["positions"][sym]["shares"] = max(0.0, portfolio["positions"][sym]["shares"] - shares_sold)
        portfolio["positions"]["USDC"]["shares"] += amt_usd
        executed_swaps.append(swap_res)
        portfolio["history"].insert(0, swap_res)

    for trade in [t for t in trades_needed if t["action"] == "BUY"]:
        sym = trade["symbol"]
        amt_usd = trade["amount_usd"]
        p_to = prices.get(sym, {}).get("price_usd", 100.0)

        swap_res = execute_swap(
            from_symbol="USDC",
            to_symbol=sym,
            from_mint=USDC["mint"],
            to_mint=STOCKS[sym]["mint"],
            amount_usd=amt_usd,
            unit_price_from=1.0,
            unit_price_to=p_to
        )

        shares_bought = amt_usd / p_to
        portfolio["positions"]["USDC"]["shares"] = max(0.0, portfolio["positions"]["USDC"]["shares"] - amt_usd)
        portfolio["positions"][sym]["shares"] += shares_bought
        executed_swaps.append(swap_res)
        portfolio["history"].insert(0, swap_res)

    portfolio["last_rebalance_ts"] = int(time.time())
    get_current_portfolio(wallet_address)

    return {
        "success": True,
        "swaps_executed": len(executed_swaps),
        "target_weights": target_weights,
        "swaps": executed_swaps,
        "portfolio": portfolio
    }
