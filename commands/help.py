import discord
from discord import app_commands
from discord.ext import commands
import os
import data_manager
import i18n

class HelpSelect(discord.ui.Select):
    def __init__(self, lang: str):
        self.lang = lang
        options = [
            discord.SelectOption(label="Trainings & Guests", value="training", emoji="🏃"),
            discord.SelectOption(label="Tournaments & Travel", value="tournament", emoji="🏆"),
            discord.SelectOption(label="Elections & Voting", value="voting", emoji="🗳️"),
            discord.SelectOption(label="Profile, Privacy & Reminders", value="profile", emoji="👤"),
            discord.SelectOption(label="Statistics & Laserforce", value="stats", emoji="📊"),
            discord.SelectOption(label="Server Admin & Setup", value="admin", emoji="⚙️")
        ]
        super().__init__(placeholder=i18n.t(lang, "help_ph"), min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        contact = os.getenv("SUPPORT_CONTACT", "@_nonamehd_")
        embed = discord.Embed(color=discord.Color.blue())

        if self.values[0] == "training":
            embed.title = "🏃 Trainings & Guests"
            embed.add_field(name="`/training`", value="Opens the **Training Dashboard** to create, edit, or cancel trainings and manage participants.\n*Permission:* `training`", inline=False)
            embed.add_field(name="`/send_training_guest_panel`", value="Posts an interactive application button for visiting players to request the Guest role.\n*Permission:* Server Admin", inline=False)

        elif self.values[0] == "tournament":
            embed.title = "🏆 Tournaments & Travel Logistics"
            embed.add_field(name="`/tournament`", value="Opens the **Tournament Center** (single events, date ranges, multi-day league series, manual participant manager).\n*Permission:* `tournament` / `tournament_participants`", inline=False)
            embed.add_field(name="Right-Click Message ➔ `Import as Tournament`", value="Parses any tournament announcement message into a ready-to-use tournament channel.\n*Permission:* `tournament`", inline=False)
            embed.add_field(name="`/orga_dashboard`, `/hotel_add`, `/hotel_list`, `/hotel_remove`", value="Manage the server's hotel catalog, assign rooms, and auto-generate carpools.\n*Permission:* `orgateam`", inline=False)

        elif self.values[0] == "voting":
            embed.title = "🗳️ Secret Elections & Polls"
            embed.add_field(name="`/captainwahl`", value="Starts a weighted, SHA-256 anonymized Captain Election using the server's custom FOR/AGAINST limits.\n*Permission:* `captain_election`", inline=False)
            embed.add_field(name="`/aufnahme` & `/votekick`", value="Starts an anonymous admission or exclusion ballot using the server's configured majority % and quorum.\n*Permission:* `team_decisions`", inline=False)
            embed.add_field(name="`/vote`", value="Creates a public or anonymous multi-option poll with live progress bars.\n*Permission:* `vote`", inline=False)

        elif self.values[0] == "profile":
            embed.title = "👤 Profile, GDPR & Reminders"
            embed.add_field(name="`/profile`", value="Manage captain eligibility, absences (auto-decline for new events), driver's license, room preferences & default passengers.", inline=False)
            embed.add_field(name="`/privacy` & `/legal`", value="View ToS/Privacy Policy and self-service **GDPR Data Export (Art. 15)** or **Complete Data Erasure (Art. 17)** — works in DMs too!", inline=False)
            embed.add_field(name="`/reminder_create`, `_list`, `_edit`, `_delete`", value="Schedule personal DM reminders.", inline=False)

        elif self.values[0] == "stats":
            embed.title = "📊 Statistics & Laserforce"
            embed.add_field(name="`/statistik`", value="Attendance rankings for trainings & tournaments, optional Google Sheet history, and server Laserforce directory.\n*Permission:* `statistics` (`statistics_details` for detailed breakdown)", inline=False)
            embed.add_field(name="`/lf_set`", value="Links a server member to their iPlayLaserforce tag.\n*Permission:* `statistics`", inline=False)

        elif self.values[0] == "admin":
            embed.title = "⚙️ Server Configuration & Moderation"
            embed.add_field(name="`/setup_config`", value="Interactive dashboard for **Language (`en`/`de`/`cs`/`it`)**, **Roles**, **Channels**, **Voting Quorums**, **Deadlines**, **Car Seats** & **Google Sheet**.\n*Permission:* Server Admin", inline=False)
            embed.add_field(name="`/setup` & `/setup_list`", value="Assign or inspect role permissions for individual bot features.\n*Permission:* Server Admin", inline=False)
            embed.add_field(name="`/log` & `/log_level`", value="Configure command, interaction, server audit, and error logging.\n*Permission:* Server Admin", inline=False)
            embed.add_field(name="`/punish` & `/pardon`", value="Restrict or restore a user's access to the bot on this server.\n*Permission:* `punish`", inline=False)

        embed.set_footer(text=f"{data_manager.BOT_NAME} • Support: {contact}")
        await interaction.response.edit_message(embed=embed, view=self.view)

class HelpView(discord.ui.View):
    def __init__(self, lang: str):
        super().__init__(timeout=180)
        self.add_item(HelpSelect(lang))

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Shows an overview of all commands, features, and permissions")
    async def help_cmd(self, interaction: discord.Interaction):
        lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        contact = os.getenv("SUPPORT_CONTACT", "@_nonamehd_")
        embed = discord.Embed(
            title=i18n.t(lang, "help_title", bot_name=data_manager.BOT_NAME),
            description=i18n.t(lang, "help_desc", contact=contact),
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=HelpView(lang), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Help(bot))
