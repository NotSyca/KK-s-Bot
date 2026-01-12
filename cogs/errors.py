import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger("bot")

class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("✅ Cog ErrorHandler listo.")
        # Asignar el manejador de errores global al árbol de comandos
        self.bot.tree.on_error = self.on_app_command_error

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # 1. Falta de Permisos del Usuario
        if isinstance(error, app_commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions)
            await interaction.response.send_message(
                f"⛔ **Acceso Denegado:** No tienes permisos suficientes.\nTe falta: `{missing}`", 
                ephemeral=True
            )
        
        # 2. Falta de Permisos del Bot
        elif isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            await interaction.response.send_message(
                f"🔒 **No puedo hacer eso:** Me faltan permisos en este servidor.\nNecesito: `{missing}`", 
                ephemeral=True
            )
            
        # 3. Cooldown (Comando usado muy rápido)
        elif isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏳ **Calma:** Espera `{error.retry_after:.2f}s` antes de usar este comando de nuevo.", 
                ephemeral=True
            )
            
        # 4. Errores genéricos
        else:
            logger.error(f"Error en comando: {error}")
            # Si ya se respondió (defer), usamos followup, si no, response
            if interaction.response.is_done():
                await interaction.followup.send("❌ Ocurrió un error inesperado. Revisa los logs.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Ocurrió un error inesperado.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))