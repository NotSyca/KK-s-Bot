import discord
from discord.ext import commands
import ollama
import asyncio

class IACog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = "llama3.2" # El modelo que descargaste

    @commands.command(name="pregunta")
    async def pregunta(self, ctx, *, prompt: str):
        """Le hace una pregunta a la IA local (Ollama)."""
        async with ctx.typing():
            try:
                # Ejecutamos la llamada a Ollama en un hilo separado para no bloquear el bot
                response = await asyncio.to_thread(
                    ollama.generate, 
                    model=self.model, 
                    prompt=prompt
                )
                
                respuesta_texto = response['response']
                
                # Discord tiene un límite de 2000 caracteres por mensaje
                if len(respuesta_texto) > 2000:
                    # Si es muy larga, la enviamos como archivo o la cortamos
                    with open("respuesta.txt", "w", encoding="utf-8") as f:
                        f.write(respuesta_texto)
                    await ctx.send("La respuesta es muy larga, aquí tienes el archivo:", file=discord.File("respuesta.txt"))
                else:
                    await ctx.send(respuesta_texto)
                    
            except Exception as e:
                await ctx.send(f"❌ Error al conectar con Ollama: {e}")

async def setup(bot):
    await bot.add_cog(IACog(bot))