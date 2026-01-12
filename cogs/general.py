import discord
from discord import app_commands
from discord.ext import commands
import logging

# 1. Configurar logger
logger = logging.getLogger("bot")

# 2. Definir la clase (El nombre "General" es importante)
class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Este evento se dispara cuando el Cog está listo
        logger.info("✅ Cog General listo y operando.")

    @app_commands.command(name="ping", description="Ver la latencia del bot")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        logger.info(f"Comando /ping usado por {interaction.user}")
        
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latencia: **{latency}ms**",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

# 3. La función setup va AL FINAL y usa el nombre de la clase de arriba
async def setup(bot):
    # Fíjate que aquí dice "General(bot)", coincidiendo con "class General"
    await bot.add_cog(General(bot))