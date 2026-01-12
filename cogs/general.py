import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger("bot")

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Comando de texto normal (se usa con !sync)
    # Solo el dueño del bot puede usarlo
    @commands.command(name="sync")
    @commands.is_owner()
    async def sync(self, ctx):
        await ctx.send("🔄 Sincronizando comandos...")
        try:
            # Sincroniza y guarda los cambios
            synced = await self.bot.tree.sync()
            logger.info(f"Slash commands sincronizados: {len(synced)}")
            await ctx.send(f"✅ Sincronizados {len(synced)} comandos globalmente. Pueden tardar unos minutos en aparecer.")
        except Exception as e:
            logger.error(f"Error sincronizando: {e}")
            await ctx.send(f"❌ Error: {e}")

async def setup(bot):
    await bot.add_cog(Admin(bot))