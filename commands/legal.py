import discord
from discord import app_commands
from discord.ext import commands
import os
import data_manager
import i18n
from commands.profile import SelfPrivacyView

class Legal(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="legal", description="Shows Terms of Service, Privacy Policy & GDPR self-service tools")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def legal(self, interaction: discord.Interaction):
        lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        tos_link = os.getenv("TOS_URL", "https://example.com/tos")
        privacy_link = os.getenv("PRIVACY_URL", "https://example.com/privacy")
        contact = os.getenv("SUPPORT_CONTACT", "@_nonamehd_")

        embed = discord.Embed(
            title=i18n.t(lang, "legal_title", bot_name=data_manager.BOT_NAME),
            description=i18n.t(lang, "legal_desc"),
            color=discord.Color.blue()
        )
        embed.add_field(name="📜 Terms of Service (ToS)", value=f"[Open Document]({tos_link})", inline=True)
        embed.add_field(name="🔒 Privacy Policy", value=f"[Open Document]({privacy_link})", inline=True)
        embed.add_field(name="📬 Contact / Data Controller", value=contact, inline=False)

        await interaction.response.send_message(embed=embed, view=SelfPrivacyView(lang), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Legal(bot))
