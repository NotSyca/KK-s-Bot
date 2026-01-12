import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
import logging

logger = logging.getLogger("bot")

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("✅ Cog Welcome (Imágenes) listo.")

    def generate_welcome_image(self, member: discord.Member):
        """Genera una imagen de bienvenida en memoria."""
        # 1. Crear lienzo base (Fondo gris oscuro profesional)
        # Puedes cambiar el color RGB: (30, 30, 30)
        W, H = 800, 300
        background = Image.new('RGB', (W, H), color=(40, 44, 52))
        draw = ImageDraw.Draw(background)

        # 2. Descargar avatar del usuario
        avatar_bytes = io.BytesIO()
        # Síncrono para Pillow (bloquea un poco, pero es rápido)
        # En producción masiva se haría en un executor, para personal está bien así.
        import requests
        response = requests.get(member.display_avatar.url)
        avatar_image = Image.open(io.BytesIO(response.content)).convert("RGBA")
        
        # 3. Redimensionar y hacer circular el avatar
        size = (200, 200)
        avatar_image = avatar_image.resize(size, Image.Resampling.LANCZOS)
        
        mask = Image.new("L", size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0) + size, fill=255)
        
        circular_avatar = ImageOps.fit(avatar_image, mask.size, centering=(0.5, 0.5))
        circular_avatar.putalpha(mask)

        # 4. Pegar avatar en el fondo
        background.paste(circular_avatar, (50, 50), circular_avatar)

        # 5. Añadir Texto
        # Si tienes una fuente .ttf, úsala aquí. Usaremos la default por defecto.
        try:
            # Intenta usar Arial si está en el sistema Linux, si no, default
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except:
            font_title = ImageFont.load_default()
            font_small = ImageFont.load_default()

        draw.text((300, 80), "BIENVENIDO", fill="white", font=font_title)
        draw.text((300, 160), str(member.name), fill=(114, 137, 218), font=font_small)

        # 6. Guardar en memoria (BytesIO)
        buffer = io.BytesIO()
        background.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Buscar canal de bienvenida
        guild = member.guild
        channel = guild.system_channel # Canal predeterminado de Discord
        
        if not channel:
            # Si no hay canal de sistema, intenta buscar uno llamado "bienvenida" o "general"
            channel = discord.utils.get(guild.text_channels, name="bienvenida")
            if not channel:
                channel = discord.utils.get(guild.text_channels, name="general")

        if channel:
            try:
                # Generar imagen (esto corre en otro hilo para no congelar el bot)
                buffer = await self.bot.loop.run_in_executor(None, self.generate_welcome_image, member)
                file = discord.File(fp=buffer, filename="welcome.png")
                
                await channel.send(f"Hola {member.mention}, bienvenido a **{guild.name}**!", file=file)
                logger.info(f"Bienvenida enviada para {member.name}")
            except Exception as e:
                logger.error(f"Error generando imagen de bienvenida: {e}")

    # Comando para probar la bienvenida sin salir y entrar
    @app_commands.command(name="testwelcome", description="Simula una bienvenida (Admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def testwelcome(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            buffer = await self.bot.loop.run_in_executor(None, self.generate_welcome_image, interaction.user)
            file = discord.File(fp=buffer, filename="test.png")
            await interaction.followup.send(file=file)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")

async def setup(bot):
    await bot.add_cog(Welcome(bot))