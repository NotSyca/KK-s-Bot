import discord
from discord.ext import commands
import os
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from collections import deque
import time
import asyncio

class GeminiChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Configuración de Google AI
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("ERROR: GOOGLE_API_KEY no encontrada en variables de entorno.")
        
        genai.configure(api_key=api_key)
        
        # Configuración del Modelo
        self.model_name = 'gemini-3-flash-preview'
        self.system_instruction = (
            "sos un participante mas del chat. hablas normal, sin usar signos de apertura como ¡ o ¿. "
            "escribis de forma corta y casual, como un amigo mas. no sos un asistente. "
            "usa minúsculas casi siempre. si el mensaje es corto, responde corto. "
            "sé sarcástico si la situación lo amerita, pero relajado."
        )
        
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=self.system_instruction
        )

        # Gestión de estado
        # active_sessions: { channel_id: timestamp_ultimo_mensaje }
        self.active_sessions = {} 
        # histories: { channel_id: deque(maxlen=12) } -> Historial de mensajes de chat de Gemini
        self.histories = {}
        
        # Tiempo de espera (5 minutos en segundos)
        self.TIMEOUT_SECONDS = 300 

    def _update_session(self, channel_id):
        """Actualiza el tiempo de la sesión y la mantiene viva."""
        self.active_sessions[channel_id] = time.time()

    def _get_history(self, channel_id):
        """Obtiene o crea el historial para un canal."""
        if channel_id not in self.histories:
            self.histories[channel_id] = deque(maxlen=12) # Historial limitado a 12 turnos
        return self.histories[channel_id]

    async def _generate_response(self, channel_id, user_text):
        """Envía el mensaje a Gemini manteniendo el contexto."""
        history_deque = self._get_history(channel_id)
        
        # Convertimos el deque a lista para la API
        chat_history = list(history_deque)
        
        chat = self.model.start_chat(history=chat_history)
        
        try:
            # Enviamos mensaje de forma asíncrona para no bloquear el bot
            response = await chat.send_message_async(user_text)
            
            # Guardamos el turno en nuestro historial local
            # La API de chat guarda el historial internamente en la sesión 'chat', 
            # pero como recreamos start_chat para persistencia entre reinicios de función,
            # actualizamos nuestro deque manual.
            history_deque.append({"role": "user", "parts": [user_text]})
            history_deque.append({"role": "model", "parts": [response.text]})
            
            return response.text
            
        except ResourceExhausted:
            # Manejo específico del Free Tier
            return "che, me canse de hablar por ahora jaja, denme un toque y vuelvo en un rato"
        except Exception as e:
            print(f"Error en Gemini API: {e}")
            return "uy, se me tildó el cerebro, proba de nuevo."

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignorar mensajes del propio bot
        if message.author == self.bot.user:
            return

        channel_id = message.channel.id
        is_mentioned = self.bot.user in message.mentions
        is_active = False

        # Lógica de activación y expiración
        if channel_id in self.active_sessions:
            last_active = self.active_sessions[channel_id]
            if time.time() - last_active < self.TIMEOUT_SECONDS:
                is_active = True
            else:
                # Expiró la sesión, limpiamos
                del self.active_sessions[channel_id]
                if channel_id in self.histories:
                    del self.histories[channel_id]
        
        # Decidir si responder
        if is_mentioned or is_active:
            # Indicar que está escribiendo (typing)
            async with message.channel.typing():
                # Limpiamos el contenido del mensaje (quitamos la mención para que no la lea la IA)
                clean_content = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
                
                if not clean_content and is_mentioned:
                    clean_content = "hola" # Si solo lo mencionan sin texto

                response_text = await self._generate_response(channel_id, clean_content)
                
                # Actualizar tiempo de sesión
                self._update_session(channel_id)
                
                # Enviar respuesta
                await message.channel.send(response_text)

async def setup(bot):
    await bot.add_cog(GeminiChat(bot))