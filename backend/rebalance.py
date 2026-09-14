"""
Portfolio State and Sentiment-Driven Rebalance Engine.
Calculates target weights from multi-factor sentiment scores, computes deviation,
and executes necessary rebalance orders via Jupiter.
"""
import time
import math
from typing import Dict, Any, List
from stocks import STOCKS, USDC
from price_service import fetch_live_stock_prices, get_price
from jupiter_service import execute_swap, DEFAULT_WALLET_PUBKEY

# Starting demo portfolio: $10,000 total allocated across stock basket & USDC
# 30% TSLA, 25% AAPL, 25% NVDA, 10% MSFT, 10% USDC
PORTFOLIO_STATE = {
    "wallet_address": DEFAULT_WALLET_PUBKEY,
    "last_rebalance_ts": int(time.time() - 3600),
    "total_value_usd": 10000.00,
    "positions": {
        "TSLA": {"shares": 8.39, "usd_value": 3000.00, "current_weight": 0.30},
        "AAPL": {"shares": 7.51, "usd_value": 2500.00, "current_weight": 0.25},
        "NVDA": {"shares": 11.89, "usd_value": 2500.00, "current_weight": 0.25},
        "MSFT": {"shares": 2.00, "usd_value": 1000.00, "current_weight": 0.10},
        "GOOGL": {"shares": 0.00, "usd_value": 0.00, "current_weight": 0.00},
        "USDC": {"shares": 1000.00, "usd_value": 1000.00, "current_weight": 0.10},
    },
    "history": [
        {
            "tx_hash": "5JtWp7xLq2vN8kR3yF6bM1sD4hG9aC8vT2pQ5uX7mN9kL4jD2fG8hJ3kL5mN7pQ9rS1tU3vW5xY7zB2cE4gH6jK8",
            "solscan_url": "https://solscan.io/tx/5JtWp7xLq2vN8kR3yF6bM1sD4hG9aC8vT2pQ5uX7mN9kL4jD2fG8hJ3kL5mN7pQ9rS1tU3vW5xY7zB2cE4gH6jK8",
            "from_symbol": "USDC",
            "to_symbol": "TSLA",
            "amount_usd": 500.00,
            "status": "CONFIRMED",
            "timestamp": int(time.time() - 3600),
            "reason": "Initial basket balancing"
        }
    ]
}

def get_current_portfolio() -> Dict[str, Any]:
    """
    Returns live valued portfolio with actual current prices and real weights.
    """
    prices = fetch_live_stock_prices()
    total_val = 0.0

    # Recalculate each position based on current price
    for sym, pos in PORTFOLIO_STATE["positions"].items():
        price = prices.get(sym, {}).get("price_usd", 1.0)
        pos["usd_value"] = round(pos["shares"] * price, 2)
        total_val += pos["usd_value"]

    PORTFOLIO_STATE["total_value_usd"] = round(total_val, 2)

    # Compute current weights
    for sym, pos in PORTFOLIO_STATE["positions"].items():
        pos["current_weight"] = round(pos["usd_value"] / total_val, 4) if total_val > 0 else 0.0
        pos["price_usd"] = prices.get(sym, {}).get("price_usd", 1.0)
        pos["mint"] = STOCKS.get(sym, {}).get("mint", USDC["mint"])

    return PORTFOLIO_STATE

def compute_target_allocation(sentiment_scores: Dict[str, float]) -> Dict[str, float]:
    """
    Multi-factor allocation formula:
    - High positive sentiment (> 0.2) -> Overweight
    - Neutral sentiment (-0.05 to 0.2) -> Base weight
    - Severe negative sentiment (<= -0.05) -> Underweight / Rotate to USDC
    """
    tickers = list(STOCKS.keys())
    target_weights: Dict[str, float] = {}
    
    # Check for severely negative stocks and shift their portion into USDC safety pool
    usdc_reserve = 0.05  # minimum 5% cash anchor
    active_stocks = []
    
    for t in tickers:
        score = sentiment_scores.get(t, 0.0)
        if score < -0.10:
            # Negative news -> drop allocation to zero and park in USDC
            target_weights[t] = 0.0
            usdc_reserve += 0.15
        else:
            active_stocks.append(t)

    # Softmax / exponential weighting over active stocks based on sentiment compound score
    if active_stocks:
        tau = 0.5  # temperature parameter
        exp_scores = {t: math.exp(sentiment_scores.get(t, 0.0) / tau) for t in active_stocks}
        total_exp = sum(exp_scores.values())
        
        remaining_weight = 1.0 - min(usdc_reserve, 0.60)
        for t in active_stocks:
            target_weights[t] = round((exp_scores[t] / total_exp) * remaining_weight, 3)

    target_weights["USDC"] = round(1.0 - sum(target_weights.values()), 3)
    return target_weights

def run_rebalance(sentiment_scores: Dict[str, float], threshold: float = 0.03) -> Dict[str, Any]:
    """
    Executes full rebalance algorithm:
    1. Computes target weights
    2. Identifies deviations exceeding threshold
    3. Issues Jupiter DEX swaps
    4. Updates portfolio holdings
    """
    portfolio = get_current_portfolio()
    target_weights = compute_target_allocation(sentiment_scores)
    total_val = portfolio["total_value_usd"]
    prices = fetch_live_stock_prices()

    trades_needed = []
    
    # 1. Determine sells first to generate USDC liquidity
    for sym, current_pos in portfolio["positions"].items():
        curr_w = current_pos["current_weight"]
        tgt_w = target_weights.get(sym, 0.0)
        delta_w = tgt_w - curr_w

        # If overweight by more than threshold, sell excess into USDC
        if delta_w < -threshold and sym != "USDC":
            amount_to_sell_usd = abs(delta_w) * total_val
            trades_needed.append({
                "action": "SELL",
                "symbol": sym,
                "amount_usd": round(amount_to_sell_usd, 2),
                "delta_weight": round(delta_w, 3)
            })

    # 2. Determine buys funded by USDC
    for sym, current_pos in portfolio["positions"].items():
        curr_w = current_pos["current_weight"]
        tgt_w = target_weights.get(sym, 0.0)
        delta_w = tgt_w - curr_w

        # If underweight by more than threshold, buy using USDC
        if delta_w > threshold and sym != "USDC":
            amount_to_buy_usd = delta_w * total_val
            trades_needed.append({
                "action": "BUY",
                "symbol": sym,
                "amount_usd": round(amount_to_buy_usd, 2),
                "delta_weight": round(delta_w, 3)
            })

    executed_swaps = []

    # 3. Execute Sell trades (Asset -> USDC)
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
        
        # Update positions
        shares_sold = amt_usd / p_from
        portfolio["positions"][sym]["shares"] = max(0.0, portfolio["positions"][sym]["shares"] - shares_sold)
        portfolio["positions"]["USDC"]["shares"] += amt_usd
        executed_swaps.append(swap_res)
        portfolio["history"].insert(0, swap_res)

    # 4. Execute Buy trades (USDC -> Asset)
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

        # Update positions
        shares_bought = amt_usd / p_to
        portfolio["positions"]["USDC"]["shares"] = max(0.0, portfolio["positions"]["USDC"]["shares"] - amt_usd)
        portfolio["positions"][sym]["shares"] += shares_bought
        executed_swaps.append(swap_res)
        portfolio["history"].insert(0, swap_res)

    portfolio["last_rebalance_ts"] = int(time.time())
    get_current_portfolio()  # refresh weights

    return {
        "success": True,
        "swaps_executed": len(executed_swaps),
        "target_weights": target_weights,
        "swaps": executed_swaps,
        "portfolio": portfolio
    }
