import discord
from discord.ext import commands
import os
from google import genai
from google.genai import types

class GeminiChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        api_key = os.getenv("GEMINI_API_KEY")
        
        if api_key:
            # Inicializamos cliente
            self.client = genai.Client(api_key=api_key)
            print("✅ IA Gemini (SDK Moderno) cargada.")
        else:
            self.client = None
            print("⚠️ Falta GEMINI_API_KEY.")

    @commands.command(name="debug_ai", hidden=True)
    async def debug_ai(self, ctx):
        """Comando para ver qué modelos están disponibles realmente"""
        if not self.client: return await ctx.send("Sin API Key.")
        
        await ctx.send("🔍 Consultando modelos disponibles en Google...")
        try:
            # Listamos modelos que soporten generación de contenido
            models_list = ""
            async for model in self.client.aio.models.list(config={"page_size": 10}):
                if "generateContent" in model.supported_generation_methods:
                    models_list += f"`{model.name}`\n"
            
            # Cortamos si es muy largo
            if len(models_list) > 1900: models_list = models_list[:1900]
            await ctx.send(f"**Modelos Disponibles:**\n{models_list}")
        except Exception as e:
            await ctx.send(f"❌ Error al listar modelos: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not self.client: return

        # Detectar mención
        if self.bot.user in message.mentions or (message.reference and message.reference.resolved and message.reference.resolved.author == self.bot.user):
            
            async with message.channel.typing():
                try:
                    history = [msg async for msg in message.channel.history(limit=10)]
                    history.reverse()

                    chat_log = "Historial:\n"
                    for msg in history:
                        name = msg.author.display_name.replace(":", "")
                        chat_log += f"{name}: {msg.clean_content}\n"
                    
                    chat_log += "\nInstrucción: Responde como un Bot de Discord útil."

                    # INTENTO 1: Usar la versión estable específica
                    model_to_use = "gemini-1.5-flash" 
                    
                    response = await self.client.aio.models.generate_content(
                        model=model_to_use,
                        contents=chat_log,
                        config=types.GenerateContentConfig(
                            max_output_tokens=500,
                            temperature=0.7
                        )
                    )
                    
                    await message.reply(response.text[:1999])

                except Exception as e:
                    print(f"❌ Error Gemini: {e}")
                    # Si falla el flash, intentamos con el modelo Pro como fallback
                    if "404" in str(e):
                        await message.reply("❌ Error 404: El modelo `gemini-1.5-flash` no responde. Usa `!debug_ai` para ver cuáles funcionan.")
                    else:
                        await message.reply("😵 Me dio un error interno.")

async def setup(bot):
    await bot.add_cog(GeminiChat(bot))