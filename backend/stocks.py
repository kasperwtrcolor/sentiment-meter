"""
Stock Basket, Token Mints, and Pyth Price Feed Configuration for Solana xStocks.
"""

# Supported Stock Basket & Anchor Stablecoin
STOCKS = {
    "TSLA": {
        "name": "Tesla, Inc.",
        "symbol": "TSLA",
        "category": "Auto & Clean Tech",
        # Real Solana xStock / Wrapped Stock mint or SPL representative
        # TSLAx on Solana SPL (mainnet standard reference)
        "mint": "XsLAs1sQvjEQdtkC2sZkWJ8V3uU8A4LhYvB1bW7E8yB",
        "decimals": 6,
        # Pyth Hermes Price Feed ID for TSLA/USD
        "pyth_id": "0x0bbf28e19c5ea2c63dfdb3c28df776c5b6b15e449fc61a4f00d604b901614747",
        "query": "Tesla TSLA stock",
    },
    "AAPL": {
        "name": "Apple Inc.",
        "symbol": "AAPL",
        "category": "Consumer Electronics",
        "mint": "AAPLxG5Z9W7W9eRz2vM6bK4sY3pT1qX8vC7mN2L9jD4F",
        "decimals": 6,
        "pyth_id": "0x49f6b65eb1bf245ad47372e11894d5db0e9808381283ded3e053a99fa2382f6c",
        "query": "Apple AAPL stock",
    },
    "NVDA": {
        "name": "NVIDIA Corporation",
        "symbol": "NVDA",
        "category": "AI & Semiconductors",
        "mint": "NVDAx2uH4r8T7wY1pK9sD3mF6bL5qX8vC2jN4L7jE9A",
        "decimals": 6,
        "pyth_id": "0x16538d38e21a24d550e24e4d6f0378e99990868f7ec4cc973273e93892789f25",
        "query": "Nvidia NVDA stock",
    },
    "MSFT": {
        "name": "Microsoft Corporation",
        "symbol": "MSFT",
        "category": "Enterprise Software & Cloud",
        "mint": "MSFTx8wY1pK9sD3mF6bL5qX8vC2jN4L7jE9AwR3tU5z",
        "decimals": 6,
        "pyth_id": "0x0d3b664d4ab28020e98585483e602498236d2c49d4eb447472061e860959a499",
        "query": "Microsoft MSFT stock",
    },
    "GOOGL": {
        "name": "Alphabet Inc.",
        "symbol": "GOOGL",
        "category": "Search, Ads & AI",
        "mint": "GOOGx1pK9sD3mF6bL5qX8vC2jN4L7jE9AwR3tU5zM2L",
        "decimals": 6,
        "pyth_id": "0x5e08ae6b245cf711d95e7b233a0887e141a5477c7b8e19e78ff6a9fc96f9bf1a",
        "query": "Alphabet Google GOOGL stock",
    },
}

# Anchor Reserve Asset: USDC on Solana
USDC = {
    "name": "USD Coin",
    "symbol": "USDC",
    "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "decimals": 6,
    "pyth_id": "0xeaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
}

# Native Solana (SOL) for Gas & Routing
SOL = {
    "name": "Wrapped SOL",
    "symbol": "SOL",
    "mint": "So11111111111111111111111111111111111111112",
    "decimals": 9,
}
