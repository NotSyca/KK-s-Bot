import discord
from discord.ext import commands
from discord import app_commands
import wavelink
import typing

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        # Configuración del Nodo Lavalink.
        # NOTA: Los nodos públicos mueren a veces. Lo ideal es hostear tu propio Lavalink.
        # Para desarrollo usaremos uno público de "Lavalink List".
        nodes = [
            wavelink.Node(
                uri="https://lavalink.devamop.in:443", # Nodo público (ejemplo)
                password="DevamOP"
            )
        ]
        # Conectamos Wavelink al iniciar el Cog
        await wavelink.Pool.connect(nodes=nodes, client=self.bot, cache_capacity=100)
        print("✅ Sistema de música (Wavelink) conectado.")

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"🎵 Nodo Lavalink listo: {payload.node.identifier}")

    # --- COMANDOS ---

    @app_commands.command(name="play", description="Reproduce música de YouTube/SoundCloud/Spotify")
    @app_commands.describe(busqueda="URL o nombre de la canción")
    async def play(self, interaction: discord.Interaction, busqueda: str):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Entra a un canal de voz primero.", ephemeral=True)

        await interaction.response.defer() # Evita timeout si tarda en buscar

        # Buscar la canción
        tracks = await wavelink.Playable.search(busqueda)
        if not tracks:
            return await interaction.followup.send("❌ No encontré nada con ese nombre.")
        
        track = tracks[0] # Tomamos el primer resultado

        # Conectar al canal si no está conectado
        if not interaction.guild.voice_client:
            vc: wavelink.Player = await interaction.user.voice.channel.connect(cls=wavelink.Player)
        else:
            vc: wavelink.Player = interaction.guild.voice_client

        # Añadir a la cola y reproducir
        await vc.queue.put_wait(track)
        
        if not vc.playing:
            await vc.play(vc.queue.get())
            await interaction.followup.send(f"▶️ Reproduciendo: **{track.title}**")
        else:
            await interaction.followup.send(f"d📝 Añadido a la cola: **{track.title}**")

    @app_commands.command(name="skip", description="Salta la canción actual")
    async def skip(self, interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client
        if not vc or not vc.playing:
            return await interaction.response.send_message("❌ No hay nada sonando.", ephemeral=True)
        
        await vc.skip(force=True)
        await interaction.response.send_message("⏭️ Canción saltada.")

    @app_commands.command(name="stop", description="Detiene la música y desconecta")
    async def stop(self, interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
            await interaction.response.send_message("🛑 Desconectado.")
        else:
            await interaction.response.send_message("❌ No estoy conectado.", ephemeral=True)

    @app_commands.command(name="volumen", description="Cambia el volumen (0-100)")
    async def volumen(self, interaction: discord.Interaction, valor: int):
        vc: wavelink.Player = interaction.guild.voice_client
        if not vc: return await interaction.response.send_message("❌ No estoy conectado.", ephemeral=True)
        
        valor = max(0, min(100, valor)) # Limitar entre 0 y 100
        await vc.set_volume(valor)
        await interaction.response.send_message(f"🔊 Volumen ajustado a **{valor}%**")

    # --- FEATURE PREMIUM: FILTROS ---
    @app_commands.command(name="filtro", description="Aplica filtros de audio (Bassboost, Nightcore)")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Ninguno", value="none"),
        app_commands.Choice(name="Bassboost (Bajo fuerte)", value="bass"),
        app_commands.Choice(name="Nightcore (Rápido/Agudo)", value="night")
    ])
    async def filtro(self, interaction: discord.Interaction, tipo: app_commands.Choice[str]):
        vc: wavelink.Player = interaction.guild.voice_client
        if not vc: return await interaction.response.send_message("❌ No estoy conectado.", ephemeral=True)

        filters: wavelink.Filters = vc.filters

        if tipo.value == "bass":
            # Ecualizador para resaltar bajos
            filters.equalizer.set(bands=[
                {"band": 0, "gain": 0.25},
                {"band": 1, "gain": 0.25},
                {"band": 2, "gain": 0.25}
            ])
            filters.timescale.reset() # Resetear velocidad
        elif tipo.value == "night":
            # Aumentar velocidad y pitch
            filters.timescale.set(pitch=1.2, speed=1.2, rate=1.0)
            filters.equalizer.reset()
        else:
            filters.reset()

        await vc.set_filters(filters)
        await interaction.response.send_message(f"🎚️ Filtro aplicado: **{tipo.name}**")

async def setup(bot):
    await bot.add_cog(Music(bot))