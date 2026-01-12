import discord
from discord.ext import commands
import google.generativeai as genai
import os
import datetime
import asyncio

# Configuración inicial de la API de Google Gemini
# Asegúrate de tener la variable de entorno cargada antes de iniciar el bot.
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Diccionario de Estado (Persistencia en Memoria)
        # Clave: ID del canal (int)
        # Valor: Timestamp del último mensaje (datetime)
        self.active_channels = {}
        
        # Configuración del Timeout (5 minutos)
        self.timeout_delta = datetime.timedelta(minutes=5)

        # Configuración del Modelo
        # Usamos system_instruction para definir la personalidad
        system_instruction = (
            "Eres un participante más en la conversación. Hablas de forma natural, "
            "fluida y coherente con el contexto de la mesa. IMPORTANTE: Actúa como "
            "un participante más en la mesa, no como un asistente formal. "
            "No uses saludos robóticos ni te ofrezcas a ayudar a menos que encaje en la charla."
        )
        
        self.model = genai.GenerativeModel(
            model_name='gemini-3-flash-preview', # Modelo solicitado
            system_instruction=system_instruction
        )

    def _check_timeout(self, channel_id):
        """
        Lógica de Timeout:
        Verifica si ha pasado más tiempo del permitido desde el último mensaje.
        Si es así, elimina el canal de la lista activa.
        Retorna True si el canal sigue activo, False si expiró.
        """
        if channel_id not in self.active_channels:
            return False
            
        last_active = self.active_channels[channel_id]
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Si la diferencia entre AHORA y la ÚLTIMA VEZ es mayor al TIMEOUT
        if (now - last_active) > self.timeout_delta:
            del self.active_channels[channel_id] # Eliminar del estado activo
            return False
            
        return True

    async def _generate_reply(self, message, history_messages):
        """Genera la respuesta usando el historial como contexto."""
        chat_context = ""
        
        # Construcción del contexto basada en el historial
        for msg in history_messages:
            author_name = msg.author.display_name
            content = msg.clean_content
            chat_context += f"{author_name}: {content}\n"
            
        # Añadir el mensaje actual si no está en el historial aún (depende de latencia)
        if history_messages and history_messages[-1].id != message.id:
             chat_context += f"{message.author.display_name}: {message.clean_content}\n"

        try:
            # Enviamos el contexto crudo para que el modelo entienda el flujo
            response = await self.model.generate_content_async(chat_context)
            return response.text
        except Exception as e:
            print(f"Error en Gemini API: {e}")
            return None

    @commands.Cog.listener()
    async def on_message(self, message):
        # 1. Ignorar mensajes del propio bot o de otros bots
        if message.author.bot:
            return

        channel_id = message.channel.id
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Verificar si el bot fue mencionado directamente
        is_mentioned = self.bot.user in message.mentions

        # Verificar estado del canal (si estaba activo previamente)
        is_active_channel = self._check_timeout(channel_id)

        # Lógica de Activación y Participación
        should_reply = False

        if is_mentioned:
            # Si lo mencionan, se activa o reactiva el canal inmediatamente
            self.active_channels[channel_id] = now
            should_reply = True
        elif is_active_channel:
            # Si el canal está activo y no ha expirado, responde a CUALQUIER mensaje
            # Actualizamos el timestamp para mantener la conversación viva
            self.active_channels[channel_id] = now
            should_reply = True

        if should_reply:
            async with message.channel.typing():
                # Lógica de Contexto: Obtener los últimos 15 mensajes
                # history devuelve del más nuevo al más viejo, por lo que usamos reversed
                history = [msg async for msg in message.channel.history(limit=15, before=datetime.datetime.now())]
                history_reversed = list(reversed(history))

                response_text = await self._generate_reply(message, history_reversed)

                if response_text:
                    # Discord tiene un límite de 2000 caracteres, cortamos si es necesario
                    if len(response_text) > 2000:
                        response_text = response_text[:1997] + "..."
                    
                    await message.reply(response_text, mention_author=False)

async def setup(bot):
    await bot.add_cog(GeminiChat(bot))