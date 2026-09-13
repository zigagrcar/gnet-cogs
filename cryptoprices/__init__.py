from redbot.core.bot import Red

from .cryptoprices import CryptoPrices

__red_end_user_data_statement__ = (
    "This cog does not persistently store data about users."
)


async def setup(bot: Red):
    await bot.add_cog(CryptoPrices(bot))
