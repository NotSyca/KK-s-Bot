import discord
from discord.ext import commands
from discord import app_commands

class Activities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="youtube", description="Inicia YouTube Watch Together en el canal de voz")
    async def youtube(self, interaction: discord.Interaction):
        # Verificar si el usuario está en voz
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Entra a un canal de voz primero.", ephemeral=True)

        channel = interaction.user.voice.channel

        # ID oficial de la actividad de YouTube en Discord
        YOUTUBE_ACTIVITY_ID = 880218394199220334 

        try:
            # Creamos la invitación a la actividad
            invite = await channel.create_invite(
                target_application_id=YOUTUBE_ACTIVITY_ID,
                target_type=discord.InviteTargetType.embedded_application,
                max_age=0, # Infinito
                max_uses=0 # Usos ilimitados
            )
            
            # Enviamos el link (botón)
            view = discord.ui.View()
            button = discord.ui.Button(label="📺 Abrir YouTube Together", url=invite.url, style=discord.ButtonStyle.link)
            view.add_item(button)

            await interaction.response.send_message(f"¡Listo! Haz clic abajo para iniciar YouTube en **{channel.name}**:", view=view)

        except discord.Forbidden:
            await interaction.response.send_message("❌ No tengo permisos para crear invitaciones en ese canal.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error desconocido: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Activities(bot))