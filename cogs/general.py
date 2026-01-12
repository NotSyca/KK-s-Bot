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
        
    @app_commands.command(name="join", description="Hace que el bot entre a tu canal de voz")
    async def join(self, interaction: discord.Interaction):
        # 1. Verificar si el usuario que llama al comando está en un canal
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ Debes estar en un canal de voz para usar esto.", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        
        # 2. Verificar si el bot ya está conectado en este servidor
        voice_client = interaction.guild.voice_client

        if voice_client:
            # Si ya está conectado, verificamos si es el mismo canal
            if voice_client.channel.id == channel.id:
                await interaction.response.send_message("ya estoy aquí contigo 👀", ephemeral=True)
                return
            else:
                # Si está en otro canal, lo movemos
                await voice_client.move_to(channel)
                await interaction.response.send_message(f"✈️ Me moví a **{channel.name}**")
        else:
            # 3. Si no está conectado, conectamos
            try:
                await channel.connect()
                logger.info(f"Conectado al canal de voz: {channel.name} en {interaction.guild.name}")
                await interaction.response.send_message(f"🔊 Conectado a **{channel.name}**")
            except Exception as e:
                logger.error(f"Error al conectar a voz: {e}")
                await interaction.response.send_message("❌ Ocurrió un error al intentar entrar.", ephemeral=True)

    @app_commands.command(name="leave", description="Saca al bot del canal de voz")
    async def leave(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client

        if voice_client:
            await voice_client.disconnect()
            await interaction.response.send_message("👋 Desconectado.")
            logger.info(f"Desconectado de voz en {interaction.guild.name}")
        else:
            await interaction.response.send_message("❌ No estoy conectado a ningún canal de voz.", ephemeral=True)

# 3. La función setup va AL FINAL y usa el nombre de la clase de arriba
async def setup(bot):
    # Fíjate que aquí dice "General(bot)", coincidiendo con "class General"
    await bot.add_cog(General(bot))