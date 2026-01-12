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
from google.api_core.exceptions import ResourceExhausted

MEMORY_FILE = "memory.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


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
# IA DE INVOCACIÓN (¿LE HABLAN AL BOT?)
# =========================================================
class CallAI:
    def __init__(self, model_name, bot_name):
        self.bot_name = bot_name.lower()
        self.model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=(
                f"decidis si un mensaje esta dirigido al bot llamado '{self.bot_name}'.\n"
                "respondes SOLO json.\n\n"
                "true si:\n"
                "- le hablan directamente\n"
                "- usan su nombre como invocacion natural\n"
                "- hay una pregunta o pedido claro\n\n"
                "false si:\n"
                "- es solo un saludo\n"
                "- hablan de el en tercera persona\n"
                "- charla entre humanos\n\n"
                "formato:\n"
                "{ \"called\": false }"
            )
        )

    async def is_called(self, text: str) -> bool:
        try:
            chat = self.model.start_chat()
            r = await chat.send_message_async(text)
            return json.loads(r.text).get("called", False)
        except:
            return False

# =========================================================
# COG PRINCIPAL
# =========================================================
class GeminiChat:
    def __init__(self, model_name="gemini-3-flash-preview"):
        # ===============================
        # API KEYS
        # ===============================
        self.api_keys = [
            os.getenv("GOOGLE_API_KEY"),
            os.getenv("GOOGLE_API_KEY_2")
        ]
        self.api_keys = [k for k in self.api_keys if k]

        if not self.api_keys:
            raise RuntimeError("No hay API keys de Gemini configuradas")

        self.current_key_index = 0
        self._configure_gemini()

        # ===============================
        # MODELO
        # ===============================
        self.model_name = model_name
        self.model = genai.GenerativeModel(self.model_name)

        # ===============================
        # ESTADO
        # ===============================
        self.chats = {}
        self.histories = {}
        self.last_bot_reply = {}

        logging.info("[GEMINI] GeminiChat inicializado correctamente")

    # ===============================
    # CONFIGURACIÓN API
    # ===============================
    def _configure_gemini(self):
        genai.configure(api_key=self.api_keys[self.current_key_index])
        logging.info(
            f"[GEMINI] usando api key #{self.current_key_index + 1}"
        )

    def _rotate_api_key(self):
        if len(self.api_keys) < 2:
            return False

        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self._configure_gemini()

        # limpiar chats porque quedan ligados a la key anterior
        self.chats.clear()

        logging.warning("[GEMINI] api key agotada, rotando a la siguiente")
        return True

    # ===============================
    # CHAT POR CANAL
    # ===============================
    def _get_chat(self, cid):
        if cid not in self.chats:
            self.chats[cid] = self.model.start_chat(history=[])
        return self.chats[cid]

    # ===============================
    # RESPUESTA
    # ===============================
    async def _reply(self, cid, text):
        chat = self._get_chat(cid)

        try:
            res = await chat.send_message_async(text)

            hist = self.histories.setdefault(cid, deque(maxlen=12))
            hist.append({"role": "user", "parts": [text]})
            hist.append({"role": "model", "parts": [res.text]})

            self.last_bot_reply[cid] = time.time()

            logging.info(
                f"[GEMINI OK] canal={cid} tokens_ok"
            )

            return res.text

        except ResourceExhausted:
            logging.warning(
                f"[GEMINI EXHAUSTED] canal={cid} mensaje='{text[:120]}'"
            )

            rotated = self._rotate_api_key()

            if rotated:
                try:
                    chat = self._get_chat(cid)
                    res = await chat.send_message_async(text)

                    hist = self.histories.setdefault(cid, deque(maxlen=12))
                    hist.append({"role": "user", "parts": [text]})
                    hist.append({"role": "model", "parts": [res.text]})

                    self.last_bot_reply[cid] = time.time()

                    logging.info(
                        "[GEMINI RECOVERED] respuesta enviada tras rotar key"
                    )

                    return res.text

                except ResourceExhausted:
                    logging.error(
                        "[GEMINI DEAD] todas las api keys sin tokens"
                    )

            return "me quede sin energia, despues sigo"

        except Exception as e:
            logging.exception(
                f"[GEMINI ERROR] canal={cid} error inesperado"
            )
            return "algo se rompio, no fui yo, fue la realidad"


async def setup(bot):
    await bot.add_cog(GeminiChat(bot))
