import discord
from discord.ext import commands
import os
import time
import random
import json
from collections import deque
from datetime import datetime
import logging
import traceback

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, GoogleAPICallError

# =========================================================
# CONFIGURACIÓN DE LOGS
# =========================================================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("GeminiBot")

MEMORY_FILE = "memory.json"

# =========================================================
# GESTOR DE KEYS
# =========================================================
class KeyManager:
    def __init__(self):
        # AÑADE AQUÍ TODAS LAS KEYS QUE TENGAS
        raw_keys = [
            os.getenv("GOOGLE_API_KEY"), 
            os.getenv("GOOGLE_API_KEY_2"), 
            os.getenv("GOOGLE_API_KEY_3")
        ]
        self.keys = [k for k in raw_keys if k]
        
        if not self.keys:
            logger.critical("❌ CRITICAL: No se encontraron API Keys en .env")
        else:
            logger.info(f"✅ KeyManager cargado con {len(self.keys)} llaves.")
        
        self.current_index = 0
        if self.keys:
            self._configure()

    def _configure(self):
        key = self.keys[self.current_index]
        genai.configure(api_key=key)
        logger.info(f"🔑 [CONFIG] Key activa: Índice {self.current_index} (***{key[-4:]})")

    def rotate(self):
        if not self.keys: return
        logger.warning(f"🔄 [ROTACION] Cambiando de Key {self.current_index} a la siguiente...")
        self.current_index = (self.current_index + 1) % len(self.keys)
        self._configure()

    async def find_working_key(self, model_name):
        if not self.keys: return False
        logger.info("🔎 [STARTUP] Buscando una API Key funcional...")
        
        for _ in range(len(self.keys)):
            try:
                model = genai.GenerativeModel(model_name)
                await model.generate_content_async("ping")
                logger.info(f"✅ [STARTUP] La Key #{self.current_index} está operativa.")
                return True
            except ResourceExhausted:
                self.rotate()
            except Exception as e:
                self.rotate()

        logger.critical("⛔ [STARTUP] TODAS LAS KEYS ESTÁN AGOTADAS O ROTAS.")
        return False

# =========================================================
# IA DE INTENCIÓN
# =========================================================
class IntentAI:
    def __init__(self, model_name):
        self.model_name = model_name 
        self._init_model()

    def _init_model(self):
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=(
                "detectas intenciones en mensajes de discord.\n"
                "respondes SOLO json valido.\n"
                "ignora nombres de usuario al principio del mensaje (ej 'Juan: pon musica').\n"
                "intenciones: play_music (query), skip_music, stop_music, join_voice, leave_voice, none\n"
                "formato: { \"intent\": \"none\", \"query\": null }"
            )
        )

    async def detect(self, text: str) -> dict:
        # Generación rápida sin historial
        r = await self.model.generate_content_async(text)
        clean = r.text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean)
        except:
            return {"intent": "none", "query": None}

# =========================================================
# COG PRINCIPAL
# =========================================================
class GeminiChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.key_manager = KeyManager()
        self.MODEL_NAME = "gemini-3-flash-preview"

        self.chats = {}
        self.histories = {}
        self.last_bot_reply = {}
        self.channel_mood = {}
        self.user_memory = {}
        
        self.silenced_until = {}
        self.forced_silence = {}
        self.api_blocked_until = 0

        self.TIMEOUT = 300
        self.COOLDOWN = 15
        self.BASE_CHANCE = 0.25

        self.intent_ai = IntentAI(self.MODEL_NAME)
        self._load_memory()
        
    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("🤖 GeminiChat Cog listo. Verificando estado de APIs...")
        working = await self.key_manager.find_working_key(self.MODEL_NAME)
        if not working:
            self.api_blocked_until = time.time() + 60

    # ... (MÉTODOS DE MEMORIA SIN CAMBIOS) ...
    def _load_memory(self):
        if not os.path.exists(MEMORY_FILE): return
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.user_memory = data.get("users", {})
                self.channel_mood = data.get("channels", {})
        except: pass

    def _save_memory(self):
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({"users": self.user_memory, "channels": self.channel_mood}, f, indent=2)
        except: pass

    def _is_heated(self, text):
        return text.count("!") >= 3 or any(w in text.lower() for w in ["callate", "idiota"])

    def _update_channel_mood(self, cid, text):
        mood = self.channel_mood.setdefault(cid, {"score": 0, "mood": "neutral"})
        if "jaja" in text: mood["score"] += 1
        if self._is_heated(text): mood["score"] -= 2
        mood["score"] = max(-5, min(5, mood["score"]))
        self._save_memory()

    def _update_user_memory(self, uid, text, talked):
        mem = self.user_memory.setdefault(uid, {"score": 0, "mood": "neutral", "conflicts": 0, "talks_to_bot": 0})
        if self._is_heated(text): mem["score"] -= 2; mem["conflicts"] += 1
        if talked: mem["talks_to_bot"] += 1
        self._save_memory()

    def _needs_intent_check(self, text):
        keywords = ["pon", "play", "skip", "siguiente", "para", "stop", "entra", "join", "sal", "leave", "musica"]
        return any(k in text.lower() for k in keywords)

    # =====================================================
    # EJECUCIÓN DE COMANDOS
    # =====================================================
    async def _handle_intent(self, intent, message):
        music_cog = self.bot.get_cog("MusicCog") # Asegúrate que coincida con tu bot
        if not music_cog: return

        i = intent["intent"]
        q = intent.get("query")
        
        try:
            if i == "play_music":
                if q:
                    await message.channel.send(f"va, pongo `{q}`")
                    if hasattr(music_cog, "play_query"): await music_cog.play_query(message, q)
                else:
                    await message.channel.send("que pongo?")

            elif i == "skip_music":
                if hasattr(music_cog, "skip"): await music_cog.skip(message)

            elif i == "stop_music":
                if hasattr(music_cog, "stop"): await music_cog.stop(message)

            elif i == "join_voice":
                if hasattr(music_cog, "join"): await music_cog.join(message)
            
            elif i == "leave_voice":
                if hasattr(music_cog, "leave"): await music_cog.leave(message)

        except Exception as e:
            logger.error(f"Error action: {e}")
            await message.channel.send("error ejecutando acción")

    # =====================================================
    # DETECCIÓN INTENCIÓN (ARREGLO LOOP)
    # =====================================================
    async def _handle_intent_safe(self, message, clean):
        # FIX 1: Usamos len(keys) para intentar todas las llaves disponibles
        total_keys = len(self.key_manager.keys)
        
        for attempt in range(total_keys):
            try:
                intent = await self.intent_ai.detect(clean)
                if intent["intent"] != "none":
                    await self._handle_intent(intent, message)
                    return True 
                return False 
            except ResourceExhausted:
                # Si es el último intento y falló, activamos circuit breaker
                if attempt == total_keys - 1:
                    logger.error("⛔ [INTENT] Todas las keys agotadas. Block 60s.")
                    self.api_blocked_until = time.time() + 60
                    return False
                else:
                    logger.warning(f"⚠️ [INTENT] Key {self.key_manager.current_index} agotada. Rotando.")
                    self.key_manager.rotate()
            except Exception: return False
        return False

    # =====================================================
    # CHAT LÓGICA (ARREGLO IDENTIDAD)
    # =====================================================
    def _get_chat_session(self, cid):
        if cid not in self.chats:
            # FIX 2: Instrucción de sistema para entender formato "Usuario: mensaje"
            system_prompt = (
                "Eres un participante más en un chat grupal de Discord.\n"
                "Los mensajes te llegarán en formato 'NombreUsuario: Mensaje'.\n"
                "Responde al mensaje, dirigiéndote a la persona correcta si es necesario.\n"
                "Tu personalidad: casual, breve, minúsculas, gracioso."
            )
            model = genai.GenerativeModel(model_name=self.MODEL_NAME, system_instruction=system_prompt)
            history = list(self.histories.get(cid, deque()))
            self.chats[cid] = model.start_chat(history=history)
        return self.chats[cid]

    async def _attempt_chat_reply(self, cid, text, username):
        chat = self._get_chat_session(cid)
        
        # FIX 2: Inyectamos el nombre del usuario en el prompt
        prompt_with_identity = f"{username}: {text}"
        
        logger.info(f"💬 [CHAT] Enviando: {prompt_with_identity}")
        response = await chat.send_message_async(prompt_with_identity)
        
        hist = self.histories.setdefault(cid, deque(maxlen=10))
        # Guardamos el historial CON el nombre para que tenga contexto futuro
        hist.append({"role": "user", "parts": [prompt_with_identity]})
        hist.append({"role": "model", "parts": [response.text]})
        
        return response.text

    # =====================================================
    # MAIN LISTENER
    # =====================================================
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        if time.time() < self.api_blocked_until: return

        cid = str(message.channel.id)
        clean = message.content.strip()
        username = message.author.display_name # Nombre legible del usuario
        now = time.time()
        
        if not clean: return

        self._update_channel_mood(cid, clean)
        self._update_user_memory(str(message.author.id), clean, False)

        # 1. Intent Check
        if self._needs_intent_check(clean):
            if await self._handle_intent_safe(message, clean):
                self.last_bot_reply[cid] = now
                return 

        # 2. Chat Check
        is_mentioned = self.bot.user in message.mentions
        should_reply = is_mentioned or (
            now - self.last_bot_reply.get(cid, 0) > self.COOLDOWN and 
            random.random() < self.BASE_CHANCE
        )

        if should_reply:
            async with message.channel.typing():
                reply_text = None
                total_keys = len(self.key_manager.keys)

                # FIX 1: Bucle dinámico según cantidad de keys
                for attempt in range(total_keys):
                    try:
                        # Pasamos el username aquí
                        reply_text = await self._attempt_chat_reply(cid, clean, username)
                        break
                    except ResourceExhausted:
                        if attempt == total_keys - 1:
                            logger.error("⛔ [CHAT] Todas las keys muertas.")
                            self.api_blocked_until = time.time() + 60
                            reply_text = "estoy frito..."
                        else:
                            logger.warning("⚠️ [CHAT] Key agotada. Rotando.")
                            self.key_manager.rotate()
                            if cid in self.chats: del self.chats[cid]
                    except Exception as e:
                        logger.error(f"❌ [CHAT-ERROR] {e}")
                        break

                if reply_text:
                    self.last_bot_reply[cid] = now
                    await message.channel.send(reply_text)

async def setup(bot):
    await bot.add_cog(GeminiChat(bot))