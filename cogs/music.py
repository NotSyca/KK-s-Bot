import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio

# Configuración de yt-dlp para obtener la mejor calidad de audio posible sin video
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0', # Bind to ipv4
}

# Configuración de FFmpeg para transmitir a Discord
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        # Ejecutamos la extracción en un hilo separado para no congelar al bot
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # Si es una playlist, tomamos el primer item
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

class music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="play", description="Reproduce música (Modo Local)")
    @app_commands.describe(busqueda="Nombre o URL de la canción")
    async def play(self, interaction: discord.Interaction, busqueda: str):
        # 1. Verificar si el usuario está en voz
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ ¡Entra a un canal de voz primero!", ephemeral=True)

        await interaction.response.defer()

        # 2. Conectar al bot si no está conectado
        if not interaction.guild.voice_client:
            try:
                await interaction.user.voice.channel.connect()
            except Exception as e:
                return await interaction.followup.send("❌ No pude conectarme al canal.")
        
        vc = interaction.guild.voice_client

        # 3. Detener si ya hay algo sonando (Este sistema simple no tiene cola compleja)
        if vc.is_playing():
            vc.stop()

        try:
            # 4. Obtener el stream
            player = await YTDLSource.from_url(busqueda, loop=self.bot.loop, stream=True)
            
            # 5. Reproducir
            vc.play(player, after=lambda e: print(f'Error de reproducción: {e}') if e else None)
            
            await interaction.followup.send(f'▶️ Reproduciendo: **{player.title}**')
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error al buscar/reproducir: `{e}`")

    @app_commands.command(name="stop", description="Detiene la música y saca al bot")
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
            await interaction.response.send_message("🛑 Desconectado.")
        else:
            await interaction.response.send_message("❌ No estoy en un canal.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(music(bot))