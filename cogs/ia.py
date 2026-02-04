import discord
from discord.ext import commands
import ollama
import asyncio

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = "llama3.2"
        # Diccionario para guardar la memoria: {user_id: [lista_de_mensajes]}
        self.memory = {}

    def get_user_context(self, user_id, user_name):
        """Inicializa o recupera el contexto del usuario."""
        if user_id not in self.memory:
            # Mensaje de sistema para darle personalidad al bot
            self.memory[user_id] = [
                {'role': 'system', 'content': f'Eres un asistente útil y sarcástico llamado KKs-Bot. Hablas con {user_name}. Recuerda su nombre y sé directo.'}
            ]
        return self.memory[user_id]

    async def process_ai_request(self, user_id, user_name, prompt):
        """Maneja la lógica de Ollama con memoria."""
        context = self.get_user_context(user_id, user_name)
        
        # Añadimos el nuevo mensaje del usuario al contexto
        context.append({'role': 'user', 'content': prompt})

        response = await asyncio.to_thread(
            ollama.chat,
            model=self.model,
            messages=context
        )

        bot_response = response['message']['content']
        
        # Guardamos lo que dijo el bot en su memoria
        context.append({'role': 'assistant', 'content': bot_response})

        # Limitamos la memoria a los últimos 10 mensajes para ahorrar RAM
        if len(context) > 11: # 1 system + 10 chat
            self.memory[user_id] = [context[0]] + context[-10:]

        return bot_response

    @commands.Cog.listener()
    async def on_message(self, message):
        """Escucha menciones directas al bot."""
        # No responder a otros bots ni a mensajes sin mención
        if message.author.bot:
            return

        if self.bot.user.mentioned_in(message):
            # Limpiamos la mención del texto para que no ensucie el prompt
            prompt = message.content.replace(f'<@{self.bot.user.id}>', '').strip()
            
            if not prompt:
                await message.reply("¿Me mencionaste? Dime algo, no leo mentes todavía.")
                return

            async with message.channel.typing():
                try:
                    respuesta = await self.process_ai_request(
                        message.author.id, 
                        message.author.name, 
                        prompt
                    )
                    await message.reply(respuesta)
                except Exception as e:
                    await message.reply(f"❌ Mi cerebro (Ollama) explotó: {str(e)}")

    @commands.command(name="olvida")
    async def olvida(self, ctx):
        """Limpia la memoria del usuario que lo solicita."""
        if ctx.author.id in self.memory:
            del self.memory[ctx.author.id]
            await ctx.send(f"✅ Memoria borrada para {ctx.author.name}. Soy un lienzo en blanco.")

async def setup(bot):
    await bot.add_cog(AIChat(bot))