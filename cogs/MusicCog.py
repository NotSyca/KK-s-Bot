import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from collections import deque

# --- CONFIGURACIÓN TÉCNICA ---
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
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# --- CLASE PARA MANEJAR LA COLA DE CADA SERVIDOR ---
class ServerQueue:
    def __init__(self):
        self.queue = deque() # La lista de canciones en espera
        self.current_track = None # La canción sonando ahora
        self.volume = 0.5 # Volumen por defecto (50%)

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {} # Diccionario para guardar las colas de cada servidor {guild_id: ServerQueue}
        
        # Configuración Spotify (Opcional)
        self.sp = None
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        if client_id and client_secret and client_id != "tu_id_aqui":
            try:
                self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
                print("✅ Spotify conectado.")
            except:
                print("⚠️ Error en credenciales Spotify.")
        else:
            print("ℹ️ Modo YouTube Puro (Sin Spotify).")

    def get_queue(self, guild_id):
        """Obtiene o crea la cola para un servidor específico"""
        if guild_id not in self.queues:
            self.queues[guild_id] = ServerQueue()
        return self.queues[guild_id]

    async def get_spotify_track_info(self, url):
        """Convierte Link de Spotify -> Texto de búsqueda"""
        if not self.sp: return None
        try:
            loop = asyncio.get_event_loop()
            track = await loop.run_in_executor(None, lambda: self.sp.track(url))
            return f"{track['artists'][0]['name']} - {track['name']} audio"
        except:
            return None

    # --- SISTEMA DE REPRODUCCIÓN ---
    def play_next(self, guild, vc):
        """Función recursiva que se llama cuando termina una canción"""
        sq = self.get_queue(guild.id)
        
        if len(sq.queue) > 0:
            # Sacamos la siguiente canción de la cola
            next_url, next_title = sq.queue.popleft()
            sq.current_track = next_title

            # Función interna para procesar el audio sin bloquear
            async def start_playback():
                try:
                    loop = self.bot.loop
                    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(next_url, download=False))
                    
                    if 'entries' in data: data = data['entries'][0]
                    filename = data['url']
                    
                    source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
                    source = discord.PCMVolumeTransformer(source, volume=sq.volume)
                    
                    # El 'after' llama a play_next otra vez cuando esta termine
                    vc.play(source, after=lambda e: self.play_next(guild, vc))
                    
                except Exception as e:
                    print(f"Error reproduciendo {next_title}: {e}")
                    self.play_next(guild, vc) # Si falla, intenta la siguiente

            # Ejecutamos la tarea asíncrona de forma segura desde el hilo principal
            asyncio.run_coroutine_threadsafe(start_playback(), self.bot.loop)
        else:
            # Se acabó la cola
            sq.current_track = None
            # Opcional: Desconectar automáticamente tras un tiempo
            # asyncio.run_coroutine_threadsafe(vc.disconnect(), self.bot.loop)

    # --- COMANDOS INTERACTIVOS ---

    @app_commands.command(name="play", description="Añade una canción a la cola")
    @app_commands.describe(busqueda="Link de YouTube/Spotify o nombre de la canción")
    async def play(self, interaction: discord.Interaction, busqueda: str):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Entra a un canal de voz.", ephemeral=True)

        await interaction.response.defer()

        # 1. Manejo de Spotify
        if "spotify.com" in busqueda:
            if not self.sp:
                # Fallback manual
                if "track" in busqueda:
                     return await interaction.followup.send("⚠️ Spotify desactivado temporalmente. Por favor escribe el nombre de la canción.")
            else:
                converted = await self.get_spotify_track_info(busqueda)
                if converted: busqueda = converted

        # 2. Conexión a Voz
        if not interaction.guild.voice_client:
            try:
                vc = await interaction.user.voice.channel.connect()
            except:
                return await interaction.followup.send("❌ No pude conectar.")
        else:
            vc = interaction.guild.voice_client

        # 3. Añadir a la Cola (Lógica PRO)
        sq = self.get_queue(interaction.guild.id)
        
        # Obtenemos info básica antes de procesar (para mostrar título rápido)
        # Nota: Hacemos una búsqueda rápida para obtener título y URL
        try:
            loop = self.bot.loop
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(busqueda, download=False))
            
            if 'entries' in data: data = data['entries'][0]
            
            title = data.get('title', 'Canción desconocida')
            url = data.get('webpage_url', busqueda) # URL limpia para guardar en cola

            # Añadimos a la cola interna
            sq.queue.append((url, title))

            if not vc.is_playing() and not vc.is_paused():
                # Si no está sonando nada, arrancamos el ciclo
                self.play_next(interaction.guild, vc)
                await interaction.followup.send(f"▶️ **Reproduciendo:** {title}")
            else:
                # Si ya suena algo, solo avisamos que se encoló
                await interaction.followup.send(f"📝 **Añadido a la cola:** {title}")

        except Exception as e:
            await interaction.followup.send(f"❌ Error al buscar: {e}")

    @app_commands.command(name="skip", description="Salta a la siguiente canción")
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            return await interaction.response.send_message("❌ No hay nada sonando.", ephemeral=True)
        
        vc.stop() # Esto fuerza el 'after' del play(), llamando a play_next
        await interaction.response.send_message("⏭️ **Saltada!**")

    @app_commands.command(name="pause", description="Pausa la música")
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ **Pausado.**")
        else:
            await interaction.response.send_message("❌ No se puede pausar ahora.", ephemeral=True)

    @app_commands.command(name="resume", description="Reanuda la música")
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ **Reanudando...**")
        else:
            await interaction.response.send_message("❌ No está pausado.", ephemeral=True)

    @app_commands.command(name="volumen", description="Ajusta el volumen (0-100)")
    async def volumen(self, interaction: discord.Interaction, nivel: int):
        vc = interaction.guild.voice_client
        if not vc or not vc.source:
            return await interaction.response.send_message("❌ No hay música sonando.", ephemeral=True)

        sq = self.get_queue(interaction.guild.id)
        
        # Convertir 0-100 a 0.0-1.0
        nuevo_vol = max(0, min(100, nivel)) / 100
        vc.source.volume = nuevo_vol
        sq.volume = nuevo_vol # Guardar para la siguiente canción
        
        await interaction.response.send_message(f"🔊 Volumen al **{nivel}%**")

    @app_commands.command(name="queue", description="Muestra la lista de reproducción")
    async def queue_list(self, interaction: discord.Interaction):
        sq = self.get_queue(interaction.guild.id)
        if not sq.queue and not sq.current_track:
            return await interaction.response.send_message("📭 La cola está vacía.")

        msg = f"**Sonando ahora:** 🎵 {sq.current_track}\n\n**En espera:**\n"
        for i, (url, title) in enumerate(sq.queue, 1):
            msg += f"`{i}.` {title}\n"
            if i >= 10: # Limite visual
                msg += "... y más."
                break
        
        await interaction.response.send_message(msg)

    @app_commands.command(name="stop", description="Limpia la cola y desconecta")
    async def stop(self, interaction: discord.Interaction):
        sq = self.get_queue(interaction.guild.id)
        sq.queue.clear() # Borrar cola
        sq.current_track = None
        
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("🛑 **Desconectado y cola borrada.**")
        else:
            await interaction.response.send_message("❌ No estoy conectado.", ephemeral=True)

    # =========================================================
    # COMANDOS CON PREFIX (!play, !skip)
    # =========================================================
    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, query: str):
        """Comando para humanos: !play despacito"""
        await self._add_to_queue_logic(ctx, query)

    @commands.command(name="skip", aliases=["s", "next"])
    async def skip(self, ctx):
        """Salta la canción actual"""
        vc = ctx.guild.voice_client
        if vc and vc.is_playing():
            vc.stop() # Esto dispara el 'after' de _play_next
            await ctx.send("⏭️ **Saltada.**")
        else:
            await ctx.send("❌ No hay nada sonando.")

    @commands.command(name="stop", aliases=["leave", "disconnect"])
    async def stop(self, ctx):
        """Desconecta al bot y borra la cola"""
        vc = ctx.guild.voice_client
        if vc:
            # Limpiar cola
            if ctx.guild.id in self.queues:
                self.queues[ctx.guild.id] = []
            await vc.disconnect()
            await ctx.send("👋 **Adiós.**")
        else:
            await ctx.send("❌ No estoy conectado.")

    @commands.command(name="join")
    async def join(self, ctx):
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
            await ctx.send("👍 **Conectado.**")
        else:
            await ctx.send("❌ Entra a un canal primero.")

    # =========================================================
    # PUENTE PARA GEMINI (IA)
    # =========================================================
    # La IA llama a estas funciones exactas.
    # Reutilizamos la lógica de arriba pasando el objeto 'message'.

    async def play_query(self, message, query):
        """Gemini llama a esto. Reutilizamos la lógica de !play"""
        await self._add_to_queue_logic(message, query)

    async def skip(self, message):
        """Gemini llama a esto."""
        # Simulamos un contexto o actuamos directo
        vc = message.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await message.channel.send("⏭️ (Saltado por IA)")

    async def stop(self, message):
        """Gemini llama a esto."""
        vc = message.guild.voice_client
        if vc:
            self.queues[message.guild.id] = []
            await vc.disconnect()
            await message.channel.send("👋 (Desconectado por IA)")

    async def join(self, message):
        """Gemini llama a esto."""
        if message.author.voice:
            await message.author.voice.channel.connect()
            await message.channel.send("👍")
        else:
            await message.channel.send("entra a un canal vos primero")
    
    async def leave(self, message):
        """Alias para stop usado por Gemini"""
        await self.stop(message)

async def setup(bot):
    await bot.add_cog(MusicCog(bot))