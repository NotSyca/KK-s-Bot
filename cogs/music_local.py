import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
import spotipy
#from spotipy.oauth2 import SpotifyClientCredentials

# --- CONFIGURACIÓN ---
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
    'default_search': 'auto', # CRÍTICO: Permite buscar "Bad Bunny" sin ser link
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class MusicLocal(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sp = None
        
        # Intentamos cargar Spotify, si falla o no hay claves, no pasa nada
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        
        if client_id and client_secret and client_id != "tu_id_aqui":
            try:
                self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
                print("✅ API de Spotify conectada (Modo Premium).")
            except Exception:
                print("⚠️ Credenciales de Spotify inválidas. Usando modo YouTube Puro.")
        else:
            print("ℹ️ Modo YouTube Puro activado (Sin Spotify).")

    async def get_spotify_track_info(self, url):
        if not self.sp: return None
        try:
            loop = asyncio.get_event_loop()
            track = await loop.run_in_executor(None, lambda: self.sp.track(url))
            return f"{track['artists'][0]['name']} - {track['name']} audio"
        except:
            return None

    @app_commands.command(name="play", description="Pon música (Escribe el nombre o link de YouTube)")
    @app_commands.describe(busqueda="Ej: 'Linkin Park Numb' o URL de YouTube")
    async def play(self, interaction: discord.Interaction, busqueda: str):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Entra a voz primero.", ephemeral=True)

        await interaction.response.defer()

        # Detección de Spotify (Solo avisamos si intenta usarlo sin tener claves)
        if "open.spotify.com" in busqueda:
            if not self.sp:
                return await interaction.followup.send("⚠️ Spotify está bloqueado temporalmente por su API. \n👉 **Solución:** Escribe el nombre de la canción en lugar del link. Ej: `/play busqueda: Bad Bunny Monaco`")
            
            # Si tuviera claves (en el futuro), hace esto:
            nuevo_termino = await self.get_spotify_track_info(busqueda)
            if nuevo_termino: busqueda = nuevo_termino

        # Conectar a voz
        if not interaction.guild.voice_client:
            try:
                vc = await interaction.user.voice.channel.connect()
            except:
                return await interaction.followup.send("❌ Error al conectar al canal.")
        else:
            vc = interaction.guild.voice_client

        if vc.is_playing():
            vc.stop()

        # Buscar y Reproducir
        try:
            loop = self.bot.loop
            # La magia está aquí: 'busqueda' puede ser un Link O un Nombre
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(busqueda, download=False))

            if 'entries' in data:
                data = data['entries'][0]

            filename = data['url']
            title = data.get('title', 'Canción desconocida')
            
            source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
            vc.play(discord.PCMVolumeTransformer(source, volume=0.5))
            
            await interaction.followup.send(f'▶️ Reproduciendo: **{title}**')
            
        except Exception as e:
            print(f"Error: {e}") # Log consola
            await interaction.followup.send("❌ No encontré la canción o hubo un error de conexión.")

    @app_commands.command(name="stop", description="Detiene la música")
    async def stop(self, interaction: discord.Interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("🛑 Bot desconectado.")
        else:
            await interaction.response.send_message("❌ No estoy conectado.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MusicLocal(bot))