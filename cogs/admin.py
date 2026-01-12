import discord
from discord.ext import commands
import logging

logger = logging.getLogger("bot")

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sync")
    async def sync(self, ctx):
        """
        Sincroniza los comandos slash INSTANTÁNEAMENTE en este servidor.
        """
        await ctx.send("🔄 Sincronizando comandos en este servidor...")
        
        try:
            # 1. Copia los comandos globales a este servidor específico
            self.bot.tree.copy_global_to(guild=ctx.guild)
            
            # 2. Sincroniza solo con este servidor (Instantáneo)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            
            logger.info(f"Slash commands sincronizados localmente: {len(synced)}")
            await ctx.send(f"✅ **¡Éxito!** Sincronizados {len(synced)} comandos. Deberían aparecer YA.")
        
        except Exception as e:
            logger.error(f"Error sincronizando: {e}")
            await ctx.send(f"❌ Error: {e}")

async def setup(bot):
    await bot.add_cog(Admin(bot))