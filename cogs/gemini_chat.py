import discord
from discord.ext import commands
import os
import time
import random
import json
from collections import deque
from datetime import datetime
import logging
import traceback  # IMPORTANTE: Para ver el error real si explota

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, GoogleAPICallError

# =========================================================
# CONFIGURACIÓN DE LOGS (NIVEL DEBUG)
# =========================================================
# Esto hará que la consola se llene de info útil
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
        raw_keys = [os.getenv("GOOGLE_API_KEY"), os.getenv("GOOGLE_API_KEY_2")]
        self.keys = [k for k in raw_keys if k]
        
        if not self.keys:
            logger.critical("❌ CRITICAL: No se encontraron API Keys en .env")
        else:
            logger.info(f"✅ KeyManager cargado con {len(self.keys)} llaves.")
        
        self.current_index = 0
        # Configuramos la primera por defecto, pero se validará en on_ready
        if self.keys:
            self._configure()

    def _configure(self):
        """Aplica la configuración de la key actual."""
        key = self.keys[self.current_index]
        genai.configure(api_key=key)
        logger.info(f"🔑 [CONFIG] Key activa: Índice {self.current_index} (***{key[-4:]})")

    def rotate(self):
        """Pasa a la siguiente key disponible."""
        if not self.keys: return
        
        logger.warning(f"🔄 [ROTACION] Cambiando de Key {self.current_index} a la siguiente...")
        self.current_index = (self.current_index + 1) % len(self.keys)
        self._configure()

    async def find_working_key(self, model_name):
        """
        Prueba las keys una por una al inicio.
        Se queda con la primera que funcione.
        """
        if not self.keys: return False

        logger.info("🔎 [STARTUP] Buscando una API Key funcional...")
        
        # Probamos tantas veces como keys tengamos
        for _ in range(len(self.keys)):
            try:
                # Prueba ligera: Generar un token
                model = genai.GenerativeModel(model_name)
                # Petición mínima para gastar lo menos posible pero validar estado
                await model.generate_content_async("ping")
                
                logger.info(f"✅ [STARTUP] La Key #{self.current_index} está operativa. Se usará esta.")
                return True
                
            except ResourceExhausted:
                logger.warning(f"⚠️ [STARTUP] Key #{self.current_index} agotada/limitada. Probando siguiente...")
                self.rotate()
            except Exception as e:
                logger.error(f"❌ [STARTUP] Key #{self.current_index} error: {e}. Probando siguiente...")
                self.rotate()

        logger.critical("⛔ [STARTUP] TODAS LAS KEYS ESTÁN AGOTADAS O ROTAS.")
        return False

# =========================================================
# IA DE INTENCIÓN (CON LOGS DE RESPUESTA RAW)
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
                "intenciones: play_music (query), skip_music, stop_music, join_voice, leave_voice, none\n"
                "formato: { \"intent\": \"none\", \"query\": null }"
            )
        )

    async def detect(self, text: str) -> dict:
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
        self.api_blocked_until = 0  # Circuit Breaker

        self.TIMEOUT = 300
        self.COOLDOWN = 15
        self.BASE_CHANCE = 0.25

        self.intent_ai = IntentAI(self.MODEL_NAME)
        self._load_memory()
        
    @commands.Cog.listener()
    async def on_ready(self):
        # Esperamos un poco para no saturar si el bot reconecta rápido
        logger.info("🤖 GeminiChat Cog listo. Verificando estado de APIs...")
        
        working = await self.key_manager.find_working_key(self.MODEL_NAME)
        
        if not working:
            logger.error("💀 [SISTEMA] El bot arranca sin keys funcionales. Se activará Circuit Breaker.")
            self.api_blocked_until = time.time() + 60
        else:
            logger.info("🚀 [SISTEMA] Sistema Gemini inicializado correctamente.")

    # ... (MÉTODOS DE MEMORIA Y UTILIDADES IGUALES) ...
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
        matches = any(k in text.lower() for k in keywords)
        if matches:
            logger.debug(f"🔍 [FILTER] Pasó filtro de intención: '{text}'")
        return matches

    # =====================================================
    # MANEJO DE EJECUCIÓN DE COMANDOS (AQUÍ ES DONDE EXPLOTA)
    # =====================================================
    async def _handle_intent(self, intent, message):
        logger.info("⚙️ [ACTION] Iniciando ejecución de comando...")
        
        # 1. VERIFICAR COG
        # IMPORTANTE: Asegúrate de que tu Music Cog se llama "MusicCog" en el setup del bot
        music_cog = self.bot.get_cog("MusicLocal") 
        
        if not music_cog:
            logger.error("❌ [ACTION-ERROR] No se encontró el Cog 'MusicCog'. ¿Está cargado? ¿Tiene otro nombre?")
            await message.channel.send("no encuentro mis funciones de musica (cog not loaded)")
            return

        i = intent["intent"]
        q = intent.get("query")
        
        logger.info(f"▶️ [ACTION-EXEC] Intent: {i} | Query: {q}")

        # 2. EJECUCIÓN SEGURA
        try:
            if i == "play_music":
                if q:
                    await message.channel.send(f"va, pongo `{q}`")
                    # VERIFICA QUE play_query EXISTA EN TU MUSIC BOT
                    if hasattr(music_cog, "play"):
                        await music_cog.play(message, q)
                    else:
                        logger.error("❌ [METHOD-ERROR] 'MusicCog' no tiene método 'play_query'.")
                        await message.channel.send("error interno: no sé como poner musica (metodo incorrecto)")
                else:
                    await message.channel.send("que pongo? no entendí la canción")

            elif i == "skip_music":
                if hasattr(music_cog, "skip"): await music_cog.skip(message)
                else: logger.error("❌ MusicCog sin metodo skip")

            elif i == "stop_music":
                if hasattr(music_cog, "stop"): await music_cog.stop(message)
                else: logger.error("❌ MusicCog sin metodo stop")

            elif i == "join_voice":
                if hasattr(music_cog, "join"): await music_cog.join(message)
                else: logger.error("❌ MusicCog sin metodo join")

            elif i == "leave_voice":
                if hasattr(music_cog, "leave"): await music_cog.leave(message)
                else: logger.error("❌ MusicCog sin metodo leave")
            
            logger.info("✅ [ACTION-SUCCESS] Comando ejecutado correctamente.")

        except Exception as e:
            # ESTO TE MOSTRARÁ EL ERROR REAL
            logger.error(f"💥 [CRITICAL ERROR] Excepción al ejecutar comando:\n{traceback.format_exc()}")
            await message.channel.send("exploté intentando hacer eso, mira la consola")

    # =====================================================
    # DETECCIÓN SEGURA (CON RETRY Y CIRCUIT BREAKER)
    # =====================================================
    async def _handle_intent_safe(self, message, clean):
        for attempt in range(2):
            try:
                intent = await self.intent_ai.detect(clean)
                
                if intent["intent"] != "none":
                    await self._handle_intent(intent, message)
                    return True 
                
                return False 

            except ResourceExhausted:
                if attempt == 0:
                    logger.warning(f"⚠️ [INTENT-QUOTA] Key #{self.key_manager.current_index} agotada. Rotando...")
                    self.key_manager.rotate()
                    continue 
                else:
                    logger.error("⛔ [INTENT-BLOCK] Ambas keys muertas. Activando Circuit Breaker (60s).")
                    self.api_blocked_until = time.time() + 60
                    return False
            
            except Exception as e:
                logger.error(f"❌ [INTENT-EXCEPTION] {e}")
                return False
        return False

    # =====================================================
    # CHAT LÓGICA
    # =====================================================
    def _get_chat_session(self, cid):
        if cid not in self.chats:
            model = genai.GenerativeModel(model_name=self.MODEL_NAME, system_instruction="habla corto y casual")
            history = list(self.histories.get(cid, deque()))
            self.chats[cid] = model.start_chat(history=history)
        return self.chats[cid]

    async def _attempt_chat_reply(self, cid, text):
        chat = self._get_chat_session(cid)
        logger.info(f"💬 [CHAT] Enviando a Gemini (Key idx {self.key_manager.current_index}): {text}")
        response = await chat.send_message_async(text)
        
        hist = self.histories.setdefault(cid, deque(maxlen=10))
        hist.append({"role": "user", "parts": [text]})
        hist.append({"role": "model", "parts": [response.text]})
        return response.text

    # =====================================================
    # MAIN LISTENER
    # =====================================================
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return

        # Circuit Breaker Check
        if time.time() < self.api_blocked_until:
            return # Silent block

        cid = str(message.channel.id)
        clean = message.content.strip()
        now = time.time()
        
        if not clean: return

        # Updates Memory (Omitido logs para no spamear)
        self._update_channel_mood(cid, clean)
        self._update_user_memory(str(message.author.id), clean, False)

        # 1. INTENT CHECK
        if self._needs_intent_check(clean):
            handled = await self._handle_intent_safe(message, clean)
            if handled:
                self.last_bot_reply[cid] = now
                return 

        # 2. CHAT CHECK
        is_mentioned = self.bot.user in message.mentions
        should_reply = is_mentioned
        
        if not should_reply and (now - self.last_bot_reply.get(cid, 0) > self.COOLDOWN):
            if random.random() < self.BASE_CHANCE:
                should_reply = True

        if should_reply:
            async with message.channel.typing():
                reply_text = None
                for attempt in range(2):
                    try:
                        reply_text = await self._attempt_chat_reply(cid, clean)
                        break
                    except ResourceExhausted:
                        if attempt == 0:
                            logger.warning("⚠️ [CHAT-QUOTA] Key agotada. Rotando y reintentando...")
                            self.key_manager.rotate()
                            if cid in self.chats: del self.chats[cid]
                            continue
                        else:
                            logger.error("⛔ [CHAT-BLOCK] Ambas keys muertas. Circuit Breaker activado.")
                            self.api_blocked_until = time.time() + 60
                            reply_text = "estoy frito..."
                    except Exception as e:
                        logger.error(f"❌ [CHAT-ERROR] {e}")
                        break

                if reply_text:
                    self.last_bot_reply[cid] = now
                    await message.channel.send(reply_text)

async def setup(bot):
    await bot.add_cog(GeminiChat(bot))