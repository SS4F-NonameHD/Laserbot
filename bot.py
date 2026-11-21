import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from command_translator import LaserbotCommandTranslator

load_dotenv()

BOT_NAME = os.getenv('BOT_NAME', 'Laserbot')

class Laserbot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.all(),
            help_command=None
        )

    async def setup_hook(self):
        # Aktiviert die mehrsprachige Übersetzung aller Slash- & Kontext-Befehle (EN, DE, CS, IT)
        await self.tree.set_translator(LaserbotCommandTranslator())

        if os.path.exists('./commands'):
            for filename in sorted(os.listdir('./commands')):
                if filename.endswith('.py'):
                    await self.load_extension(f'commands.{filename[:-3]}')
                    print(f'Loaded extension: {filename}')

        await self.tree.sync()
        print("Slash commands & localizations synchronized.")

    async def on_ready(self):
        activity_name = os.getenv('BOT_ACTIVITY', 'Lasertag | /help')
        await self.change_presence(activity=discord.Game(name=activity_name))
        print(f'Logged in as {self.user} ({BOT_NAME})!')

bot = Laserbot()

token = os.getenv('DISCORD_TOKEN')
if token:
    bot.run(token)
else:
    print("Please check DISCORD_TOKEN in .env!")
