import discord
from discord.ext import commands
import google.generativeai as genai
import os

class GeminiChat(commands.Cog):
    """
    Clase GeminiChat: Maneja la integración con Google Gemini para responder
    a menciones en el chat de Discord utilizando el contexto reciente.
    """

    def __init__(self, bot):
        self.bot = bot
        
        # Configuración de la API Key desde variables de entorno
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            print("ERROR: La variable de entorno GEMINI_API_KEY no está configurada.")
            return

        genai.configure(api_key=api_key)

        # Configuración del modelo con la instrucción de sistema requerida.
        # NOTA: Se usa 'gemini-3-flash-preview' según requisitos. 
        # Si este modelo aún no es público, cambiar a 'gemini-1.5-flash' o 'gemini-2.0-flash-exp'.
        self.model = genai.GenerativeModel(
            model_name='gemini-3-flash-preview',
            system_instruction="Eres un asistente inteligente en Discord. Analizas el contexto del chat para dar respuestas coherentes y naturales cuando te mencionan."
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        # Evitar que el bot se responda a sí mismo
        if message.author == self.bot.user:
            return

        # Verificar si el bot ha sido mencionado en el mensaje
        if self.bot.user in message.mentions:
            try:
                # Indicador visual de que el bot está "escribiendo"
                async with message.channel.typing():
                    
                    # Recopilar el historial (últimos 15 mensajes)
                    history_messages = []
                    async for msg in message.channel.history(limit=15):
                        # Formato: [Autor]: [Mensaje]
                        content = f"[{msg.author.display_name}]: {msg.content}"
                        history_messages.append(content)
                    
                    # El historial se obtiene del más nuevo al más antiguo, lo invertimos
                    # para mantener la cronología lógica del chat.
                    history_messages.reverse()
                    
                    # Construcción del bloque de contexto
                    history_text = "\n".join(history_messages)
                    prompt_final = f"Contexto del chat:\n{history_text}\n\nResponde a la última mención:"

                    # Generar respuesta usando Gemini (Thread-safe call)
                    response = await self.bot.loop.run_in_executor(
                        None, 
                        lambda: self.model.generate_content(prompt_final)
                    )

                    # Enviar respuesta al canal mencionando al usuario (reply)
                    await message.reply(response.text)

            except Exception as e:
                print(f"Error al generar respuesta con Gemini: {e}")
                await message.reply("Lo siento, tuve un error procesando tu solicitud.")

async def setup(bot):
    # Función de carga estándar para extensiones en Discord.py
    await bot.add_cog(GeminiChat(bot))