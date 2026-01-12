import discord
from discord.ext import commands
import os
import time
import random
import json
from collections import deque
from datetime import datetime

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

MEMORY_FILE = "memory.json"


# =========================================================
# IA DE INTENCIÓN (NO HABLA)
# =========================================================
class IntentAI:
    def __init__(self, model_name):
        self.model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=(
                "detectas intenciones en mensajes de discord.\n"
                "respondes SOLO json valido.\n\n"
                "intenciones:\n"
                "- play_music (query)\n"
                "- skip_music\n"
                "- stop_music\n"
                "- join_voice\n"
                "- leave_voice\n"
                "- none\n\n"
                "formato:\n"
                "{ \"intent\": \"none\", \"query\": null }"
            )
        )

    async def detect(self, text: str) -> dict:
        try:
            chat = self.model.start_chat()
            r = await chat.send_message_async(text)
            return json.loads(r.text)
        except:
            return {"intent": "none", "query": None}


# =========================================================
# COG PRINCIPAL
# =========================================================
class GeminiChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        self.MODEL_NAME = "gemini-3-flash-preview"

        # estado
        self.chats = {}
        self.histories = {}
        self.last_bot_reply = {}
        self.active_sessions = {}

        self.channel_mood = {}
        self.user_memory = {}
        self.conflict_memory = {}
        self.silenced_until = {}
        self.forced_silence = {}

        self.TIMEOUT = 300
        self.COOLDOWN = 15
        self.BASE_CHANCE = 0.25

        self.intent_ai = IntentAI(self.MODEL_NAME)

        self._load_memory()

    # =====================================================
    # MEMORIA
    # =====================================================
    def _load_memory(self):
        if not os.path.exists(MEMORY_FILE):
            return
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.user_memory = data.get("users", {})
                self.channel_mood = data.get("channels", {})
        except:
            print("memoria dañada, se ignora")

    def _save_memory(self):
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"users": self.user_memory, "channels": self.channel_mood},
                f,
                ensure_ascii=False,
                indent=2
            )

    # =====================================================
    # UTILIDADES SOCIALES
    # =====================================================
    def _hour_modifier(self):
        h = datetime.now().hour
        if 0 <= h <= 6:
            return 0.1
        if 7 <= h <= 12:
            return 0.3
        if 13 <= h <= 18:
            return 0.25
        return 0.15

    def _looks_like_talking_to_me(self, text):
        t = text.lower()
        return "?" in t or len(t.split()) <= 4

    def _is_heated(self, text):
        t = text.lower()
        return t.count("!") >= 3 or any(w in t for w in ["callate", "idiota", "nunca", "siempre"])

    # =====================================================
    # MOOD Y USUARIOS
    # =====================================================
    def _update_channel_mood(self, cid, text):
        mood = self.channel_mood.setdefault(cid, {"score": 0, "mood": "neutral"})
        if "jaja" in text:
            mood["score"] += 1
        if any(w in text for w in ["callate", "idiota"]):
            mood["score"] -= 2

        mood["score"] = max(-5, min(5, mood["score"]))
        mood["mood"] = (
            "tenso" if mood["score"] <= -3 else
            "relajado" if mood["score"] >= 3 else
            "neutral"
        )
        self._save_memory()

    def _update_user_memory(self, uid, text, talked):
        mem = self.user_memory.setdefault(uid, {
            "score": 0,
            "mood": "neutral",
            "conflicts": 0,
            "talks_to_bot": 0,
            "last_seen": 0
        })

        if any(w in text for w in ["callate", "idiota"]):
            mem["score"] -= 2
            mem["conflicts"] += 1
        if "jaja" in text:
            mem["score"] += 1
        if talked:
            mem["talks_to_bot"] += 1

        mem["score"] = max(-5, min(5, mem["score"]))
        mem["mood"] = (
            "conflictivo" if mem["score"] <= -3 else
            "calmado" if mem["score"] >= 3 else
            "neutral"
        )
        mem["last_seen"] = time.time()
        self._save_memory()

    # =====================================================
    # CHAT
    # =====================================================
    def _system_prompt(self, cid):
        mood = self.channel_mood.get(cid, {}).get("mood", "neutral")
        base = "sos un participante mas del chat. hablas corto, casual, minusculas."
        if mood == "tenso":
            return base + " solo intervenis para calmar."
        if mood == "relajado":
            return base + " estas mas suelto."
        return base

    def _get_chat(self, cid):
        if cid not in self.chats:
            model = genai.GenerativeModel(
                model_name=self.MODEL_NAME,
                system_instruction=self._system_prompt(cid)
            )
            self.chats[cid] = model.start_chat(
                history=list(self.histories.get(cid, []))
            )
        return self.chats[cid]

    async def _reply(self, cid, text):
        chat = self._get_chat(cid)
        try:
            res = await chat.send_message_async(text)
            hist = self.histories.setdefault(cid, deque(maxlen=12))
            hist.append({"role": "user", "parts": [text]})
            hist.append({"role": "model", "parts": [res.text]})
            self.last_bot_reply[cid] = time.time()
            return res.text
        except ResourceExhausted:
            return "me quede sin energia, despues sigo"

    # =====================================================
    # ACCIONES (MUSIC COG)
    # =====================================================
    async def _handle_intent(self, intent, message):
        music = self.bot.get_cog("MusicCog")
        if not music:
            return

        i = intent["intent"]

        if i == "play_music":
            await message.channel.send("va, pongo algo")
            await music.play_query(message, intent.get("query"))

        elif i == "skip_music":
            await music.skip(message)

        elif i == "stop_music":
            await music.stop(message)

        elif i == "join_voice":
            await music.join(message)

        elif i == "leave_voice":
            await music.leave(message)

    # =====================================================
    # LISTENER
    # =====================================================
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        cid = str(message.channel.id)
        now = time.time()
        clean = message.content.strip()

        if not clean:
            return

        if cid in self.forced_silence:
            until = self.forced_silence[cid]
            if until is None or now < until:
                return
            del self.forced_silence[cid]

        is_mentioned = self.bot.user in message.mentions
        talked = is_mentioned or self._looks_like_talking_to_me(clean)

        self._update_channel_mood(cid, clean)
        self._update_user_memory(str(message.author.id), clean, talked)

        if self._is_heated(clean):
            self.silenced_until[cid] = now + 3600
            return

        if cid in self.silenced_until and now < self.silenced_until[cid]:
            return

        # --------- INTENCIÓN ----------
        intent = await self.intent_ai.detect(clean)
        if intent["intent"] != "none":
            await self._handle_intent(intent, message)
            self.last_bot_reply[cid] = now
            return

        # --------- DECIDIR SI HABLA ----------
        if not is_mentioned:
            last = self.last_bot_reply.get(cid, 0)
            if now - last < self.COOLDOWN:
                return

            chance = self.BASE_CHANCE * self._hour_modifier()
            if random.random() > chance:
                return

        async with message.channel.typing():
            reply = await self._reply(cid, clean)
            await message.channel.send(reply)

    # =====================================================
    # COMANDOS MOD
    # =====================================================
    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def silencio(self, ctx, minutos: int = 0):
        cid = str(ctx.channel.id)
        self.forced_silence[cid] = None if minutos <= 0 else time.time() + minutos * 60
        await ctx.send("ok, me callo")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def habla(self, ctx):
        self.forced_silence.pop(str(ctx.channel.id), None)
        await ctx.send("volvi")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def perfil(self, ctx, user: discord.Member):
        mem = self.user_memory.get(str(user.id))
        if not mem:
            await ctx.send("no hay datos")
            return
        await ctx.send(
            f"mood: {mem['mood']}\n"
            f"conflictos: {mem['conflicts']}\n"
            f"habla con bot: {mem['talks_to_bot']}"
        )


async def setup(bot):
    await bot.add_cog(GeminiChat(bot))
