import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv

# Carga variables desde .env (Solo funciona en local, en el host ya están en el sistema)
load_dotenv()

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=".",
            intents=discord.Intents.all(), # O ajusta según necesites
            help_command=None
        )

    async def setup_hook(self):
        # Carga extensiones de la carpeta cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                extension_name = f'cogs.{filename[:-3]}'
                try:
                    await self.load_extension(extension_name)
                except Exception as e:
                    print(f'❌ Error cargando {extension_name}: {e}')

        await self.tree.sync()
        print("🌲 Slash commands sincronizados")

    async def on_ready(self):
        print(f'✅ Logueado como {self.user}')

async def main():
    bot = Bot()
    async with bot:
        await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass