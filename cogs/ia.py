import discord
from discord.ext import commands
import ollama
import asyncio
from datetime import datetime

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = "glm-4.7-flash"
        # Diccionario para guardar el historial: {channel_id: [mensajes]}
        self.history = {}

    def get_user_context(self, message):
        """Crea un pequeño encabezado para que la IA sepa quién habla."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"[Usuario: {message.author.display_name} | Hora: {timestamp}]"

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignorar si es un bot o no mencionan al bot
        if message.author.bot:
            return
        
        if self.bot.user.mentioned_in(message) and not message.mention_everyone:
            # Limpiar la mención del texto para que no ensucie el prompt
            prompt = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
            
            if not prompt:
                await message.reply("¿Me llamaste? Dime algo y charlamos.")
                return

            async with message.channel.typing():
                channel_id = message.channel.id
                
                # Inicializar historial si no existe
                if channel_id not in self.history:
                    self.history[channel_id] = [
                        {"role": "system", "content": "Eres un asistente inteligente llamado KKs-Bot. Hablas con diferentes usuarios y debes recordar quién te habla según el contexto proporcionado en cada mensaje."}
                    ]

                # Añadir contexto de usuario y hora al prompt
                full_prompt = f"{self.get_user_context(message)}: {prompt}"
                
                # Añadir mensaje del usuario al historial
                self.history[channel_id].append({"role": "user", "content": full_prompt})

                # Mantener solo los últimos 15 mensajes para ahorrar RAM
                if len(self.history[channel_id]) > 15:
                    self.history[channel_id] = [self.history[channel_id][0]] + self.history[channel_id][-14:]

                try:
                    # Llamada asíncrona a Ollama
                    response = await asyncio.to_thread(
                        ollama.chat,
                        model=self.model,
                        messages=self.history[channel_id]
                    )

                    reply_text = response['message']['content']
                    
                    # Añadir respuesta de la IA al historial
                    self.history[channel_id].append({"role": "assistant", "content": reply_text})

                    # Manejo de límite de caracteres de Discord
                    if len(reply_text) > 2000:
                        await message.reply(f"La respuesta es muy larga:\n{reply_text[:1900]}...")
                    else:
                        await message.reply(reply_text)

                except Exception as e:
                    await message.reply(f"❌ Error con Ollama ({self.model}): {str(e)}")

async def setup(bot):
    await bot.add_cog(AIChat(bot))