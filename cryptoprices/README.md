# CryptoPrices Cog

A cryptocurrency price lookup, charting, and market sentiment cog for [Red-DiscordBot](https://github.com/Cog-Creators/Red-DiscordBot).

Powered by the public [CoinGecko API](https://www.coingecko.com/en/api) and [Alternative.me Fear and Greed Index](https://alternative.me/crypto/fear-and-greed-index/).

---

## Features

- **Price Lookup (`[p]crypto` & `[p]coin`):** Fetch live cryptocurrency prices formatted in a clean Discord embed or plain text. Supports fiat conversions (`usd`, `eur`, `gbp`, `jpy`, etc.).
- **Interactive Price Charts (`[p]cryptoinfo`):** Generate historical price trend charts for timeframes from 1 to 365 days, rendered via headless Matplotlib.
- **Crypto Fear & Greed Index (`[p]feargreed`):** View today's crypto market sentiment score or chart historical sentiment over time.
- **In-Memory Caching:** Automatically caches prices, chart data, and index results to avoid hitting public API rate limits. Cache duration is configurable by the bot owner.
- **Ticker & Name Resolution:** Preloaded map of 100+ popular cryptocurrencies, tokens, and aliases plus dynamic fallback search via CoinGecko's search endpoint. Look up coins by ticker (`imx`, `stx`, `btc`, `sol`, `fet`, `rndr`, `tia`, etc.) or full coin names without needing to know CoinGecko's internal IDs.

---

## Installation

Add the repository (if not added yet):
```ini
[p]repo add gnet-cogs https://github.com/zigagrcar/gnet-cogs
```

Install the cog:
```ini
[p]cog install gnet-cogs cryptoprices
```

Load the cog:
```ini
[p]load cryptoprices
```

---

## Commands

### User Commands

| Command | Description | Example |
| :--- | :--- | :--- |
| `[p]crypto <coin> [currency]` | Get current price formatted in a rich embed. | `[p]crypto btc`<br>`[p]crypto ethereum eur` |
| `[p]coin <coin> [currency]` | Get raw price in plain text (useful for quick references). | `[p]coin sol`<br>`[p]coin btc usd` |
| `[p]cryptoinfo <coin> [days] [currency]` | Generate a historical price chart (1–365 days). | `[p]cryptoinfo btc`<br>`[p]cryptoinfo eth 30 eur` |
| `[p]feargreed [days]` | View Fear & Greed index (1 = current score, >1 = trend chart). | `[p]feargreed`<br>`[p]feargreed 30` |

### Owner Commands

| Command | Description |
| :--- | :--- |
| `[p]cryptocache` | Clear the in-memory cache for prices, charts, and fear/greed data. |
| `[p]cryptocachetime <minutes>` | Configure how many minutes API responses stay cached before refetching (default: 5). |

---

## Requirements

- Zero external pip requirements (pure Python, discord.py, and aiohttp)
- Red-DiscordBot >= 3.5.0
- Python >= 3.9
