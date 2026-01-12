import discord
from discord.ext import commands

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Aquí tus comandos...
    @commands.command()
    async def ping(self, ctx):
        await ctx.send("Pong!")

# --- ESTO ES LO QUE TE FALTA ---
async def setup(bot):
    await bot.add_cog(Admin(bot))