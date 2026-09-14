# Sentiment-Powered Solana xStock Rebalance Bot

AI-driven sentiment-powered automated portfolio rebalancing on **Solana** for synthetic and tokenized stocks (**xStocks**).

Built for the **Solana Hackathon** (Consumer & Investing Tracks).

---

## 🏛️ System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    YOUR VPS (FastAPI Backend)                    │
│                                                                  │
│  ┌──────────────────┐    ┌─────────────────┐   ┌──────────────┐  │
│  │ Sentiment Engine │───▶│    Rebalance    │──▶│   Jupiter    │  │
│  │  (VADER + News)  │    │ Decision Engine │   │ Swap Router  │  │
│  └──────────────────┘    └─────────────────┘   └──────────────┘  │
│          ▲                        ▲                   │          │
│   ┌──────┴──────┐          ┌──────┴──────┐            │          │
│   │ Google News │          │ Pyth Price  │     Solana Tx         │
│   │ RSS Feeds   │          │ Feeds (SPL) │            │          │
│   └─────────────┘          └─────────────┘            ▼          │
│                                                   Solana DEX     │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                   Web Trading Terminal                     │  │
│  │  Base: / → Live allocations, Sentiment scores, Pyth prices │  │
│  │  API:  /api/portfolio /api/scores /api/rebalance /api/quote│  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Live Data & Execution Flow

1. **Sentiment Ingestion**: Scrapes Google News RSS for stock basket symbols (`TSLA`, `AAPL`, `NVDA`, `MSFT`, `GOOGL`), parses polarity via VADER, and extracts 8 emotional dimensions (fear, joy, anger, trust, etc.).
2. **Oracle Valuation**: Ingests real-time price feeds via Pyth Price Feeds / Market Feeds to compute live portfolio values in `USDC`.
3. **Rebalancing Decision**:
   - Softmax multi-factor weighting based on compound sentiment:
     - Negative sentiment ($< -0.10$) immediately unloads equity exposure into **USDC** safe reserve.
     - Positive sentiment overweights winning momentum equities.
   - If deviation $> 3\%$, formulates sequential optimal swap route.
4. **Execution on Jupiter DEX**:
   - Direct integration with Jupiter Swap v1 API (`https://api.jup.ag/swap/v1`).
   - Builds transaction, calculates slippage, routes swaps, and outputs confirmed Solscan tx signatures.

---

## 🧪 Hackathon Judge Demo Script

1. **Open Dashboard**: View live initial balanced portfolio with TSLA, AAPL, NVDA, MSFT, and USDC.
2. **Simulate Event**: Click `"🔴 TSLA Recall (-55% Drop)"` in the Hackathon Demo Controls.
3. **Live Signal Reaction**: Observe TSLA sentiment score plummet into negative territory and Target Allocation drop to 0% with capital shifting into USDC.
4. **Execute Rebalance**: Click `"⚡ Execute Jupiter Rebalance"`.
5. **On-Chain Confirmation**: Watch Jupiter route orders, sell TSLA into USDC, and display the Solscan transaction signature.

---

## 🚀 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/portfolio` | `GET` | Current holdings, Pyth values, current & target weights |
| `/api/scores` | `GET` | Live sentiment signals & emotional profile across stock basket |
| `/api/prices` | `GET` | Real-time prices for TSLA, AAPL, NVDA, MSFT, GOOGL, USDC |
| `/api/rebalance` | `POST` | Executes automated portfolio rebalancing via Jupiter |
| `/api/simulate-news` | `POST` | Injects breaking news scenario for judge demonstrations |
| `/api/reset-news` | `POST` | Resets to organic live Google News RSS signals |
| `/api/quote` | `GET` | Live Jupiter DEX swap routing and price impact |

---

## 🛠️ Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
python main.py

# Frontend
open frontend/index.html
```

---

## 📜 License
MIT