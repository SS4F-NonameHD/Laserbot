import discord
from discord import app_commands
from discord.ext import commands
import datetime
import traceback
import data_manager
import i18n

DEV_ONLY_LOG_LEVELS = ('server', 'error', 'full', 'console', 'trace')

class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def log_to_guild(self, guild, log_type, title, description, color=discord.Color.light_grey(), fields=None):
        if not guild:
            return
        settings = data_manager.get_log_settings(guild.id)
        if not settings:
            return

        channel_id, level = settings
        level = level.lower()
        if level == 'none':
            return

        should_log = False
        if level == 'trace':
            should_log = True
        elif level == 'full' and log_type in ('commands', 'server', 'interactions', 'error'):
            should_log = True
        elif level == 'bot' and log_type in ('commands', 'interactions'):
            should_log = True
        elif level == 'console' and log_type == 'console':
            should_log = True
        elif level == log_type:
            should_log = True

        if not should_log:
            return
        try:
            channel = guild.get_channel(int(channel_id))
            if not channel:
                return
            embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now())
            embed.set_footer(text=f"Log-Type: {log_type.upper()}")
            if fields:
                for n, v in fields:
                    embed.add_field(name=n, value=v, inline=False)
            await channel.send(embed=embed)
        except Exception as e:
            print(f"Logging Failed: {e}")

    async def log_error(self, guild: discord.Guild, source: str, error_message: str):
        """Sendet einen abgefangenen Fehler-Log auf dem eigenständigen 'error'-Level."""
        safe_error = str(error_message)[:4000]
        description = f"**Source:** {source}\n\n**Error:**\n```py\n{safe_error}\n```"
        await self.log_to_guild(guild, "error", "🚨 SYSTEM ERROR", description, discord.Color.brand_red(), None)

    @app_commands.command(name="log", description="Sets the channel for bot & command logs")
    async def log_setup(self, i: discord.Interaction, channel: discord.TextChannel):
        if not i.guild:
            await i.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return
        if not (i.user.guild_permissions.administrator or i.user.id in data_manager.DEVELOPER_IDS):
            await i.response.send_message(i18n.t(i, "no_permission"), ephemeral=True)
            return
        curr = data_manager.get_log_settings(i.guild.id)
        lvl = curr[1] if curr else "none"
        data_manager.set_log_settings(i.guild.id, channel.id, lvl)
        await i.response.send_message(f"✅ Log channel set to {channel.mention} (Current level: `{lvl}`).", ephemeral=True)

    @app_commands.command(name="log_level", description="Configures the detail level for the server log channel")
    @app_commands.choices(level=[
        app_commands.Choice(name="❌ None (Off)", value="none"),
        app_commands.Choice(name="🤖 Bot (Commands + Interactions)", value="bot"),
        app_commands.Choice(name="Commands only", value="commands"),
        app_commands.Choice(name="Interactions only", value="interactions"),
        app_commands.Choice(name="[Dev] Server Audit", value="server"),
        app_commands.Choice(name="[Dev] 🚨 Error (Caught Errors)", value="error"),
        app_commands.Choice(name="[Dev] Full (Cmds + Inter. + Server + Error)", value="full"),
        app_commands.Choice(name="[Dev] Console (Uncaught Tracebacks)", value="console"),
        app_commands.Choice(name="[Dev] Trace (Debug)", value="trace")
    ])
    async def log_level(self, i: discord.Interaction, level: app_commands.Choice[str]):
        if not i.guild:
            await i.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return
        if level.value in DEV_ONLY_LOG_LEVELS and i.user.id not in data_manager.DEVELOPER_IDS:
            await i.response.send_message("⛔ The selected log level (`server`, `error`, `full`, `console`, `trace`) is restricted to Bot Developers.", ephemeral=True)
            return
        if not (i.user.guild_permissions.administrator or i.user.id in data_manager.DEVELOPER_IDS):
            await i.response.send_message(i18n.t(i, "no_permission"), ephemeral=True)
            return

        curr = data_manager.get_log_settings(i.guild.id)
        if not curr:
            await i.response.send_message("⚠️ Please configure a log channel via `/log` first.", ephemeral=True)
            return

        data_manager.set_log_settings(i.guild.id, curr[0], level.value)
        await i.response.send_message(f"✅ Log level set to: **{level.name}**", ephemeral=True)

    @commands.Cog.listener()
    async def on_app_command_completion(self, i: discord.Interaction, cmd):
        if not i.guild:
            return
        ch_mention = i.channel.mention if hasattr(i.channel, "mention") else "Channel"
        txt = f"User: {i.user.mention}\nChannel: {ch_mention}"
        p = []
        try:
            for k, v in i.namespace.__dict__.items():
                p.append(f"{k}: {v}")
        except:
            pass
        await self.log_to_guild(i.guild, "commands", f"▶️ /{cmd.name}", txt, discord.Color.blue(), [("Params", "\n".join(p) if p else "-")])

    @commands.Cog.listener()
    async def on_interaction(self, i: discord.Interaction):
        if not i.guild or i.type == discord.InteractionType.application_command:
            return
        settings = data_manager.get_log_settings(i.guild.id)
        if settings and settings[1] == 'trace':
            await self.log_to_guild(i.guild, "trace", "🔍 Trace", f"Type: {i.type}\nID: {i.data.get('custom_id', '?')}", discord.Color.dark_grey())
            return
        if i.type == discord.InteractionType.component:
            await self.log_to_guild(i.guild, "interactions", "🖱️ Interaction", f"User: {i.user.mention}\nID: `{i.data.get('custom_id', '?')}`", discord.Color.orange())

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, e: discord.AuditLogEntry):
        f = []
        if hasattr(e, 'changes'):
            c_str = ""
            try:
                for c in e.changes:
                    c_str += f"{c.attribute}: {c.before} -> {c.after}\n"
            except:
                pass
            if c_str:
                f.append(("Changes", c_str[:1000]))

        try:
            target_info = str(e.target)
        except Exception:
            target_info = "Unknown (None)"

        user_m = e.user.mention if e.user else "Unknown"
        await self.log_to_guild(e.guild, "server", "🛡️ Server Audit", f"User: {user_m}\nAction: {e.action.name}\nTarget: {target_info}", discord.Color.purple(), f)

    @commands.Cog.listener()
    async def on_app_command_error(self, i: discord.Interaction, e):
        if not i.guild:
            return
        tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))[:1000]
        await self.log_to_guild(i.guild, "console", "⚠️ Unhandled Error", f"Cmd: {i.command.name if i.command else '?'}\nErr: {e}", discord.Color.red(), [("Trace", f"```py\n{tb}```")])

async def setup(bot):
    await bot.add_cog(Logging(bot))
