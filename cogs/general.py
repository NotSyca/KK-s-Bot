import discord
from discord import app_commands
from discord.ext import commands
import logging
import platform
import datetime
from typing import Optional

# 1. Configurar Logger
logger = logging.getLogger("bot")

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Guardamos la hora de inicio para calcular el Uptime
        self.start_time = datetime.datetime.now()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("✅ Cog General cargado y listo.")

    # --- COMANDO PING ---
    @app_commands.command(name="ping", description="Verifica la latencia y conexión con la API.")
    async def ping(self, interaction: discord.Interaction):
        # Calculamos latencia
        latency = round(self.bot.latency * 1000)
        
        # Color dinámico: Verde si es rápido, Rojo si es lento
        color = discord.Color.green() if latency < 150 else discord.Color.red()
        
        embed = discord.Embed(title="🏓 Pong!", color=color)
        embed.add_field(name="Latencia API", value=f"```js\n{latency}ms```", inline=True)
        # Aquí podrías añadir latencia de base de datos si la tuvieras
        
        await interaction.response.send_message(embed=embed)

    # --- COMANDO USERINFO (Información de Usuario) ---
    @app_commands.command(name="userinfo", description="Muestra información avanzada de un usuario.")
    @app_commands.describe(usuario="El usuario del que quieres ver info (Déjalo vacío para ver la tuya)")
    async def userinfo(self, interaction: discord.Interaction, usuario: Optional[discord.Member] = None):
        target = usuario or interaction.user
        
        # Crear Embed
        embed = discord.Embed(
            title=f"Información de {target.display_name}",
            color=target.color if target.color != discord.Color.default() else discord.Color.blue()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        
        # Fechas con formato relativo de Discord (<t:timestamp:R> = "hace X tiempo")
        created_at = int(target.created_at.timestamp())
        joined_at = int(target.joined_at.timestamp()) if target.joined_at else None

        embed.add_field(name="👤 Identidad", value=f"**Nombre:** {target.name}\n**ID:** `{target.id}`\n**Mención:** {target.mention}", inline=False)
        embed.add_field(name="📅 Fechas", value=f"**Creado:** <t:{created_at}:D> (<t:{created_at}:R>)\n**Unido:** <t:{joined_at}:D> (<t:{joined_at}:R>)", inline=False)
        
        # Roles (excluyendo @everyone)
        roles = [role.mention for role in target.roles if role.name != "@everyone"]
        roles_str = ", ".join(roles) if roles else "Sin roles"
        # Cortar si es muy largo para evitar errores
        if len(roles_str) > 1000: 
            roles_str = roles_str[:1000] + "..."
            
        embed.add_field(name=f"🛡️ Roles [{len(roles)}]", value=roles_str, inline=False)
        embed.set_footer(text=f"Solicitado por {interaction.user.name}", icon_url=interaction.user.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    # --- COMANDO SERVERINFO (Información del Servidor) ---
    @app_commands.command(name="serverinfo", description="Datos técnicos del servidor actual.")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        
        embed = discord.Embed(title=f"Información de {guild.name}", color=discord.Color.gold())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        created_at = int(guild.created_at.timestamp())
        
        # Contadores
        total_members = guild.member_count
        # Nota: contar bots vs humanos requiere intents.members = True (ya lo tienes)
        bots = len([m for m in guild.members if m.bot])
        humans = total_members - bots

        embed.add_field(name="👑 Dueño", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="🆔 ID Servidor", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="📅 Creado", value=f"<t:{created_at}:R>", inline=True)
        
        embed.add_field(name="👥 Miembros", value=f"**Total:** {total_members}\n**Humanos:** {humans}\n**Bots:** {bots}", inline=True)
        embed.add_field(name="🚀 Boosts", value=f"Nivel: {guild.premium_tier}\nMejoras: {guild.premium_subscription_count}", inline=True)
        
        await interaction.response.send_message(embed=embed)

    # --- COMANDO AVATAR ---
    @app_commands.command(name="avatar", description="Obtén la imagen de perfil de alguien en alta calidad.")
    async def avatar(self, interaction: discord.Interaction, usuario: Optional[discord.Member] = None):
        target = usuario or interaction.user
        
        embed = discord.Embed(title=f"Avatar de {target.display_name}", color=discord.Color.purple())
        # Usamos size=4096 para máxima calidad
        embed.set_image(url=target.display_avatar.url)
        
        # Botones para descargar
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Descargar (PNG)", url=target.display_avatar.with_format("png").url))
        if target.display_avatar.is_animated():
            view.add_item(discord.ui.Button(label="Descargar (GIF)", url=target.display_avatar.with_format("gif").url))
            
        await interaction.response.send_message(embed=embed, view=view)

    # --- COMANDO BOTINFO (Estadísticas) ---
    @app_commands.command(name="botinfo", description="Estadísticas técnicas del bot.")
    async def botinfo(self, interaction: discord.Interaction):
        # Calcular Uptime
        uptime = datetime.datetime.now() - self.start_time
        uptime_str = str(uptime).split('.')[0] # Quitar milisegundos feos
        
        embed = discord.Embed(title="🤖 Panel de Control", color=discord.Color.dark_grey())
        
        embed.add_field(name="Versiones", value=f"Python: `{platform.python_version()}`\nDiscord.py: `{discord.__version__}`", inline=True)
        embed.add_field(name="Estadísticas", value=f"Servidores: `{len(self.bot.guilds)}`\nLatencia: `{round(self.bot.latency * 1000)}ms`", inline=True)
        embed.add_field(name="Tiempo Activo", value=f"```\n{uptime_str}\n```", inline=False)
        
        await interaction.response.send_message(embed=embed)

# --- SETUP OBLIGATORIO ---
async def setup(bot):
    await bot.add_cog(General(bot))