import asyncio
import io
import logging
import time
from typing import Optional

import aiohttp
import discord
from redbot.core import commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.gnet-cogs.cryptoprices")

COINGECKO_API = "https://api.coingecko.com/api/v3"
ALTERNATIVE_ME_API = "https://api.alternative.me/fng/"
QUICKCHART_API = "https://quickchart.io/chart"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=8, connect=4, sock_read=6)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


class CryptoAPIError(Exception):
    """Base exception for API errors."""

    def __init__(self, message: str, is_ratelimit: bool = False):
        super().__init__(message)
        self.message = message
        self.is_ratelimit = is_ratelimit


class RateLimitError(CryptoAPIError):
    """Raised when an API is throttling requests (HTTP 429)."""

    def __init__(self, service: str = "CoinGecko"):
        super().__init__(
            f"**{service}** is currently throttling requests (rate limited). Please wait a few moments and try again.",
            is_ratelimit=True,
        )


class APIDownError(CryptoAPIError):
    """Raised when an API is down, slow, or returning server errors."""

    def __init__(self, service: str = "CoinGecko", reason: str = "service unavailable"):
        super().__init__(
            f"**{service}** API is currently unreachable ({reason}). Please try again later."
        )


class CryptoPrices(commands.Cog):
    """Look up cryptocurrency prices and charts from the public CoinGecko API.

    Prices and chart data are cached in memory for a configurable number of
    minutes to avoid hitting CoinGecko's rate limits.

    Commands: `[p]crypto` (price embed), `[p]coin` (price only, plain text),
    `[p]cryptoinfo` (price chart), `[p]feargreed` (Fear & Greed Index).
    """

    __author__ = "zigagrcar"
    __version__ = "1.0.0"
    __red_end_user_data_statement__ = (
        "This cog does not persistently store data about users."
    )

    def __init__(self, bot: Red):
        self.bot = bot
        self.session = aiohttp.ClientSession(headers={"User-Agent": USER_AGENT})

        self.config = Config.get_conf(self, identifier=8675309001, force_registration=True)
        self.config.register_global(cache_minutes=5)

        # In-memory cache: {(coin_id, currency): (price, fetched_at_timestamp)}
        self._cache: dict[tuple[str, str], tuple[float, float]] = {}

        # In-memory cache for chart data: {(coin_id, currency, days): (data, fetched_at)}
        self._chart_cache: dict[tuple[str, str, int], tuple[list, float]] = {}

        # In-memory cache for the fear & greed index: {limit: (data, fetched_at)}
        self._fng_cache: dict[int, tuple[list, float]] = {}

        # In-memory cache for dynamically searched tickers -> CoinGecko IDs
        self._dynamic_alias_cache: dict[str, str] = {}

        # Preloaded map of popular tickers to CoinGecko IDs for instant resolution
        self._alias_map = {
            "btc": "bitcoin",
            "eth": "ethereum",
            "sol": "solana",
            "stx": "blockstack",
            "imx": "immutable-x",
            "xrp": "ripple",
            "ada": "cardano",
            "doge": "dogecoin",
            "bnb": "binancecoin",
            "dot": "polkadot",
            "matic": "matic-network",
            "pol": "polygon-ecosystem-token",
            "link": "chainlink",
            "avax": "avalanche-2",
            "shib": "shiba-inu",
            "trx": "tron",
            "near": "near",
            "atom": "cosmos",
            "arb": "arbitrum",
            "op": "optimism",
            "sui": "sui",
            "apt": "aptos",
            "ton": "the-open-network",
            "kas": "kaspa",
            "fet": "artificial-superintelligence-alliance",
            "rndr": "render-token",
            "render": "render-token",
            "pepe": "pepe",
            "wif": "dogwifcoin",
            "tao": "bittensor",
            "uni": "uniswap",
            "ltc": "litecoin",
            "bch": "bitcoin-cash",
            "xlm": "stellar",
            "etc": "ethereum-classic",
            "xmr": "monero",
            "fil": "filecoin",
            "vet": "vechain",
            "inj": "injective-protocol",
            "tia": "celestia",
            "sei": "sei-network",
            "rune": "thorchain",
            "algo": "algorand",
            "icp": "internet-computer",
            "aave": "aave",
            "mkr": "maker",
            "cro": "crypto-com-chain",
            "usdt": "tether",
            "usdc": "usd-coin",
            "dai": "dai",
        }

    async def cog_unload(self):
        await self.session.close()

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        """Nothing to delete — this cog does not store user data."""
        return

    async def _resolve_id(self, coin: str) -> str:
        """Resolve a user-provided ticker/name to CoinGecko's internal API ID.
        Checks hardcoded common aliases first, then dynamic memory cache,
        and finally searches CoinGecko's search endpoint.
        """
        coin_clean = coin.lower().strip()
        if coin_clean in self._alias_map:
            return self._alias_map[coin_clean]

        if coin_clean in self._dynamic_alias_cache:
            return self._dynamic_alias_cache[coin_clean]

        try:
            params = {"query": coin_clean}
            async with self.session.get(
                f"{COINGECKO_API}/search", params=params, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    coins = data.get("coins", [])
                    if coins:
                        # 1. Exact symbol match with highest market cap rank (lowest rank number)
                        symbol_matches = [
                            c for c in coins if c.get("symbol", "").lower() == coin_clean
                        ]
                        if symbol_matches:
                            symbol_matches.sort(
                                key=lambda x: x.get("market_cap_rank") or 999999
                            )
                            best_id = symbol_matches[0]["id"]
                            self._dynamic_alias_cache[coin_clean] = best_id
                            return best_id

                        # 2. Exact ID match
                        id_matches = [
                            c for c in coins if c.get("id", "").lower() == coin_clean
                        ]
                        if id_matches:
                            best_id = id_matches[0]["id"]
                            self._dynamic_alias_cache[coin_clean] = best_id
                            return best_id

                        # 3. Exact name match
                        name_matches = [
                            c for c in coins if c.get("name", "").lower() == coin_clean
                        ]
                        if name_matches:
                            name_matches.sort(
                                key=lambda x: x.get("market_cap_rank") or 999999
                            )
                            best_id = name_matches[0]["id"]
                            self._dynamic_alias_cache[coin_clean] = best_id
                            return best_id

                        # 4. Fallback to top ranked search result
                        coins.sort(key=lambda x: x.get("market_cap_rank") or 999999)
                        best_id = coins[0]["id"]
                        self._dynamic_alias_cache[coin_clean] = best_id
                        return best_id
        except Exception:
            pass

        return coin_clean

    async def _get_cache_seconds(self) -> int:
        return await self.config.cache_minutes() * 60

    async def _fetch_price(self, coin_id: str, currency: str) -> Optional[float]:
        """Return the price, using the cache when it's still fresh."""
        key = (coin_id, currency)
        cache_seconds = await self._get_cache_seconds()

        cached = self._cache.get(key)
        if cached is not None:
            price, fetched_at = cached
            if time.monotonic() - fetched_at < cache_seconds:
                return price

        params = {"ids": coin_id, "vs_currencies": currency}
        try:
            async with self.session.get(
                f"{COINGECKO_API}/simple/price", params=params, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status == 429:
                    raise RateLimitError("CoinGecko")
                if resp.status >= 500:
                    raise APIDownError("CoinGecko", f"HTTP {resp.status}")
                if resp.status != 200:
                    return None
                data = await resp.json()
        except (asyncio.TimeoutError, TimeoutError):
            raise APIDownError("CoinGecko", "connection timed out")
        except aiohttp.ClientError as e:
            raise APIDownError("CoinGecko", "network connection error")
        except asyncio.CancelledError:
            raise

        coin_data = data.get(coin_id)
        if not coin_data or currency not in coin_data:
            return None

        price = coin_data[currency]
        self._cache[key] = (price, time.monotonic())
        return price

    async def _fetch_chart(
        self, coin_id: str, currency: str, days: int
    ) -> Optional[list]:
        """Return a list of [timestamp_ms, price] points, using the cache when fresh."""
        key = (coin_id, currency, days)
        cache_seconds = await self._get_cache_seconds()

        cached = self._chart_cache.get(key)
        if cached is not None:
            data, fetched_at = cached
            if time.monotonic() - fetched_at < cache_seconds:
                return data

        params = {"vs_currency": currency, "days": days}
        try:
            async with self.session.get(
                f"{COINGECKO_API}/coins/{coin_id}/market_chart",
                params=params,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status == 429:
                    raise RateLimitError("CoinGecko")
                if resp.status >= 500:
                    raise APIDownError("CoinGecko", f"HTTP {resp.status}")
                if resp.status != 200:
                    return None
                data = await resp.json()
        except (asyncio.TimeoutError, TimeoutError):
            raise APIDownError("CoinGecko", "connection timed out")
        except aiohttp.ClientError as e:
            raise APIDownError("CoinGecko", "network connection error")
        except asyncio.CancelledError:
            raise

        prices = data.get("prices")
        if not prices:
            return None

        self._chart_cache[key] = (prices, time.monotonic())
        return prices

    async def _render_chart(
        self, prices: list, coin_id: str, currency: str, days: int
    ) -> Optional[io.BytesIO]:
        """Render a chart using QuickChart.io API without any heavy local C dependencies."""
        import datetime

        step = max(1, len(prices) // 100)
        sampled = prices[::step]
        if prices[-1] not in sampled:
            sampled.append(prices[-1])

        labels = []
        for p in sampled:
            dt = datetime.datetime.fromtimestamp(p[0] / 1000, tz=datetime.timezone.utc)
            if days <= 1:
                labels.append(dt.strftime("%H:%M"))
            elif days <= 7:
                labels.append(dt.strftime("%a %H:%M"))
            else:
                labels.append(dt.strftime("%b %d"))

        values = [round(p[1], 6) if p[1] < 1 else round(p[1], 2) for p in sampled]

        start_p, end_p = sampled[0][1], sampled[-1][1]
        line_color = "#57f287" if end_p >= start_p else "#ed4245"  # Discord Green / Discord Red
        bg_color = (
            "rgba(87, 242, 135, 0.12)" if end_p >= start_p else "rgba(237, 66, 69, 0.12)"
        )

        chart_config = {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": f"{coin_id.upper()} ({currency.upper()})",
                        "data": values,
                        "borderColor": line_color,
                        "backgroundColor": bg_color,
                        "fill": True,
                        "borderWidth": 2.5,
                        "pointRadius": 0,
                        "tension": 0.25,
                    }
                ],
            },
            "options": {
                "legend": {"display": False},
                "title": {
                    "display": True,
                    "text": f"{coin_id.capitalize()} — Last {days}d ({currency.upper()})",
                    "fontColor": "#f2f3f5",
                    "fontFamily": "gg sans, Noto Sans, Helvetica Neue, Arial, sans-serif",
                    "fontSize": 16,
                    "padding": 16,
                },
                "scales": {
                    "xAxes": [
                        {
                            "gridLines": {"color": "rgba(255, 255, 255, 0.05)"},
                            "ticks": {
                                "fontColor": "#949ba4",
                                "fontFamily": "gg sans, Noto Sans, Helvetica Neue, Arial, sans-serif",
                                "maxTicksLimit": 8,
                                "autoSkip": True,
                            },
                        }
                    ],
                    "yAxes": [
                        {
                            "gridLines": {"color": "rgba(255, 255, 255, 0.05)"},
                            "ticks": {
                                "fontColor": "#949ba4",
                                "fontFamily": "gg sans, Noto Sans, Helvetica Neue, Arial, sans-serif",
                            },
                        }
                    ],
                },
            },
        }

        payload = {
            "backgroundColor": "#2b2d31",  # Discord Embed Background
            "width": 800,
            "height": 400,
            "devicePixelRatio": 1.5,
            "format": "png",
            "chart": chart_config,
        }

        try:
            async with self.session.post(
                QUICKCHART_API, json=payload, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    buf = io.BytesIO(data)
                    buf.seek(0)
                    return buf
        except Exception as e:
            log.warning(f"Failed to generate QuickChart: {e}")
        return None

    async def _fetch_fear_greed(self, limit: int) -> Optional[list]:
        """Return a list of Fear & Greed Index entries (newest first), using
        the cache when fresh. Source: alternative.me (no API key required).
        """
        cache_seconds = await self._get_cache_seconds()

        cached = self._fng_cache.get(limit)
        if cached is not None:
            data, fetched_at = cached
            if time.monotonic() - fetched_at < cache_seconds:
                return data

        params = {"limit": limit, "format": "json"}
        try:
            async with self.session.get(
                ALTERNATIVE_ME_API, params=params, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status == 429:
                    raise RateLimitError("Alternative.me")
                if resp.status >= 500:
                    raise APIDownError("Alternative.me", f"HTTP {resp.status}")
                if resp.status != 200:
                    return None
                payload = await resp.json()
        except (asyncio.TimeoutError, TimeoutError):
            raise APIDownError("Alternative.me", "connection timed out")
        except aiohttp.ClientError as e:
            raise APIDownError("Alternative.me", "network connection error")
        except asyncio.CancelledError:
            raise

        entries = payload.get("data")
        if not entries:
            return None

        self._fng_cache[limit] = (entries, time.monotonic())
        return entries

    @staticmethod
    def _fng_color(value: int) -> discord.Color:
        if value <= 24:
            return discord.Color.dark_red()
        if value <= 49:
            return discord.Color.orange()
        if value <= 54:
            return discord.Color.gold()
        if value <= 74:
            return discord.Color.green()
        return discord.Color.dark_green()

    async def _render_fng_chart(self, entries: list) -> Optional[io.BytesIO]:
        """Render Fear & Greed trend chart using QuickChart.io API."""
        import datetime

        entries = list(reversed(entries))
        labels = [
            datetime.datetime.fromtimestamp(
                int(e["timestamp"]), tz=datetime.timezone.utc
            ).strftime("%b %d")
            for e in entries
        ]
        values = [int(e["value"]) for e in entries]

        chart_config = {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": "Fear & Greed Index",
                        "data": values,
                        "borderColor": "#5865f2",  # Discord Blurple
                        "backgroundColor": "rgba(88, 101, 242, 0.15)",
                        "fill": True,
                        "borderWidth": 2.5,
                        "pointRadius": 1 if len(values) <= 30 else 0,
                        "tension": 0.25,
                    }
                ],
            },
            "options": {
                "legend": {"display": False},
                "title": {
                    "display": True,
                    "text": "Crypto Fear & Greed Index History",
                    "fontColor": "#f2f3f5",
                    "fontFamily": "gg sans, Noto Sans, Helvetica Neue, Arial, sans-serif",
                    "fontSize": 16,
                    "padding": 16,
                },
                "scales": {
                    "xAxes": [
                        {
                            "gridLines": {"color": "rgba(255, 255, 255, 0.05)"},
                            "ticks": {
                                "fontColor": "#949ba4",
                                "fontFamily": "gg sans, Noto Sans, Helvetica Neue, Arial, sans-serif",
                                "maxTicksLimit": 8,
                                "autoSkip": True,
                            },
                        }
                    ],
                    "yAxes": [
                        {
                            "gridLines": {"color": "rgba(255, 255, 255, 0.05)"},
                            "ticks": {
                                "fontColor": "#949ba4",
                                "fontFamily": "gg sans, Noto Sans, Helvetica Neue, Arial, sans-serif",
                                "min": 0,
                                "max": 100,
                            },
                        }
                    ],
                },
            },
        }

        payload = {
            "backgroundColor": "#2b2d31",  # Discord Embed Background
            "width": 800,
            "height": 400,
            "devicePixelRatio": 1.5,
            "format": "png",
            "chart": chart_config,
        }

        try:
            async with self.session.post(
                QUICKCHART_API, json=payload, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    buf = io.BytesIO(data)
                    buf.seek(0)
                    return buf
        except Exception as e:
            log.warning(f"Failed to generate Fear & Greed QuickChart: {e}")
        return None

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def coin(self, ctx: commands.Context, coin: str, currency: str = "usd"):
        """Get just the current price of a cryptocurrency (no embed, price only).

        Example:
        - `[p]coin btc`
        - `[p]coin imx`
        - `[p]coin stx eur`
        """
        currency = currency.lower().strip()

        async with ctx.typing():
            coin_id = await self._resolve_id(coin)
            try:
                price = await self._fetch_price(coin_id, currency)
            except CryptoAPIError as e:
                await ctx.send(e.message)
                return

        if price is None:
            await ctx.send(f"Couldn't find a price for `{coin}` in `{currency}`.")
            return

        await ctx.send(f"{price:,.6g} {currency.upper()}")

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def cryptoinfo(
        self,
        ctx: commands.Context,
        coin: str,
        days: Optional[int] = 7,
        currency: str = "usd",
    ):
        """Show a simple price chart for a cryptocurrency.

        `days` is how far back to chart (CoinGecko's public tier supports
        up to 365). Defaults to 7 days.

        Example:
        - `[p]cryptoinfo btc`
        - `[p]cryptoinfo imx`
        - `[p]cryptoinfo stx eur`
        - `[p]cryptoinfo ethereum 30 eur`
        """
        currency = currency.lower().strip()
        days = max(1, min(days or 7, 365))

        async with ctx.typing():
            coin_id = await self._resolve_id(coin)
            try:
                prices = await self._fetch_chart(coin_id, currency, days)
            except CryptoAPIError as e:
                await ctx.send(e.message)
                return

        if not prices or len(prices) < 2:
            await ctx.send(
                f"Couldn't find chart data for `{coin}` in `{currency}`. "
                "Check the coin id/ticker and currency code and try again."
            )
            return

        values = [p[1] for p in prices]
        current, start = values[-1], values[0]
        change_pct = ((current - start) / start) * 100 if start else 0

        chart_buf = await self._render_chart(prices, coin_id, currency, days)
        chart_file = (
            discord.File(chart_buf, filename="chart.png") if chart_buf else None
        )

        embed = discord.Embed(
            title=f"{coin_id.capitalize()} — last {days} day(s)",
            color=await ctx.embed_color(),
        )
        embed.add_field(name="Current", value=f"{current:,.6g} {currency.upper()}")
        embed.add_field(name="Change", value=f"{change_pct:+.2f}%")
        embed.add_field(name="High / Low", value=f"{max(values):,.6g} / {min(values):,.6g}")
        if chart_file:
            embed.set_image(url="attachment://chart.png")
        cache_minutes = await self.config.cache_minutes()
        embed.set_footer(text=f"Source: CoinGecko • cached up to {cache_minutes} min")

        await ctx.send(embed=embed, file=chart_file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def crypto(self, ctx: commands.Context, coin: str, currency: str = "usd"):
        """Get the current price of a cryptocurrency.

        `coin` can be a common ticker (btc, eth, imx, stx, ...) or a CoinGecko id
        (e.g. `bitcoin`, `ethereum`, `immutable-x`, `blockstack`).
        `currency` defaults to usd, but any CoinGecko-supported currency works
        (eur, gbp, jpy, ...).

        Example:
        - `[p]crypto btc`
        - `[p]crypto imx`
        - `[p]crypto stx eur`
        - `[p]crypto ethereum eur`
        """
        currency = currency.lower().strip()

        async with ctx.typing():
            coin_id = await self._resolve_id(coin)
            try:
                price = await self._fetch_price(coin_id, currency)
            except CryptoAPIError as e:
                await ctx.send(e.message)
                return

        if price is None:
            await ctx.send(
                f"Couldn't find a price for `{coin}` in `{currency}`. "
                "Check the coin id/ticker and currency code and try again."
            )
            return

        embed = discord.Embed(
            title=f"{coin_id.capitalize()} Price",
            description=f"**{price:,.6g} {currency.upper()}**",
            color=await ctx.embed_color(),
        )
        cache_minutes = await self.config.cache_minutes()
        embed.set_footer(text=f"Source: CoinGecko • cached up to {cache_minutes} min")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def feargreed(self, ctx: commands.Context, days: int = 1):
        """Show the Crypto Fear & Greed Index (via alternative.me).

        `days` of history to include. 1 shows just the current reading;
        anything higher also attaches a trend chart. Capped at 90.

        Example:
        - `[p]feargreed`
        - `[p]feargreed 30`
        """
        days = max(1, min(days, 90))

        async with ctx.typing():
            try:
                entries = await self._fetch_fear_greed(days)
            except CryptoAPIError as e:
                await ctx.send(e.message)
                return

        if not entries:
            await ctx.send("Couldn't fetch the Fear & Greed Index right now.")
            return

        latest = entries[0]
        value = int(latest["value"])
        classification = latest["value_classification"]

        embed = discord.Embed(
            title="Crypto Fear & Greed Index",
            description=f"**{value}/100 — {classification}**",
            color=self._fng_color(value),
        )
        cache_minutes = await self.config.cache_minutes()
        embed.set_footer(text=f"Source: alternative.me • cached up to {cache_minutes} min")

        file = None
        if days > 1 and len(entries) > 1:
            chart_buf = await self._render_fng_chart(entries)
            if chart_buf:
                file = discord.File(chart_buf, filename="feargreed.png")
                embed.set_image(url="attachment://feargreed.png")

        await ctx.send(embed=embed, file=file)

    @commands.is_owner()
    @commands.command()
    async def cryptocache(self, ctx: commands.Context):
        """Clear the in-memory crypto price, chart, and fear/greed cache (owner only)."""
        self._cache.clear()
        self._chart_cache.clear()
        self._fng_cache.clear()
        self._dynamic_alias_cache.clear()
        await ctx.send("Crypto price, chart, and fear/greed cache cleared.")

    @commands.is_owner()
    @commands.command()
    async def cryptocachetime(self, ctx: commands.Context, minutes: int):
        """Set how many minutes prices stay cached before refetching (owner only)."""
        if minutes < 1:
            await ctx.send("Cache time must be at least 1 minute.")
            return
        await self.config.cache_minutes.set(minutes)
        self._cache.clear()
        self._chart_cache.clear()
        self._fng_cache.clear()
        self._dynamic_alias_cache.clear()
        await ctx.send(f"Cache duration set to {minutes} minute(s). Cache cleared.")
