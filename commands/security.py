import discord
from discord.ext import commands
from datetime import datetime
import data_manager
import i18n

class Security(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.tree.interaction_check = self.global_interaction_check

    async def global_interaction_check(self, interaction: discord.Interaction) -> bool:
        # Developer dürfen sich nie selbst aussperren
        if interaction.user.id in data_manager.DEVELOPER_IDS:
            return True

        lang = i18n.get_interaction_lang(interaction, prefer_guild=False)

        # 1. Globale Bot-Blacklist prüfen
        g_status = data_manager.get_global_blacklist_status(interaction.user.id)
        if g_status["is_blacklisted"]:
            if g_status["unban_time"] and datetime.now() > g_status["unban_time"]:
                data_manager.unblacklist_global_user(interaction.user.id)
            else:
                msg = i18n.t(lang, "ban_global_title", bot_name=data_manager.BOT_NAME)
                if g_status["unban_time"]:
                    msg += i18n.t(lang, "ban_until", time=g_status["unban_time"].strftime("%d.%m.%Y %H:%M"))
                else:
                    msg += i18n.t(lang, "ban_perm")
                if g_status["reason"]:
                    msg += i18n.t(lang, "ban_reason", reason=g_status["reason"])
                await interaction.response.send_message(msg, ephemeral=True)
                return False

        # 2. Lokale Server-Blacklist prüfen (falls Befehl auf einem Server ausgeführt wird)
        if interaction.guild_id:
            s_status = data_manager.get_guild_blacklist_status(interaction.guild_id, interaction.user.id)
            if s_status["is_blacklisted"]:
                if s_status["unban_time"] and datetime.now() > s_status["unban_time"]:
                    data_manager.unblacklist_guild_user(interaction.guild_id, interaction.user.id)
                else:
                    msg = i18n.t(lang, "ban_guild_title", bot_name=data_manager.BOT_NAME)
                    if s_status["unban_time"]:
                        msg += i18n.t(lang, "ban_until", time=s_status["unban_time"].strftime("%d.%m.%Y %H:%M"))
                    else:
                        msg += i18n.t(lang, "ban_perm")
                    if s_status["reason"]:
                        msg += i18n.t(lang, "ban_reason", reason=s_status["reason"])
                    await interaction.response.send_message(msg, ephemeral=True)
                    return False

        return True

async def setup(bot):
    await bot.add_cog(Security(bot))
