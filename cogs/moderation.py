import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging

logger = logging.getLogger("bot")

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("✅ Cog Moderación listo.")

    # --- KICK (Expulsar) ---
    @app_commands.command(name="kick", description="Expulsa a un usuario del servidor.")
    @app_commands.describe(usuario="El miembro a expulsar", razon="Motivo de la expulsión")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, usuario: discord.Member, razon: str = "No especificada"):
        if usuario.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ No puedes expulsar a alguien con igual o mayor rango que tú.", ephemeral=True)
            return

        try:
            await usuario.kick(reason=f"Por: {interaction.user} | Razón: {razon}")
            
            embed = discord.Embed(title="👢 Usuario Expulsado", color=discord.Color.orange())
            embed.add_field(name="Usuario", value=f"{usuario.mention} (`{usuario.id}`)", inline=True)
            embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
            embed.add_field(name="Razón", value=razon, inline=False)
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user} expulsó a {usuario}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Error al expulsar: {e}", ephemeral=True)

    # --- BAN (Banear) ---
    @app_commands.command(name="ban", description="Banea a un usuario permanentemente.")
    @app_commands.describe(borrar_mensajes="Borrar mensajes de los últimos días (0-7)")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, usuario: discord.Member, borrar_mensajes: int = 0, razon: str = "No especificada"):
        if usuario.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ No puedes banear a alguien con igual o mayor rango que tú.", ephemeral=True)
            return

        try:
            # delete_message_days está deprecado, usamos delete_message_seconds
            seconds = borrar_mensajes * 86400 # Convertir días a segundos
            await usuario.ban(reason=f"Por: {interaction.user} | Razón: {razon}", delete_message_seconds=seconds)
            
            embed = discord.Embed(title="⛔ Usuario Baneado", color=discord.Color.dark_red())
            embed.add_field(name="Usuario", value=f"{usuario.mention}", inline=True)
            embed.add_field(name="Razón", value=razon, inline=False)
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user} baneó a {usuario}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Error al banear: {e}", ephemeral=True)

    # --- TIMEOUT (Aislamiento) ---
    @app_commands.command(name="timeout", description="Aísla a un usuario (Mute moderno).")
    @app_commands.describe(minutos="Duración del aislamiento en minutos")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, usuario: discord.Member, minutos: int, razon: str = "No especificada"):
        if usuario.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ No puedes aislar a alguien con igual o mayor rango.", ephemeral=True)
            return

        duration = datetime.timedelta(minutes=minutos)
        try:
            await usuario.timeout(duration, reason=razon)
            await interaction.response.send_message(f"🤐 **{usuario.mention}** ha sido aislado por **{minutos} minutos**.\n📝 Razón: {razon}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    # --- CLEAR (Limpiar Chat) ---
    @app_commands.command(name="clear", description="Borra mensajes del chat.")
    @app_commands.describe(cantidad="Número de mensajes a borrar (Max 100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, cantidad: int):
        if cantidad > 100: cantidad = 100
        
        # Defer: Avisamos a Discord que vamos a tardar un poco (borrar mensajes toma tiempo)
        await interaction.response.defer(ephemeral=True) 
        
        deleted = await interaction.channel.purge(limit=cantidad)
        
        await interaction.followup.send(f"🧹 Se han borrado **{len(deleted)}** mensajes.", ephemeral=True)
        logger.info(f"{interaction.user} borró {len(deleted)} mensajes en #{interaction.channel.name}")

async def setup(bot):
    await bot.add_cog(Moderation(bot))