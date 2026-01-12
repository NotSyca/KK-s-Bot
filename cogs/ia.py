import discord
from discord.ext import commands
import os
from google import genai
from google.genai import types

class GeminiChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            self.client = None
            print("⚠️ GEMINI_API_KEY no encontrada.")
            return

        self.client = genai.Client(api_key=api_key)
        print("✅ Gemini IA inicializada correctamente.")

        # Modelo estable para bots
        self.model_name = "gemini-1.5-flash-latest"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not self.client:
            return

        is_mentioned = self.bot.user in message.mentions
        is_reply = (
            message.reference
            and message.reference.resolved
            and message.reference.resolved.author == self.bot.user
        )

        if not (is_mentioned or is_reply):
            return

        async with message.channel.typing():
            try:
                # ===== HISTORIAL =====
                history = [msg async for msg in message.channel.history(limit=8)]
                history.reverse()

                chat_log = []
                for msg in history:
                    name = msg.author.display_name.replace(":", "")
                    content = msg.clean_content
                    chat_log.append(f"{name}: {content}")

                prompt = (
                    "Eres un bot sarcástico, directo y breve.\n"
                    "No seas ofensivo.\n\n"
                    + "\n".join(chat_log)
                )

                # ===== GEMINI =====
                response = await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        max_output_tokens=300,
                        temperature=0.8
                    )
                )

                if response.text:
                    await message.reply(response.text[:1999])
                else:
                    await message.reply("🤔 La IA respondió vacío. Clásico.")

            except Exception as e:
                err = str(e)
                print(f"❌ Error Gemini: {err}")

                if "404" in err:
                    await message.reply("❌ Modelo no disponible. Google hizo de las suyas.")
                elif "429" in err:
                    await message.reply("⏳ Rate limit. Respira 5 segundos.")
                else:
                    await message.reply("🔥 Error interno de IA.")

async def setup(bot):
    await bot.add_cog(GeminiChat(bot))
