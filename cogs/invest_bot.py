import discord
from discord.ext import commands
from discord import Option
import logging
# Import the data from your new database file
from cogs.suburbs_database import ALL_AUSTRALIAN_SUBURBS, SUBURB_TO_STATE

logger = logging.getLogger("ShadowSyn.InvestBot")

async def get_suburb_autocomplete(ctx: discord.AutocompleteContext):
    """
    Corrected signature: Py-cord passes only one argument 'ctx'.
    This now searches your suburbs_database.py variables.
    """
    user_input = ctx.value.lower() if ctx.value else ""
    # Prioritize 'starts with' to make R-suburbs appear first
    matches = [s for s in ALL_AUSTRALIAN_SUBURBS if s.lower().startswith(user_input)]
    if len(matches) < 15:
        matches += [s for s in ALL_AUSTRALIAN_SUBURBS if user_input in s.lower() and s not in matches]
    return matches[:15]

class InvestBotCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(name="suburb", description="Get suburb investment analysis")
    async def suburb(self, ctx, 
                     suburb_name: Option(str, description="Suburb name", 
                                        autocomplete=get_suburb_autocomplete)):
        await ctx.defer()
        
        # Access the state mapping from the database file
        state = SUBURB_TO_STATE.get(suburb_name.lower(), "nsw")
        
        # Build embed logic here...
        # Ensure you handle the scraper logic without calling 'self.client'
        # ...
        await ctx.followup.send(f"Analyzing {suburb_name} ({state})...")

def setup(bot):
    bot.add_cog(InvestBotCog(bot))
    logger.info("InvestBotCog linked to suburbs_database.py")
