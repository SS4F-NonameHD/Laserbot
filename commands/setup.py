import discord
from discord import app_commands, ui
from discord.ext import commands
from datetime import datetime, timedelta
import re
import io
import data_manager
import i18n

def is_developer(interaction: discord.Interaction) -> bool:
    return interaction.user.id in data_manager.DEVELOPER_IDS

def is_setup_authorized(interaction: discord.Interaction) -> bool:
    if is_developer(interaction):
        return True
    if isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
    return False

def build_config_embed(guild: discord.Guild) -> discord.Embed:
    s = data_manager.get_server_settings(guild.id)
    lang = s["language"]
    na = i18n.t(lang, "not_configured")

    def fmt_role(rid):
        if not rid: return f"`{na}`"
        r = guild.get_role(int(rid))
        return r.mention if r else f"`Deleted ({rid})`"

    def fmt_chan(cid):
        if not cid: return f"`{na}`"
        ch = guild.get_channel(int(cid))
        return ch.mention if ch else f"`Deleted ({cid})`"

    embed = discord.Embed(
        title=i18n.t(lang, "setup_title", bot_name=data_manager.BOT_NAME),
        description=i18n.t(lang, "setup_desc"),
        color=discord.Color.blurple()
    )
    embed.add_field(
        name="🌐 Language & Roles",
        value=(
            f"**Language:** {i18n.SUPPORTED_LANGUAGES.get(lang, lang)}\n"
            f"**Team Role:** {fmt_role(s['team_role_id'])}\n"
            f"**Guest Role:** {fmt_role(s['guest_role_id'])} ({s['guest_default_days']}d)\n"
            f"**Observer Role:** {fmt_role(s['observer_role_id'])}"
        ),
        inline=False
    )
    embed.add_field(
        name="📂 Channels & Categories",
        value=(
            f"**Training Channel:** {fmt_chan(s['training_channel_id'])}\n"
            f"**Tournament Category:** {fmt_chan(s['tournament_category_id'])}\n"
            f"**Report Channel:** {fmt_chan(s['report_channel_id'])}"
        ),
        inline=False
    )
    embed.add_field(
        name="🗳️ Voting & Elections",
        value=(
            f"**Captain Election:** max. `+{s['captain_max_for']}` / `-{s['captain_max_against']}` (Default `{s['captain_default_hours']}h`)\n"
            f"**Admission Majority:** `{s['aufnahme_majority']}%` | **Votekick Majority:** `{s['votekick_majority']}%`\n"
            f"**Min. Participation (Quorum):** `{s['decision_quorum']}%` (Default `{s['decision_default_hours']}h`)"
        ),
        inline=False
    )
    sheet_status = "✅ Linked" if s.get("google_sheet_url") else f"`{na}`"
    embed.add_field(
        name="⏱️ Deadlines & Logistics",
        value=(
            f"**Training Deadline:** `{s['training_deadline_hours']}h` before (Reminder: `{s['training_reminder_hours']}h` before DL)\n"
            f"**Tournament Default Deadline:** `{s['tournament_deadline_hours']}h` before\n"
            f"**Auto-Carpool Seats:** `{s['default_car_seats']}` per car | **Google Sheet:** {sheet_status}"
        ),
        inline=False
    )
    return embed

# --- MODALS & SUB-VIEWS FÜR /setup_config ---

class VotingRulesModal(ui.Modal, title="Voting & Election Rules"):
    cap_for = ui.TextInput(label="Captain: Max FOR votes (+1) [1-10]", required=True, max_length=2)
    cap_against = ui.TextInput(label="Captain: Max AGAINST votes (-1) [0-5]", required=True, max_length=2)
    adm_maj = ui.TextInput(label="Admission Majority in % (e.g. 66.67 or 50.1)", required=True, max_length=6)
    kick_maj = ui.TextInput(label="Votekick Majority in % (e.g. 66.67 or 75)", required=True, max_length=6)
    quorum = ui.TextInput(label="Min. Turnout Quorum in % (0 = disabled)", required=True, max_length=6)

    def __init__(self, current_settings, main_msg):
        super().__init__()
        self.main_msg = main_msg
        self.cap_for.default = str(current_settings["captain_max_for"])
        self.cap_against.default = str(current_settings["captain_max_against"])
        self.adm_maj.default = str(current_settings["aufnahme_majority"])
        self.kick_maj.default = str(current_settings["votekick_majority"])
        self.quorum.default = str(current_settings["decision_quorum"])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cf = max(1, min(10, int(self.cap_for.value)))
            ca = max(0, min(5, int(self.cap_against.value)))
            am = max(1.0, min(100.0, float(self.adm_maj.value.replace(',', '.'))))
            km = max(1.0, min(100.0, float(self.kick_maj.value.replace(',', '.'))))
            qu = max(0.0, min(100.0, float(self.quorum.value.replace(',', '.'))))
        except ValueError:
            await interaction.response.send_message("❌ Invalid number format.", ephemeral=True)
            return

        data_manager.update_server_settings(
            interaction.guild_id,
            captain_max_for=cf,
            captain_max_against=ca,
            aufnahme_majority=round(am, 2),
            votekick_majority=round(km, 2),
            decision_quorum=round(qu, 2)
        )
        await interaction.response.send_message(i18n.t(interaction.guild_id, "setup_saved"), ephemeral=True)
        try:
            await self.main_msg.edit(embed=build_config_embed(interaction.guild))
        except: pass

class DeadlinesLogisticsModal(ui.Modal, title="Deadlines, Cars & Sheet"):
    train_dl = ui.TextInput(label="Training Deadline (hours before, e.g. 30.5)", required=True, max_length=6)
    train_rem = ui.TextInput(label="Training Reminder (hours before DL, 0=off)", required=True, max_length=6)
    tourn_dl = ui.TextInput(label="Tournament Default Deadline (hours before)", required=True, max_length=4)
    car_seats = ui.TextInput(label="Default Seats per Car (incl. driver, e.g. 4)", required=True, max_length=2)
    sheet_url = ui.TextInput(label="Google Sheet URL (optional, empty = clear)", required=False, max_length=500)

    def __init__(self, current_settings, main_msg):
        super().__init__()
        self.main_msg = main_msg
        self.train_dl.default = str(current_settings["training_deadline_hours"])
        self.train_rem.default = str(current_settings["training_reminder_hours"])
        self.tourn_dl.default = str(current_settings["tournament_deadline_hours"])
        self.car_seats.default = str(current_settings["default_car_seats"])
        self.sheet_url.default = current_settings.get("google_sheet_url") or ""

    async def on_submit(self, interaction: discord.Interaction):
        try:
            tdl = max(0.0, float(self.train_dl.value.replace(',', '.')))
            trem = max(0.0, float(self.train_rem.value.replace(',', '.')))
            todl = max(0, int(self.tourn_dl.value))
            seats = max(2, min(15, int(self.car_seats.value)))
        except ValueError:
            await interaction.response.send_message("❌ Invalid number format.", ephemeral=True)
            return

        sheet = self.sheet_url.value.strip() or None
        data_manager.update_server_settings(
            interaction.guild_id,
            training_deadline_hours=tdl,
            training_reminder_hours=trem,
            tournament_deadline_hours=todl,
            default_car_seats=seats,
            google_sheet_url=sheet
        )
        await interaction.response.send_message(i18n.t(interaction.guild_id, "setup_saved"), ephemeral=True)
        try:
            await self.main_msg.edit(embed=build_config_embed(interaction.guild))
        except: pass

class LanguageSelectView(ui.View):
    def __init__(self, main_msg):
        super().__init__(timeout=120)
        self.main_msg = main_msg
        opts = [discord.SelectOption(label=lbl, value=code) for code, lbl in i18n.SUPPORTED_LANGUAGES.items()]
        sel = ui.Select(placeholder="Select Server Language...", options=opts)
        sel.callback = self.on_select
        self.add_item(sel)

    async def on_select(self, interaction: discord.Interaction):
        chosen = interaction.data["values"][0]
        data_manager.update_server_settings(interaction.guild_id, language=chosen)
        await interaction.response.edit_message(content=i18n.t(chosen, "setup_saved"), view=None)
        try:
            await self.main_msg.edit(embed=build_config_embed(interaction.guild), view=SetupConfigMainView(interaction.guild_id))
        except: pass

class RolesConfigView(ui.View):
    def __init__(self, main_msg):
        super().__init__(timeout=120)
        self.main_msg = main_msg

    @ui.select(cls=ui.RoleSelect, placeholder="1. Select Main Team Role...", min_values=0, max_values=1, row=0)
    async def sel_team(self, interaction: discord.Interaction, select: ui.RoleSelect):
        rid = str(select.values[0].id) if select.values else None
        data_manager.update_server_settings(interaction.guild_id, team_role_id=rid)
        await interaction.response.send_message(i18n.t(interaction.guild_id, "setup_saved"), ephemeral=True)
        try: await self.main_msg.edit(embed=build_config_embed(interaction.guild))
        except: pass

    @ui.select(cls=ui.RoleSelect, placeholder="2. Select Guest Role...", min_values=0, max_values=1, row=1)
    async def sel_guest(self, interaction: discord.Interaction, select: ui.RoleSelect):
        rid = str(select.values[0].id) if select.values else None
        data_manager.update_server_settings(interaction.guild_id, guest_role_id=rid)
        await interaction.response.send_message(i18n.t(interaction.guild_id, "setup_saved"), ephemeral=True)
        try: await self.main_msg.edit(embed=build_config_embed(interaction.guild))
        except: pass

    @ui.select(cls=ui.RoleSelect, placeholder="3. Select Observer Role (optional)...", min_values=0, max_values=1, row=2)
    async def sel_obs(self, interaction: discord.Interaction, select: ui.RoleSelect):
        rid = str(select.values[0].id) if select.values else None
        data_manager.update_server_settings(interaction.guild_id, observer_role_id=rid)
        await interaction.response.send_message(i18n.t(interaction.guild_id, "setup_saved"), ephemeral=True)
        try: await self.main_msg.edit(embed=build_config_embed(interaction.guild))
        except: pass

class ChannelsConfigView(ui.View):
    def __init__(self, main_msg):
        super().__init__(timeout=120)
        self.main_msg = main_msg

    @ui.select(cls=ui.ChannelSelect, channel_types=[discord.ChannelType.text, discord.ChannelType.news], placeholder="1. Training Announcements Channel...", min_values=0, max_values=1, row=0)
    async def sel_train_ch(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        cid = str(select.values[0].id) if select.values else None
        data_manager.update_server_settings(interaction.guild_id, training_channel_id=cid)
        await interaction.response.send_message(i18n.t(interaction.guild_id, "setup_saved"), ephemeral=True)
        try: await self.main_msg.edit(embed=build_config_embed(interaction.guild))
        except: pass

    @ui.select(cls=ui.ChannelSelect, channel_types=[discord.ChannelType.category], placeholder="2. Tournament Channels Category...", min_values=0, max_values=1, row=1)
    async def sel_tourn_cat(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        cid = str(select.values[0].id) if select.values else None
        data_manager.update_server_settings(interaction.guild_id, tournament_category_id=cid)
        await interaction.response.send_message(i18n.t(interaction.guild_id, "setup_saved"), ephemeral=True)
        try: await self.main_msg.edit(embed=build_config_embed(interaction.guild))
        except: pass

    @ui.select(cls=ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="3. Message Report Target Channel...", min_values=0, max_values=1, row=2)
    async def sel_rep_ch(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        cid = str(select.values[0].id) if select.values else None
        data_manager.update_server_settings(interaction.guild_id, report_channel_id=cid)
        await interaction.response.send_message(i18n.t(interaction.guild_id, "setup_saved"), ephemeral=True)
        try: await self.main_msg.edit(embed=build_config_embed(interaction.guild))
        except: pass

class SetupConfigMainView(ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        lang = i18n.get_guild_lang(guild_id)
        options = [
            discord.SelectOption(label=i18n.t(lang, "setup_opt_lang"), value="lang", emoji="🌐"),
            discord.SelectOption(label=i18n.t(lang, "setup_opt_roles"), value="roles", emoji="👥"),
            discord.SelectOption(label=i18n.t(lang, "setup_opt_channels"), value="channels", emoji="📂"),
            discord.SelectOption(label=i18n.t(lang, "setup_opt_voting"), value="voting", emoji="🗳️"),
            discord.SelectOption(label=i18n.t(lang, "setup_opt_deadlines"), value="deadlines", emoji="⏱️")
        ]
        sel = ui.Select(placeholder=i18n.t(lang, "setup_select_cat"), options=options)
        sel.callback = self.on_cat_select
        self.add_item(sel)

    async def on_cat_select(self, interaction: discord.Interaction):
        val = interaction.data["values"][0]
        settings = data_manager.get_server_settings(interaction.guild_id)
        if val == "lang":
            await interaction.response.send_message("🌐 **Language / Sprache:**", view=LanguageSelectView(interaction.message), ephemeral=True)
        elif val == "roles":
            await interaction.response.send_message("👥 **Select Server Roles:**", view=RolesConfigView(interaction.message), ephemeral=True)
        elif val == "channels":
            await interaction.response.send_message("📂 **Select Channels & Category:**", view=ChannelsConfigView(interaction.message), ephemeral=True)
        elif val == "voting":
            await interaction.response.send_modal(VotingRulesModal(settings, interaction.message))
        elif val == "deadlines":
            await interaction.response.send_modal(DeadlinesLogisticsModal(settings, interaction.message))

# --- HAUPT-COG ---

PERMISSION_CHOICES = [
    app_commands.Choice(name="Training (Create / Edit Dashboard)", value="training"),
    app_commands.Choice(name="Training Participation (Buttons)", value="training_participate"),
    app_commands.Choice(name="Training Delete Notes", value="training_delete_notes"),
    app_commands.Choice(name="Tournament (Create / Edit Base)", value="tournament"),
    app_commands.Choice(name="Tournament (Manage Participants)", value="tournament_participants"),
    app_commands.Choice(name="Orgateam (Hotels & Carpools)", value="orgateam"),
    app_commands.Choice(name="Orga-Ping (Direct Message)", value="orga_ping"),
    app_commands.Choice(name="Captain Election (Start)", value="captain_election"),
    app_commands.Choice(name="Team Decisions (Admission / Votekick)", value="team_decisions"),
    app_commands.Choice(name="General Poll (/vote)", value="vote"),
    app_commands.Choice(name="Statistics (Basic)", value="statistics"),
    app_commands.Choice(name="Statistics (Detailed & Guests)", value="statistics_details"),
    app_commands.Choice(name="Profile (/profile)", value="profile"),
    app_commands.Choice(name="Server Bot Restriction (/punish & /pardon)", value="punish"),
    app_commands.Choice(name="Manage Guests (Approve / Duration)", value="manage_guests")
]

def format_gdpr_report(user_id_str: str, raw_data: dict) -> str:
    output = f"GDPR PERSONAL DATA EXPORT (Art. 15 GDPR)\n"
    output += f"Service: {data_manager.BOT_NAME}\n"
    output += f"Discord User ID: {user_id_str}\n"
    output += f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    output += "=" * 60 + "\n\n"
    output += (
        "Note: Secret ballots (Captain Elections, Team Decisions, Anonymous Polls) use irreversible "
        "one-way SHA-256 hashing with a cryptographic salt and cannot be linked back to an individual user.\n\n"
    )
    has_data = False
    for table_name, rows in raw_data.items():
        if rows:
            has_data = True
            output += f"--- TABLE: {table_name.upper()} ---\n"
            for i, row in enumerate(rows, 1):
                output += f"  [Record {i}]\n"
                for key, val in row.items():
                    output += f"    {key}: {val}\n"
            output += "\n"
    if not has_data:
        output += "No personal data stored for this User ID.\n"
    return output

class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def extract_role_ids(self, text: str):
        mention_ids = re.findall(r'<@&(\d+)>', text)
        raw_ids = re.findall(r'\b(\d{17,20})\b', text)
        return list(set(mention_ids + raw_ids))

    @app_commands.command(name="setup_config", description="Interactive dashboard for server language, roles, channels, quorums & deadlines")
    @app_commands.check(is_setup_authorized)
    async def setup_config(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return
        embed = build_config_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=SetupConfigMainView(interaction.guild_id), ephemeral=True)

    @app_commands.command(name="setup", description="Assign or remove command permissions for server roles")
    @app_commands.describe(befehl="Feature / Command to configure", aktion="Add or Remove", rollen_input="Mention roles (@Role) or paste Role IDs")
    @app_commands.choices(befehl=PERMISSION_CHOICES, aktion=[
        app_commands.Choice(name="Add (Allow)", value="add"),
        app_commands.Choice(name="Remove (Revoke)", value="remove")
    ])
    @app_commands.check(is_setup_authorized)
    async def setup(self, interaction: discord.Interaction, befehl: app_commands.Choice[str], aktion: app_commands.Choice[str], rollen_input: str):
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return
        role_ids = self.extract_role_ids(rollen_input)
        if not role_ids:
            await interaction.response.send_message("❌ No valid roles detected.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        processed = []
        for rid in role_ids:
            role_obj = interaction.guild.get_role(int(rid))
            rname = role_obj.name if role_obj else f"ID {rid}"
            if aktion.value == "add":
                ok = data_manager.add_command_permission(str(interaction.guild_id), befehl.value, rid)
            else:
                ok = data_manager.remove_command_permission(str(interaction.guild_id), befehl.value, rid)
            processed.append(f"{'✅' if ok else '❌'} {rname}")

        await interaction.followup.send(f"**Permissions `{befehl.name}`:**\n" + "\n".join(processed), ephemeral=True)

    @app_commands.command(name="setup_list", description="Displays allowed roles for a specific command category")
    @app_commands.choices(befehl=PERMISSION_CHOICES)
    @app_commands.check(is_setup_authorized)
    async def setup_list(self, interaction: discord.Interaction, befehl: app_commands.Choice[str]):
        if not interaction.guild_id:
            return
        allowed_ids = data_manager.get_allowed_roles(str(interaction.guild_id), befehl.value)
        embed = discord.Embed(title=f"Permissions: {befehl.name}", color=discord.Color.orange())
        if not allowed_ids:
            if befehl.value == "training_participate":
                embed.description = "⚠️ No roles configured ➔ **Everyone** is allowed to participate."
            else:
                embed.description = "⚠️ No roles configured ➔ Only Administrators have access."
        else:
            lines = []
            for rid in allowed_ids:
                role = interaction.guild.get_role(int(rid))
                lines.append(f"• {role.mention}" if role else f"• Deleted Role (`{rid}`)")
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- DEVELOPER REMOTE COMMANDS ---

    @app_commands.command(name="dev_ban", description="[Developer] Global bot ban/unban by User ID")
    @app_commands.choices(action=[
        app_commands.Choice(name="Global Ban", value="ban"),
        app_commands.Choice(name="Global Unban", value="unban")
    ])
    @app_commands.check(is_developer)
    async def dev_ban(self, interaction: discord.Interaction, user_id: str, action: app_commands.Choice[str], hours: int = None, reason: str = "Terms of Service violation"):
        if not user_id.isdigit():
            await interaction.response.send_message("❌ Invalid numeric User ID.", ephemeral=True)
            return
        if int(user_id) in data_manager.DEVELOPER_IDS:
            await interaction.response.send_message("❌ Cannot ban a Developer.", ephemeral=True)
            return

        if action.value == "ban":
            unban_dt = (datetime.now() + timedelta(hours=hours)) if hours else None
            data_manager.blacklist_global_user(user_id, unban_dt, reason)
            await interaction.response.send_message(f"✅ User `{user_id}` globally banned.", ephemeral=True)
        else:
            data_manager.unblacklist_global_user(user_id)
            await interaction.response.send_message(f"✅ Global ban lifted for `{user_id}`.", ephemeral=True)

    @app_commands.command(name="dev_dsgvo", description="[Developer] Cross-server GDPR export or erasure for any User ID")
    @app_commands.choices(action=[
        app_commands.Choice(name="Export Data (Art. 15)", value="export"),
        app_commands.Choice(name="Erase All Data (Art. 17)", value="erase")
    ])
    @app_commands.check(is_developer)
    async def dev_dsgvo(self, interaction: discord.Interaction, user_id: str, action: app_commands.Choice[str]):
        if not user_id.isdigit():
            await interaction.response.send_message("❌ Invalid numeric User ID.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if action.value == "export":
            raw = data_manager.get_dsgvo_data(user_id)
            txt = format_gdpr_report(user_id, raw)
            file = discord.File(fp=io.BytesIO(txt.encode("utf-8")), filename=f"GDPR_Export_{user_id}.txt")
            await interaction.followup.send(f"✅ GDPR export for `{user_id}`:", file=file, ephemeral=True)
        else:
            ok = data_manager.delete_all_user_data(user_id)
            msg = f"✅ All personal data for `{user_id}` erased." if ok else "❌ Database error during erasure."
            await interaction.followup.send(msg, ephemeral=True)

    @setup_config.error
    @setup.error
    @setup_list.error
    @dev_ban.error
    @dev_dsgvo.error
    async def setup_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Setup(bot))