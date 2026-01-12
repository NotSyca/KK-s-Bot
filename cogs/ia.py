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
            # Instanciamos el cliente nuevo
            # http_options={'api_version': 'v1alpha'} a veces es necesario para modelos muy nuevos, 
            # pero para 1.5-flash el cliente default va bien.
            self.client = genai.Client(api_key=api_key)
            print("✅ IA Gemini (Nueva GenAI SDK) conectada.")
        else:
            self.client = None
            print("⚠️ Falta GEMINI_API_KEY.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not self.client:
            return

        # Detectar mención o respuesta
        is_mentioned = self.bot.user in message.mentions
        is_reply = (message.reference and message.reference.resolved and 
                    message.reference.resolved.author == self.bot.user)

        if is_mentioned or is_reply:
            async with message.channel.typing():
                try:
                    # 1. Preparar Historial
                    history = [msg async for msg in message.channel.history(limit=15)]
                    history.reverse()

                    # Convertimos el chat a texto plano para evitar errores de estructura
                    chat_log = "Historial reciente del chat:\n"
                    for msg in history:
                        author = msg.author.display_name.replace(":", "")
                        content = msg.clean_content
                        chat_log += f"{author}: {content}\n"
                    
                    chat_log += "\nInstrucción: Eres 'Bot', un asistente sarcástico de Discord. Responde al último mensaje."

                    # 2. Llamada a la API (ASÍNCRONA con .aio)
                    # Usamos el modelo 'gemini-1.5-flash' que es el estándar rápido actual
                    response = await self.client.aio.models.generate_content(
                        model='gemini-1.5-flash',
                        contents=chat_log,
                        config=types.GenerateContentConfig(
                            max_output_tokens=400,
                            temperature=0.7
                        )
                    )

                    reply_text = response.text

                    # 3. Enviar
                    if len(reply_text) > 2000:
                        reply_text = reply_text[:1990] + "..."
                    
                    await message.reply(reply_text)

                except Exception as e:
                    print(f"❌ Error Gemini: {e}")
                    # Feedback visual si falla
                    await message.add_reaction("⚠️")

async def setup(bot):
    await bot.add_cog(GeminiChat(bot))