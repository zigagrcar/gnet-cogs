# gnet-cogs

[![Red-DiscordBot](https://img.shields.io/badge/Red--DiscordBot-V3-red.svg)](https://github.com/Cog-Creators/Red-DiscordBot)
[![discord.py](https://img.shields.io/badge/discord.py-rewrite-blue.svg)](https://github.com/Rapptz/discord.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A collection of cogs for [Red-DiscordBot](https://github.com/Cog-Creators/Red-DiscordBot) by [zigagrcar](https://github.com/zigagrcar).

---

## Installation

To add this repository to your Red-DiscordBot instance:

```ini
[p]repo add gnet-cogs https://github.com/zigagrcar/gnet-cogs
```

To install a specific cog:

```ini
[p]cog install gnet-cogs <cog_name>
```

To load the installed cog:

```ini
[p]load <cog_name>
```

> **Note:** Replace `[p]` with your bot's prefix.

---

## Available Cogs

| Cog | Description | Status |
| :--- | :--- | :--- |
| [`cryptoprices`](cryptoprices/) | Real-time cryptocurrency prices, price charts, and Crypto Fear & Greed Index powered by CoinGecko and Alternative.me. | Working |

---

## Cog Overview

### `cryptoprices`

Look up live cryptocurrency prices, plot price trend charts across multiple timeframes, and inspect the Crypto Fear & Greed Index with automatic in-memory caching to prevent API rate limits.

**Main Commands:**
- `[p]crypto <coin> [currency]` — Look up current price formatted in a rich embed.
- `[p]coin <coin> [currency]` — Quick plain-text price lookup.
- `[p]cryptoinfo <coin> [days] [currency]` — Render a historical price line chart (1–365 days).
- `[p]feargreed [days]` — Display the Crypto Fear & Greed Index (with trend chart for multi-day views).

See the [`cryptoprices` README](cryptoprices/README.md) for full documentation and configuration options.

---

## Contributing & Issues

If you encounter any bugs, rate limit issues, or have feature suggestions:
- Open an issue on the [GitHub Issues](https://github.com/zigagrcar/gnet-cogs/issues) page.
- Pull requests are always welcome!

---

## Author

- **zigagrcar** ([GitHub](https://github.com/zigagrcar))

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
