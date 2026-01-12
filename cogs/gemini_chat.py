import discord
from discord.ext import commands
import os
import time
import random
import json
from collections import deque
from datetime import datetime
import logging

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, GoogleAPICallError

# Configuración de logs
logging.basicConfig(level=logging.INFO)

MEMORY_FILE = "memory.json"

# =========================================================
# GESTOR DE KEYS Y CONFIGURACIÓN GLOBAL
# =========================================================
class KeyManager:
    def __init__(self):
        # Carga keys, filtra las vacías o None
        raw_keys = [os.getenv("GOOGLE_API_KEY"), os.getenv("GOOGLE_API_KEY_2")]
        self.keys = [k for k in raw_keys if k]
        
        if not self.keys:
            logging.critical("CRITICAL: No se encontraron API Keys en .env")
            # No lanzamos error para no crashear el bot entero, pero no funcionará la IA
        
        self.current_index = 0
        if self.keys:
            self._configure()

    def _configure(self):
        """Configura la librería con la key actual."""
        key = self.keys[self.current_index]
        genai.configure(api_key=key)
        logging.info(f"[GEMINI] Key activa: Índice {self.current_index} (***{key[-4:]})")

    def rotate(self):
        """Rota a la siguiente key."""
        if not self.keys: return
        self.current_index = (self.current_index + 1) % len(self.keys)
        self._configure()
        logging.warning(f"[GEMINI] Rotación realizada. Nueva key índice {self.current_index}")

# =========================================================
# CLASES AUXILIARES (IA)
# =========================================================
class IntentAI:
    def __init__(self, model_name):
        self.model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=(
                "detectas intenciones en mensajes de discord.\n"
                "respondes SOLO json valido.\n"
                "intenciones: play_music (query), skip_music, stop_music, join_voice, leave_voice, none\n"
                "formato: { \"intent\": \"none\", \"query\": null }"
            )
        )

    async def detect(self, text: str) -> dict:
        # Generación sin historia (más barato/rápido)
        r = await self.model.generate_content_async(text)
        text_clean = r.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text_clean)

# =========================================================
# COG PRINCIPAL
# =========================================================
class GeminiChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.key_manager = KeyManager()
        
        # Usamos flash para velocidad y mayor rate limit
        self.MODEL_NAME = "gemini-1.5-flash"

        # --- ESTADO ---
        self.chats = {}           # Sesiones de chat activas
        self.histories = {}       # Historial persistente
        self.last_bot_reply = {}  # Cooldown
        
        # --- MEMORIA ---
        self.channel_mood = {}
        self.user_memory = {}
        
        # --- SEGURIDAD Y CONTROL ---
        self.silenced_until = {}       # Auto-silencio por "calentura"
        self.forced_silence = {}       # Silencio por admin
        self.api_blocked_until = 0     # CIRCUIT BREAKER (Global)

        # --- CONSTANTES ---
        self.TIMEOUT = 300
        self.COOLDOWN = 15
        self.BASE_CHANCE = 0.25

        # Instancias
        self.intent_ai = IntentAI(self.MODEL_NAME)
        
        self._load_memory()

    # =====================================================
    # PERSISTENCIA Y UTILIDADES
    # =====================================================
    def _load_memory(self):
        if not os.path.exists(MEMORY_FILE): return
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.user_memory = data.get("users", {})
                self.channel_mood = data.get("channels", {})
        except Exception as e:
            logging.error(f"Error cargando memoria: {e}")

    def _save_memory(self):
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({"users": self.user_memory, "channels": self.channel_mood}, f, indent=2)
        except Exception: pass

    def _is_heated(self, text):
        t = text.lower()
        bad_words = ["callate", "idiota", "estupido", "mierda", "basura"]
        return t.count("!") >= 3 or any(w in t for w in bad_words)

    def _needs_intent_check(self, text):
        """Filtro local para ahorrar peticiones a la API."""
        # Solo verificamos intención si hay palabras clave de música
        keywords = ["pon", "play", "skip", "siguiente", "para", "stop", "entra", "join", "sal", "leave", "musica"]
        return any(k in text.lower() for k in keywords)

    # =====================================================
    # LÓGICA DE MEMORIA (MOOD)
    # =====================================================
    def _update_channel_mood(self, cid, text):
        mood = self.channel_mood.setdefault(cid, {"score": 0, "mood": "neutral"})
        if "jaja" in text.lower(): mood["score"] += 1
        if self._is_heated(text): mood["score"] -= 2
        mood["score"] = max(-5, min(5, mood["score"]))
        mood["mood"] = "tenso" if mood["score"] <= -3 else "relajado" if mood["score"] >= 3 else "neutral"
        self._save_memory()

    def _update_user_memory(self, uid, text, talked):
        mem = self.user_memory.setdefault(uid, {"score": 0, "mood": "neutral", "conflicts": 0, "talks_to_bot": 0})
        if self._is_heated(text):
            mem["score"] -= 2
            mem["conflicts"] += 1
        if "jaja" in text.lower(): mem["score"] += 1
        if talked: mem["talks_to_bot"] += 1
        mem["score"] = max(-5, min(5, mem["score"]))
        mem["mood"] = "conflictivo" if mem["score"] <= -3 else "amigable" if mem["score"] >= 3 else "neutral"
        self._save_memory()

    # =====================================================
    # SISTEMA DE CHAT CON RETRY Y CIRCUIT BREAKER
    # =====================================================
    def _get_chat_session(self, cid):
        """Crea o recupera la sesión. Si hubo rotación, se debe resetear antes."""
        if cid not in self.chats:
            mood = self.channel_mood.get(cid, {}).get("mood", "neutral")
            prompt = "eres un usuario de discord. responde corto, casual y en minusculas."
            if mood == "tenso": prompt += " ambiente tenso, calmate."
            if mood == "relajado": prompt += " ambiente de fiesta, se gracioso."

            model = genai.GenerativeModel(model_name=self.MODEL_NAME, system_instruction=prompt)
            history = list(self.histories.get(cid, deque()))
            self.chats[cid] = model.start_chat(history=history)
        return self.chats[cid]

    async def _attempt_chat_reply(self, cid, text):
        """Lógica interna de intento de respuesta."""
        chat = self._get_chat_session(cid)
        response = await chat.send_message_async(text)
        
        # Guardamos historial
        hist = self.histories.setdefault(cid, deque(maxlen=10))
        hist.append({"role": "user", "parts": [text]})
        hist.append({"role": "model", "parts": [response.text]})
        return response.text

    async def _attempt_intent_detect(self, text):
        """Lógica interna de intento de detección."""
        return await self.intent_ai.detect(text)

    # =====================================================
    # EVENTO PRINCIPAL (ON_MESSAGE)
    # =====================================================
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        
        # 1. CIRCUIT BREAKER CHECK
        # Si la API está bloqueada, ignoramos todo para no spamear logs ni quemar CPU
        if time.time() < self.api_blocked_until:
            return

        cid = str(message.channel.id)
        clean = message.content.strip()
        now = time.time()

        if not clean: return

        # 2. CHEQUEO DE SILENCIO ADMIN
        if cid in self.forced_silence:
            until = self.forced_silence[cid]
            if until and now < until: return
            if until and now >= until: del self.forced_silence[cid]

        # 3. ACTUALIZAR MEMORIA
        is_mentioned = self.bot.user in message.mentions
        looks_talking = "?" in clean or len(clean.split()) <= 4
        talked = is_mentioned or looks_talking

        self._update_channel_mood(cid, clean)
        self._update_user_memory(str(message.author.id), clean, talked)

        # 4. CHEQUEO DE AUTO-SILENCIO (CALENTURA)
        if self._is_heated(clean):
            self.silenced_until[cid] = now + 1800 # 30 min
            return
        if cid in self.silenced_until and now < self.silenced_until[cid]:
            return

        # 5. DETECCIÓN DE INTENCIÓN (OPTIMIZADA)
        # Solo gastamos tokens si parece un comando de música
        if self._needs_intent_check(clean):
            try:
                # Intento 1
                intent = await self._attempt_intent_detect(clean)
                if intent["intent"] != "none":
                    await self._handle_intent(intent, message)
                    self.last_bot_reply[cid] = now
                    return # Si fue comando, no charlamos
            except ResourceExhausted:
                # Manejo simple para intent: Si falla, asumimos que no es comando y seguimos
                # Si falla mucho, el chat normal activará el circuit breaker luego
                logging.warning("[INTENT] Falló detección por quota. Ignorando.")

        # 6. DECISIÓN DE HABLAR
        should_reply = False
        if is_mentioned:
            should_reply = True
        elif now - self.last_bot_reply.get(cid, 0) > self.COOLDOWN:
            chance = self.BASE_CHANCE
            if random.random() < chance:
                should_reply = True

        if should_reply:
            async with message.channel.typing():
                reply_text = None
                
                # BUCLE DE REINTENTO (Retry Logic)
                for attempt in range(2):
                    try:
                        reply_text = await self._attempt_chat_reply(cid, clean)
                        break # Éxito, salimos del loop
                    
                    except ResourceExhausted:
                        if attempt == 0:
                            # Primer fallo: Rotamos y reseteamos sesión
                            logging.warning(f"[CHAT] Quota agotada (Key {self.key_manager.current_index}). Rotando...")
                            self.key_manager.rotate()
                            if cid in self.chats: del self.chats[cid] # Forzar recreación
                            continue
                        else:
                            # Segundo fallo: Ambas keys muertas -> CIRCUIT BREAKER
                            logging.error("[CHAT] TODAS LAS KEYS AGOTADAS. Activando Circuit Breaker (60s).")
                            self.api_blocked_until = time.time() + 60
                            reply_text = "estoy mareado, dame un minuto..."
                    
                    except Exception as e:
                        logging.error(f"[CHAT] Error desconocido: {e}")
                        break

                if reply_text:
                    self.last_bot_reply[cid] = now
                    await message.channel.send(reply_text)

    # =====================================================
    # MANEJO DE INTENCIONES
    # =====================================================
    async def _handle_intent(self, intent, message):
        music = self.bot.get_cog("MusicCog")
        if not music: return

        i = intent["intent"]
        q = intent.get("query")
        
        try:
            if i == "play_music" and q:
                await message.channel.send(f"buscando `{q}`...")
                await music.play_query(message, q) # Ajusta según tu MusicCog
            elif i == "skip_music": await music.skip(message)
            elif i == "stop_music": await music.stop(message)
            elif i == "join_voice": await music.join(message)
            elif i == "leave_voice": await music.leave(message)
        except Exception as e:
            await message.channel.send(f"error ejecutando comando: {e}")

    # =====================================================
    # COMANDOS ADMIN
    # =====================================================
    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def silencio(self, ctx, minutos: int = 0):
        cid = str(ctx.channel.id)
        if minutos <= 0:
            self.forced_silence[cid] = None
            await ctx.send("silencio indefinido activado.")
        else:
            self.forced_silence[cid] = time.time() + (minutos * 60)
            await ctx.send(f"silencio por {minutos} mins.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def habla(self, ctx):
        cid = str(ctx.channel.id)
        self.forced_silence.pop(cid, None)
        self.silenced_until.pop(cid, None)
        self.api_blocked_until = 0 # Admin puede resetear el circuit breaker
        await ctx.send("liberado.")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def perfil(self, ctx, user: discord.Member):
        mem = self.user_memory.get(str(user.id), {})
        await ctx.send(f"Stats de {user.display_name}:\n{json.dumps(mem, indent=2)}")

async def setup(bot):
    await bot.add_cog(GeminiChat(bot))