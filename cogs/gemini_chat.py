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

# Configuración de logs básica para ver cuando rota la key
logging.basicConfig(level=logging.INFO)

MEMORY_FILE = "memory.json"

# =========================================================
# GESTOR DE API KEYS (ROTACIÓN)
# =========================================================
class KeyManager:
    def __init__(self):
        # Carga las keys del entorno, ignorando las vacías
        self.keys = [
            k for k in [os.getenv("GOOGLE_API_KEY"), os.getenv("GOOGLE_API_KEY_2")] 
            if k
        ]
        
        if not self.keys:
            logging.critical("[GEMINI] ¡NO SE ENCONTRARON API KEYS EN .ENV!")
            raise ValueError("Faltan GOOGLE_API_KEY o GOOGLE_API_KEY_2 en .env")
        
        self.current_index = 0
        self._configure()

    def _configure(self):
        """Aplica la key actual a la configuración global de Google Generative AI."""
        current_key = self.keys[self.current_index]
        genai.configure(api_key=current_key)
        # Mostramos solo los últimos 4 caracteres por seguridad
        logging.info(f"[GEMINI] Configurada Key #{self.current_index + 1} (***{current_key[-4:]})")

    def rotate(self):
        """Rota a la siguiente key disponible y reconfigura."""
        if len(self.keys) < 2:
            logging.warning("[GEMINI] Se intentó rotar, pero solo hay una key configurada.")
            return

        logging.warning(f"[GEMINI] Quota excedida en Key #{self.current_index + 1}. Rotando...")
        self.current_index = (self.current_index + 1) % len(self.keys)
        self._configure()

# =========================================================
# IA DE INTENCIÓN (DETECTA COMANDOS DE MÚSICA, ETC)
# =========================================================
class IntentAI:
    def __init__(self, model_name, key_manager: KeyManager):
        self.key_manager = key_manager
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
        # Intentamos 2 veces: intento normal -> error -> rotar -> reintento
        for attempt in range(2):
            try:
                chat = self.model.start_chat()
                r = await chat.send_message_async(text)
                return json.loads(r.text)
            except ResourceExhausted:
                if attempt == 0:
                    self.key_manager.rotate()
                    continue # Reintenta el loop
                logging.error("[INTENT] Todas las keys agotadas.")
                return {"intent": "none", "query": None}
            except Exception as e:
                logging.error(f"[INTENT] Error parseando o conectando: {e}")
                return {"intent": "none", "query": None}
        return {"intent": "none", "query": None}

# =========================================================
# IA DE INVOCACIÓN (¿LE HABLAN AL BOT?)
# =========================================================
class CallAI:
    def __init__(self, model_name, bot_name, key_manager: KeyManager):
        self.key_manager = key_manager
        self.bot_name = bot_name.lower()
        self.model_name = model_name
        self._init_model()

    def _init_model(self):
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=(
                f"decidis si un mensaje esta dirigido al bot '{self.bot_name}'.\n"
                "respondes SOLO json: { \"called\": boolean }"
            )
        )

    async def is_called(self, text: str) -> bool:
        for attempt in range(2):
            try:
                chat = self.model.start_chat()
                r = await chat.send_message_async(text)
                return json.loads(r.text).get("called", False)
            except ResourceExhausted:
                if attempt == 0:
                    self.key_manager.rotate()
                    continue
                return False
            except Exception:
                return False
        return False

# =========================================================
# COG PRINCIPAL
# =========================================================
class GeminiChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # 1. Inicializar Gestor de Keys
        self.key_manager = KeyManager()
        
        # 2. Configuración del Modelo
        # Usamos flash por velocidad y costo. Cambia a "gemini-pro" si prefieres calidad.
        self.MODEL_NAME = "gemini-1.5-flash" 

        # 3. Estado en Memoria Volátil
        self.chats = {}           # Objetos ChatSession activos por canal
        self.histories = {}       # Historial serializable (deque) por canal
        self.last_bot_reply = {}  # Timestamp última respuesta
        
        # 4. Estado Persistente
        self.channel_mood = {}
        self.user_memory = {}
        self.conflict_memory = {} # (Opcional, no usado activamente en este snippet)
        
        # 5. Control de flujo
        self.silenced_until = {}  # Silencio temporal por "calentura"
        self.forced_silence = {}  # Silencio forzado por admin
        self.TIMEOUT = 300
        self.COOLDOWN = 15
        self.BASE_CHANCE = 0.25

        # 6. Instancias Helper (Inyectamos el KeyManager)
        self.intent_ai = IntentAI(self.MODEL_NAME, self.key_manager)
        self.bot_name = "botsi" # Cambia esto por el nombre real de tu bot
        self.call_ai = CallAI(self.MODEL_NAME, self.bot_name, self.key_manager)

        self._load_memory()

    # =====================================================
    # PERSISTENCIA (JSON)
    # =====================================================
    def _load_memory(self):
        if not os.path.exists(MEMORY_FILE):
            return
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.user_memory = data.get("users", {})
                self.channel_mood = data.get("channels", {})
        except Exception as e:
            logging.error(f"Error cargando memoria: {e}")

    def _save_memory(self):
        # Guardado atómico simple
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {"users": self.user_memory, "channels": self.channel_mood},
                    f, ensure_ascii=False, indent=2
                )
        except Exception as e:
            logging.error(f"Error guardando memoria: {e}")

    # =====================================================
    # UTILIDADES DE CONTEXTO
    # =====================================================
    def _hour_modifier(self):
        h = datetime.now().hour
        if 0 <= h <= 6: return 0.1   # Madrugada: Habla poco
        if 7 <= h <= 12: return 0.3  # Mañana: Activo
        if 13 <= h <= 18: return 0.25 # Tarde: Normal
        return 0.15                   # Noche: Tranquilo

    def _looks_like_talking_to_me(self, text):
        # Heurística simple: Preguntas cortas o menciones implícitas
        return "?" in text or len(text.split()) <= 4

    def _is_heated(self, text):
        t = text.lower()
        bad_words = ["callate", "idiota", "estupido", "mierda"]
        return t.count("!") >= 3 or any(w in t for w in bad_words)

    # =====================================================
    # GESTIÓN DE ÁNIMO (MOOD)
    # =====================================================
    def _update_channel_mood(self, cid, text):
        mood = self.channel_mood.setdefault(cid, {"score": 0, "mood": "neutral"})
        
        if "jaja" in text.lower(): 
            mood["score"] += 1
        if self._is_heated(text):
            mood["score"] -= 2

        # Clamp score entre -5 y 5
        mood["score"] = max(-5, min(5, mood["score"]))
        
        if mood["score"] <= -3: mood["mood"] = "tenso"
        elif mood["score"] >= 3: mood["mood"] = "relajado"
        else: mood["mood"] = "neutral"
        
        self._save_memory()

    def _update_user_memory(self, uid, text, talked):
        mem = self.user_memory.setdefault(uid, {
            "score": 0, "mood": "neutral", "conflicts": 0, 
            "talks_to_bot": 0, "last_seen": 0
        })

        if self._is_heated(text):
            mem["score"] -= 2
            mem["conflicts"] += 1
        if "jaja" in text.lower():
            mem["score"] += 1
        if talked:
            mem["talks_to_bot"] += 1

        mem["score"] = max(-5, min(5, mem["score"]))
        
        if mem["score"] <= -3: mem["mood"] = "conflictivo"
        elif mem["score"] >= 3: mem["mood"] = "amigable"
        else: mem["mood"] = "neutral"
        
        mem["last_seen"] = time.time()
        self._save_memory()

    # =====================================================
    # LÓGICA DE CHAT CON RETRY
    # =====================================================
    def _system_prompt(self, cid):
        mood = self.channel_mood.get(cid, {}).get("mood", "neutral")
        base = (
            "Eres un usuario más del chat de Discord. "
            "Responde de forma breve, casual, todo en minúsculas (a menos que grites). "
            "No actúes como un asistente virtual. "
        )
        if mood == "tenso": return base + "El ambiente está tenso, sé conciliador o callado."
        if mood == "relajado": return base + "El ambiente es joda, puedes ser más gracioso o troll."
        return base

    def _get_chat_session(self, cid):
        """Obtiene o crea la sesión. Si no existe, la inicia con el historial."""
        if cid not in self.chats:
            model = genai.GenerativeModel(
                model_name=self.MODEL_NAME,
                system_instruction=self._system_prompt(cid)
            )
            # Recuperamos el historial acumulado
            history = list(self.histories.get(cid, deque()))
            self.chats[cid] = model.start_chat(history=history)
        return self.chats[cid]

    def _reset_chat_session(self, cid):
        """Borra la sesión actual para forzar recreación con la nueva API Key."""
        if cid in self.chats:
            del self.chats[cid]
        # Al llamar a _get_chat_session de nuevo, se creará con la config global nueva

    async def _reply(self, cid, text):
        """Intenta responder manejando la rotación de keys."""
        
        for attempt in range(2):
            chat = self._get_chat_session(cid)
            
            try:
                # Llamada a la API
                res = await chat.send_message_async(text)
                response_text = res.text
                
                # Éxito: Guardamos en historial persistente (deque)
                hist = self.histories.setdefault(cid, deque(maxlen=12))
                hist.append({"role": "user", "parts": [text]})
                hist.append({"role": "model", "parts": [response_text]})
                
                self.last_bot_reply[cid] = time.time()
                return response_text

            except ResourceExhausted:
                # Fallo por cuota
                if attempt == 0:
                    logging.warning(f"[CHAT] Quota agotada (Canal {cid}). Rotando Key y reintentando...")
                    self.key_manager.rotate()
                    self._reset_chat_session(cid) # CRÍTICO: Nueva sesión con nueva key
                    continue
                else:
                    logging.error(f"[CHAT] Se agotaron TODAS las keys para el canal {cid}.")
                    return None # Devuelve None para indicar que no pudo responder

            except Exception as e:
                logging.error(f"[CHAT] Error desconocido: {e}")
                return None

        return None

    # =====================================================
    # MANEJO DE INTENCIONES (MÚSICA)
    # =====================================================
    async def _handle_intent(self, intent, message):
        music = self.bot.get_cog("MusicCog")
        if not music:
            # Si no hay bot de música, ignoramos o respondemos error si quieres
            return

        i = intent["intent"]
        q = intent.get("query")

        if i == "play_music" and q:
            await message.channel.send(f"dale, busco `{q}`")
            await music.play_query(message, q) # Asumiendo que MusicCog tiene este método
        elif i == "skip_music":
            await music.skip(message)
        elif i == "stop_music":
            await music.stop(message)
        elif i == "join_voice":
            await music.join(message)
        elif i == "leave_voice":
            await music.leave(message)

    # =====================================================
    # EVENT LISTENER (MAIN LOOP)
    # =====================================================
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        cid = str(message.channel.id)
        clean = message.content.strip()
        now = time.time()

        if not clean: return

        # 1. Chequeo de Silencio Forzado (Admin)
        if cid in self.forced_silence:
            until = self.forced_silence[cid]
            if until is not None and now < until:
                return # Sigue silenciado
            if until is not None and now >= until:
                del self.forced_silence[cid] # Expiró el silencio

        # 2. Análisis Básico
        is_mentioned = self.bot.user in message.mentions
        looks_like_talking = self._looks_like_talking_to_me(clean)
        talked_directly = is_mentioned or looks_like_talking

        # 3. Actualizar Memorias
        self._update_channel_mood(cid, clean)
        self._update_user_memory(str(message.author.id), clean, talked_directly)

        # 4. Chequeo de Silencio por "Calentura" (Auto-moderación)
        if self._is_heated(clean):
            self.silenced_until[cid] = now + 1800 # 30 mins de silencio
            return

        if cid in self.silenced_until:
            if now < self.silenced_until[cid]:
                return
            else:
                del self.silenced_until[cid] # Ya pasó el tiempo

        # 5. Detección de Intenciones (Solo si parece comando o mención)
        # Para ahorrar tokens, no pasamos todo por IntentAI, solo si hay indicios
        # O bien, pasamos todo si tienes suficientes tokens. Aquí lo paso siempre para mejor UX.
        intent = await self.intent_ai.detect(clean)
        if intent["intent"] != "none":
            await self._handle_intent(intent, message)
            self.last_bot_reply[cid] = now
            return

        # 6. Decidir si responder (Chat)
        should_reply = False
        
        if is_mentioned:
            should_reply = True
        else:
            # Lógica probabilística para intervenir naturalmente
            last = self.last_bot_reply.get(cid, 0)
            if now - last > self.COOLDOWN:
                chance = self.BASE_CHANCE * self._hour_modifier()
                # Aumenta chance si el mood es relajado
                mood = self.channel_mood.get(cid, {}).get("mood", "neutral")
                if mood == "relajado": chance *= 1.5
                
                if random.random() < chance:
                    should_reply = True

        if should_reply:
            async with message.channel.typing():
                reply_text = await self._reply(cid, clean)
                if reply_text:
                    await message.channel.send(reply_text)

    # =====================================================
    # COMANDOS DE ADMINISTRACIÓN
    # =====================================================
    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def silencio(self, ctx, minutos: int = 0):
        """Calla al bot en este canal. 0 = indefinido."""
        cid = str(ctx.channel.id)
        if minutos <= 0:
            self.forced_silence[cid] = None # Indefinido
            await ctx.send("shh, me callo indefinidamente.")
        else:
            self.forced_silence[cid] = time.time() + (minutos * 60)
            await ctx.send(f"ok, me callo por {minutos} minutos.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def habla(self, ctx):
        """Permite al bot hablar de nuevo."""
        cid = str(ctx.channel.id)
        self.forced_silence.pop(cid, None)
        self.silenced_until.pop(cid, None) # Resetea también el silencio por mood
        await ctx.send("ya volví.")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def perfil(self, ctx, user: discord.Member):
        """Muestra qué piensa el bot de un usuario."""
        mem = self.user_memory.get(str(user.id))
        if not mem:
            await ctx.send("ni idea de quién es ese.")
            return
        
        embed = discord.Embed(title=f"Perfil de {user.display_name}", color=discord.Color.blue())
        embed.add_field(name="Mood", value=mem['mood'], inline=True)
        embed.add_field(name="Score", value=str(mem['score']), inline=True)
        embed.add_field(name="Conflictos", value=str(mem['conflicts']), inline=True)
        embed.add_field(name="Interacciones", value=str(mem['talks_to_bot']), inline=True)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(GeminiChat(bot))