import discord
from discord.ext import commands
import yt_dlp
import asyncio

# Configuración de YT-DLP (Optimizado para audio)
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Estructura de colas: {guild_id: [lista_canciones]}
        self.queues = {}

    # =========================================================
    # LÓGICA CENTRAL (REUTILIZABLE)
    # =========================================================
    def get_queue(self, guild_id):
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    async def _play_next(self, guild, voice_client):
        """Función recursiva para tocar la siguiente canción"""
        sq = self.get_queue(guild.id)
        
        if len(sq) > 0:
            # Sacamos la siguiente canción
            url, title = sq.pop(0)
            
            # Definimos la fuente de audio
            source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)
            
            # Definimos qué hacer cuando termine (llamar a esta misma función)
            def after_playing(error):
                if error: print(f"Error FFMPEG: {error}")
                # Correr en el loop principal para evitar bloqueos
                coro = self._play_next(guild, voice_client)
                fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
                try: fut.result()
                except: pass

            voice_client.play(source, after=after_playing)
            print(f"🎵 Tocando ahora: {title}")
        else:
            # Si no hay más canciones, esperamos un rato y desconectamos (opcional)
            pass

    async def _add_to_queue_logic(self, ctx_or_msg, query):
        """
        Lógica compartida: Busca en YT y añade a la cola.
        Acepta 'ctx' (Comando) o 'message' (IA).
        """
        author = ctx_or_msg.author
        guild = ctx_or_msg.guild
        channel = ctx_or_msg.channel # Donde responder

        # 1. Validar Voz
        if not author.voice:
            await channel.send("❌ ¡Entra a un canal de voz primero!")
            return

        # 2. Conectar
        voice_client = guild.voice_client
        if not voice_client:
            try:
                voice_client = await author.voice.channel.connect()
            except Exception as e:
                await channel.send(f"❌ No pude conectarme: {e}")
                return

        # 3. Buscar Canción (Bloqueante, ejecutamos en Thread)
        msg_wait = await channel.send(f"🔎 Buscando `{query}`...")
        
        try:
            loop = self.bot.loop
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
            
            if 'entries' in data: # Si es playlist o búsqueda
                data = data['entries'][0]
            
            url = data['url']
            title = data['title']
            
            # 4. Añadir a cola interna
            sq = self.get_queue(guild.id)
            sq.append((url, title))
            
            await msg_wait.delete() # Borrar mensaje de "buscando"

            # 5. Reproducir si no suena nada
            if not voice_client.is_playing():
                await self._play_next(guild, voice_client)
                await channel.send(f"▶️ **Reproduciendo:** {title}")
            else:
                await channel.send(f"📝 **Encolado:** {title}")

        except Exception as e:
            await channel.send(f"❌ Error buscando: {e}")

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