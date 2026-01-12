import discord
from discord.ext import commands

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Aquí tus comandos...
    @commands.command()
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latencia: **{latency}ms**",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

# --- ESTO ES LO QUE TE FALTA ---
async def setup(bot):
    await bot.add_cog(Admin(bot))