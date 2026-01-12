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
            self.client = genai.Client(api_key=api_key)
            print("✅ IA Gemini (SDK Moderno) cargada.")
        else:
            self.client = None
            print("⚠️ Falta GEMINI_API_KEY.")

    @commands.command(name="debug_ai")
    async def debug_ai(self, ctx):
        """Lista los modelos que TU clave puede ver."""
        if not self.client: return await ctx.send("❌ Sin API Key.")
        
        await ctx.send("🔍 Consultando API de Google...")
        try:
            # CORRECCIÓN: Primero hacemos await a la llamada, luego iteramos
            response = await self.client.aio.models.list()
            
            models_found = []
            # La respuesta suele ser iterable directamente en el nuevo SDK
            for model in response:
                # Filtramos solo los que sirven para chatear (generateContent)
                if "generateContent" in (model.supported_generation_methods or []):
                    # Guardamos el nombre limpio (quitando 'models/')
                    name = model.name.split("/")[-1]
                    models_found.append(name)
            
            if models_found:
                lista_txt = ", ".join(models_found[:10]) # Mostramos solo los primeros 10
                await ctx.send(f"✅ **Modelos activos:**\n`{lista_txt}`\n\n*Usa uno de estos en el código si falla el actual.*")
            else:
                await ctx.send("⚠️ La API respondió, pero no encontré modelos compatibles con chat.")

        except Exception as e:
            await ctx.send(f"❌ Error crítico listando modelos: `{e}`")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not self.client: return

        # Lógica de mención
        is_mentioned = self.bot.user in message.mentions
        is_reply = (message.reference and message.reference.resolved and 
                    message.reference.resolved.author == self.bot.user)

        if is_mentioned or is_reply:
            async with message.channel.typing():
                try:
                    # 1. Historial
                    history = [msg async for msg in message.channel.history(limit=10)]
                    history.reverse()

                    chat_log = "Historial:\n"
                    for msg in history:
                        name = msg.author.display_name.replace(":", "")
                        content = msg.clean_content
                        chat_log += f"{name}: {content}\n"
                    
                    chat_log += "\nInstrucción: Eres 'Bot'. Responde corto y sarcástico."

                    # 2. Selección de Modelo
                    # Intentamos usar el modelo más estándar. 
                    # Si debug_ai te da otros nombres, cambia esta línea.
                    model_name = "gemini-1.5-flash"

                    # 3. Generación
                    response = await self.client.aio.models.generate_content(
                        model=model_name,
                        contents=chat_log,
                        config=types.GenerateContentConfig(
                            max_output_tokens=400,
                            temperature=0.8
                        )
                    )
                    
                    if response.text:
                        await message.reply(response.text[:1999])
                    else:
                        await message.reply("🤔 Recibí una respuesta vacía de la IA.")

                except Exception as e:
                    print(f"❌ Error Gemini: {e}")
                    err_msg = str(e)
                    if "404" in err_msg:
                        await message.reply("❌ Error de Modelo: `gemini-1.5-flash` no encontrado. Usa `!debug_ai` para ver el nombre correcto.")
                    elif "429" in err_msg:
                        await message.reply("⏳ Estoy saturado (Rate Limit). Espera un poco.")
                    else:
                        await message.reply("🔥 Error interno de IA.")

async def setup(bot):
    await bot.add_cog(GeminiChat(bot))