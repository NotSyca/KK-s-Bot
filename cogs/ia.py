import discord
from discord.ext import commands
import os
import google.generativeai as genai
import asyncio

class GeminiChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        api_key = os.getenv("GEMINI_API_KEY")
        
        if api_key:
            # 1. Configuración de Google
            genai.configure(api_key=api_key)
            
            # 2. Configuración del Modelo
            # Usamos 'gemini-1.5-flash' porque es rápido y barato/gratis.
            self.model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                system_instruction=(
                    "Eres un bot de Discord sarcástico pero útil. "
                    "Te llamas 'Bot'. "
                    "Tus respuestas deben ser cortas (máximo 400 caracteres) y directas. "
                    "Si te piden poner música, diles que usen el comando /play. "
                    "No uses emojis excesivos."
                )
            )
            print("✅ IA Gemini conectada y lista.")
        else:
            self.model = None
            print("⚠️ Falta GEMINI_API_KEY. El módulo IA no funcionará.")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignorar bots y mensajes propios
        if message.author.bot or not self.model:
            return

        # Detectar mención (@Bot) o respuesta a un mensaje del bot
        is_mentioned = self.bot.user in message.mentions
        is_reply = (message.reference and message.reference.resolved and 
                    message.reference.resolved.author == self.bot.user)

        if is_mentioned or is_reply:
            async with message.channel.typing():
                try:
                    # --- RECOPILACIÓN DE CONTEXTO ---
                    # Obtenemos los últimos 15 mensajes para que entienda el hilo
                    history = [msg async for msg in message.channel.history(limit=15)]
                    history.reverse() # Ordenar cronológicamente

                    # Construimos el "script" del chat
                    chat_log = "Historial del chat reciente:\n"
                    for msg in history:
                        # Limpieza básica del nombre
                        author_name = msg.author.display_name.replace(":", "")
                        content = msg.clean_content
                        
                        # Si el mensaje tiene imagen, lo indicamos (Gemini texto no ve imágenes sin procesar)
                        if msg.attachments:
                            content += " [El usuario envió una imagen]"
                        
                        chat_log += f"{author_name}: {content}\n"

                    chat_log += "\nInstrucción: Responde al último mensaje como el Bot."

                    # --- LLAMADA A LA API (ASÍNCRONA) ---
                    # generate_content_async es vital para no congelar el bot
                    response = await self.model.generate_content_async(chat_log)
                    
                    reply_text = response.text

                    # --- ENVÍO DE RESPUESTA ---
                    if len(reply_text) > 2000:
                        # Cortar si es demasiado largo (Discord limit)
                        reply_text = reply_text[:1990] + "..."
                    
                    await message.reply(reply_text)

                except Exception as e:
                    print(f"❌ Error Gemini: {e}")
                    await message.reply("Me he mareado. Intenta preguntarme de nuevo.")

async def setup(bot):
    await bot.add_cog(GeminiChat(bot))