import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import data_manager
import i18n

async def is_authorized_punish(interaction: discord.Interaction) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if interaction.guild_id and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
        allowed = data_manager.get_allowed_roles(str(interaction.guild_id), "punish")
        if set(allowed) & set([str(r.id) for r in interaction.user.roles]):
            return True
    return False

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="punish", description="Restricts a member from using the bot on this server")
    @app_commands.describe(
        member="Member to restrict",
        duration_hours="Optional: Duration in hours (leave empty for permanent)",
        reason="Reason for the restriction"
    )
    @app_commands.check(is_authorized_punish)
    async def punish(self, interaction: discord.Interaction, member: discord.Member, duration_hours: int = None, reason: str = "No reason provided"):
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return

        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        g_lang = i18n.get_guild_lang(interaction.guild_id)

        if member.id in data_manager.DEVELOPER_IDS:
            await interaction.response.send_message(i18n.t(u_lang, "punish_err_dev"), ephemeral=True)
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message(i18n.t(u_lang, "punish_err_self"), ephemeral=True)
            return

        unban_time = None
        if duration_hours and duration_hours > 0:
            unban_time = datetime.now() + timedelta(hours=duration_hours)
            time_str = unban_time.strftime('%d.%m.%Y %H:%M')
        else:
            time_str = "Permanent"

        if data_manager.blacklist_guild_user(interaction.guild_id, member.id, unban_time, reason):
            embed = discord.Embed(
                title=i18n.t(g_lang, "punish_title"),
                description=i18n.t(g_lang, "punish_desc", mention=member.mention, bot_name=data_manager.BOT_NAME),
                color=discord.Color.red()
            )
            embed.add_field(name=i18n.t(g_lang, "punish_dur"), value=time_str, inline=True)
            embed.add_field(name=i18n.t(g_lang, "punish_reason"), value=reason, inline=True)
            embed.set_footer(text=i18n.t(g_lang, "punish_footer", admin=interaction.user.display_name))
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(i18n.t(u_lang, "db_error"), ephemeral=True)

    @app_commands.command(name="pardon", description="Lifts a member's bot restriction on this server")
    @app_commands.describe(member="Member to unban")
    @app_commands.check(is_authorized_punish)
    async def pardon(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return

        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        g_lang = i18n.get_guild_lang(interaction.guild_id)

        status = data_manager.get_guild_blacklist_status(interaction.guild_id, member.id)
        if not status["is_blacklisted"]:
            await interaction.response.send_message(i18n.t(u_lang, "pardon_not_banned", name=member.display_name), ephemeral=True)
            return

        if data_manager.unblacklist_guild_user(interaction.guild_id, member.id):
            embed = discord.Embed(
                title=i18n.t(g_lang, "pardon_title"),
                description=i18n.t(g_lang, "pardon_desc", mention=member.mention, bot_name=data_manager.BOT_NAME),
                color=discord.Color.green()
            )
            embed.set_footer(text=i18n.t(g_lang, "punish_footer", admin=interaction.user.display_name))
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(i18n.t(u_lang, "db_error"), ephemeral=True)

    @punish.error
    @pardon.error
    async def error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
