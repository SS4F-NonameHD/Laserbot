import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import random
import string
import re
import data_manager
import i18n

async def is_authorized_decisions(interaction: discord.Interaction) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if interaction.guild_id and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
        allowed_ids = data_manager.get_allowed_roles(str(interaction.guild_id), "team_decisions")
        user_role_ids = [str(r.id) for r in interaction.user.roles]
        if set(allowed_ids) & set(user_role_ids):
            return True
    return False

def generate_poll_id():
    return ''.join(random.choices(string.digits, k=10))

class DecisionVoteView(discord.ui.View):
    def __init__(self, guild_id, poll_id, lang="en"):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.lang = lang
        self.vote_yes.label = i18n.t(lang, "dec_btn_yes")
        self.vote_no.label = i18n.t(lang, "dec_btn_no")
        self.vote_abstain.label = i18n.t(lang, "dec_btn_abstain")

    def _choice_label(self, val):
        if val == "YES": return f"✅ {i18n.t(self.lang, 'dec_btn_yes')}"
        if val == "NO": return f"❌ {i18n.t(self.lang, 'dec_btn_no')}"
        return f"😶 {i18n.t(self.lang, 'dec_btn_abstain')}"

    async def cast_vote(self, interaction: discord.Interaction, vote_value: str):
        success = data_manager.save_majority_vote(self.guild_id, self.poll_id, interaction.user.id, vote_value)
        if success:
            txt = i18n.t(self.lang, "dec_voted_confirm", choice=self._choice_label(vote_value))
            await interaction.response.edit_message(content=txt, view=self)
        else:
            await interaction.response.send_message(i18n.t(self.lang, "db_error"), ephemeral=True)

    @discord.ui.button(label="FOR", style=discord.ButtonStyle.success, emoji="✅")
    async def vote_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cast_vote(interaction, "YES")

    @discord.ui.button(label="AGAINST", style=discord.ButtonStyle.danger, emoji="❌")
    async def vote_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cast_vote(interaction, "NO")

    @discord.ui.button(label="ABSTAIN", style=discord.ButtonStyle.secondary, emoji="😶")
    async def vote_abstain(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cast_vote(interaction, "ABSTAIN")

class DecisionMainView(discord.ui.View):
    def __init__(self, lang="en"):
        super().__init__(timeout=None)
        self.open_vote_button.label = i18n.t(lang, "dec_btn_vote")
        self.result_button.label = i18n.t(lang, "dec_btn_results")

    def get_poll_info(self, embed):
        if not embed.footer or not embed.footer.text:
            return None, "admission", None
        text = embed.footer.text

        id_match = re.search(r'ID:\s*([a-zA-Z0-9]+)', text)
        poll_id = id_match.group(1) if id_match else None

        type_match = re.search(r'(?:Type|Typ|Tipo):\s*([a-zA-Z_]+)', text)
        poll_type = type_match.group(1).lower() if type_match else ("votekick" if "kick" in (embed.title or "").lower() else "admission")

        date_match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})\s+(\d{1,2}:\d{2})', text)
        deadline = None
        if date_match:
            try:
                deadline = datetime.strptime(f"{date_match.group(1)} {date_match.group(2)}", "%d.%m.%Y %H:%M")
            except:
                pass
        return poll_id, poll_type, deadline

    @discord.ui.button(label="Vote", style=discord.ButtonStyle.primary, emoji="🗳️", custom_id="decision_vote_btn")
    async def open_vote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.message.embeds:
            return
        lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        settings = data_manager.get_server_settings(interaction.guild_id)
        poll_id, _, deadline = self.get_poll_info(interaction.message.embeds[0])
        if not poll_id:
            return

        if deadline and datetime.now() > deadline:
            await interaction.response.send_message(i18n.t(lang, "dec_ended"), ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member):
            return
        if data_manager.is_member_observer(interaction.user):
            await interaction.response.send_message(i18n.t(lang, "observer_blocked"), ephemeral=True)
            return

        team_role_id = settings.get("team_role_id")
        if not team_role_id:
            await interaction.response.send_message(i18n.t(lang, "team_role_missing_cfg"), ephemeral=True)
            return
        team_role = interaction.guild.get_role(int(team_role_id))
        if not team_role or team_role not in interaction.user.roles:
            r_mention = team_role.mention if team_role else "Team"
            await interaction.response.send_message(i18n.t(lang, "team_only", role=r_mention), ephemeral=True)
            return

        current_vote = data_manager.get_my_vote(interaction.guild_id, poll_id, interaction.user.id)
        if current_vote == "YES": c_str = f"✅ {i18n.t(lang, 'dec_btn_yes')}"
        elif current_vote == "NO": c_str = f"❌ {i18n.t(lang, 'dec_btn_no')}"
        elif current_vote == "ABSTAIN": c_str = f"😶 {i18n.t(lang, 'dec_btn_abstain')}"
        else: c_str = i18n.t(lang, "dec_none")

        msg_text = i18n.t(lang, "dec_current", pid=poll_id, choice=c_str)
        await interaction.response.send_message(msg_text, view=DecisionVoteView(interaction.guild_id, poll_id, lang), ephemeral=True)

    @discord.ui.button(label="Evaluate", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="decision_result_btn")
    async def result_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.message.embeds:
            return
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        g_lang = i18n.get_guild_lang(interaction.guild_id)

        if not await is_authorized_decisions(interaction):
            await interaction.response.send_message(i18n.t(u_lang, "no_permission"), ephemeral=True)
            return

        poll_id, poll_type, deadline = self.get_poll_info(interaction.message.embeds[0])
        if deadline and datetime.now() < deadline:
            await interaction.response.send_message(i18n.t(u_lang, "dec_running", dl=deadline.strftime('%d.%m.%Y %H:%M')), ephemeral=True)
            return
        if not poll_id:
            await interaction.response.send_message(i18n.t(u_lang, "db_error"), ephemeral=True)
            return

        settings = data_manager.get_server_settings(interaction.guild_id)
        req_maj = float(settings.get("votekick_majority", 66.67) if poll_type == "votekick" else settings.get("aufnahme_majority", 66.67))
        req_quorum = float(settings.get("decision_quorum", 0.0))

        raw_votes = data_manager.get_full_majority_poll_data(interaction.guild_id, poll_id)
        yes, no, abstain = 0, 0, 0
        voted_hashes = set()

        for v_type, v_hash in raw_votes:
            voted_hashes.add(v_hash)
            if v_type == 'YES': yes += 1
            elif v_type == 'NO': no += 1
            elif v_type == 'ABSTAIN': abstain += 1

        total_votes = yes + no + abstain
        valid_votes = yes + no
        if total_votes == 0:
            await interaction.response.send_message(i18n.t(u_lang, "cap_no_votes"), ephemeral=True)
            return

        team_role_id = settings.get("team_role_id")
        team_role = interaction.guild.get_role(int(team_role_id)) if team_role_id else None
        if team_role:
            eligible_members = [
                m for m in interaction.guild.members
                if not m.bot and not data_manager.is_member_observer(m) and team_role in m.roles
            ]
        else:
            eligible_members = []

        voted_count = 0
        eligible_count = len(eligible_members)
        for m in eligible_members:
            m_hash = data_manager._anonymize_voter(m.id, f"{interaction.guild_id}-{poll_id}")
            if m_hash in voted_hashes:
                voted_count += 1

        participation_rate = (voted_count / eligible_count * 100) if eligible_count > 0 else 100.0
        percent_yes = (yes / valid_votes * 100) if valid_votes > 0 else 0.0
        percent_no = (no / valid_votes * 100) if valid_votes > 0 else 0.0

        quorum_ok = participation_rate >= req_quorum
        maj_ok = valid_votes > 0 and (percent_yes + 1e-9) >= req_maj

        if not quorum_ok:
            outcome_str = i18n.t(g_lang, "dec_failed_quorum", quorum=req_quorum)
            col = discord.Color.red()
        elif maj_ok:
            outcome_str = i18n.t(g_lang, "dec_passed")
            col = discord.Color.green()
        else:
            outcome_str = i18n.t(g_lang, "dec_failed_maj", maj=req_maj)
            col = discord.Color.red()

        res_embed = discord.Embed(
            title=i18n.t(g_lang, "dec_res_title", title=interaction.message.embeds[0].title),
            color=col
        )
        res_embed.add_field(name=f"✅ {i18n.t(g_lang, 'dec_btn_yes')}", value=f"{yes} ({percent_yes:.1f}%)", inline=True)
        res_embed.add_field(name=f"❌ {i18n.t(g_lang, 'dec_btn_no')}", value=f"{no} ({percent_no:.1f}%)", inline=True)
        res_embed.add_field(name=f"😶 {i18n.t(g_lang, 'dec_btn_abstain')}", value=str(abstain), inline=True)
        res_embed.add_field(name=i18n.t(g_lang, "dec_status_title"), value=outcome_str, inline=False)
        res_embed.add_field(
            name=i18n.t(g_lang, "dec_turnout_title"),
            value=i18n.t(g_lang, "dec_turnout_val", rate=participation_rate, voted=voted_count, eligible=eligible_count),
            inline=False
        )
        await interaction.response.send_message(embed=res_embed)

def build_decision_poll_embed(guild_id, poll_type: str, person_name: str, deadline_hours: int = None):
    settings = data_manager.get_server_settings(guild_id)
    lang = settings["language"]
    hours = deadline_hours if deadline_hours is not None else int(settings.get("decision_default_hours", 48))

    is_kick = (poll_type == "votekick")
    maj = settings.get("votekick_majority", 66.67) if is_kick else settings.get("aufnahme_majority", 66.67)
    quorum = float(settings.get("decision_quorum", 0.0))
    quorum_txt = i18n.t(lang, "dec_quorum_line", quorum=quorum) if quorum > 0 else ""

    type_label = i18n.t(lang, "dec_type_votekick" if is_kick else "dec_type_admission")
    color = discord.Color.red() if is_kick else discord.Color.green()

    poll_id = generate_poll_id()
    deadline = datetime.now() + timedelta(hours=max(1, hours))

    embed = discord.Embed(
        title=f"{type_label}: {person_name}",
        description=i18n.t(lang, "dec_desc", name=person_name),
        color=color
    )
    embed.add_field(
        name=i18n.t(lang, "dec_info_title"),
        value=i18n.t(lang, "dec_info_val", maj=maj, quorum_txt=quorum_txt),
        inline=False
    )
    embed.set_footer(text=i18n.t(lang, "dec_footer", pid=poll_id, ptype=poll_type, dl=deadline.strftime('%d.%m.%Y %H:%M')))
    return embed, DecisionMainView(lang)

class TeamDecisions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(DecisionMainView())

    @app_commands.command(name="admission", description="Starts an anonymous team admission vote")
    @app_commands.describe(name="Applicant's name", deadline_hours="Optional: Hours until poll closes (default: server setting)")
    @app_commands.check(is_authorized_decisions)
    async def admission(self, interaction: discord.Interaction, name: str, deadline_hours: int = None):
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return
        settings = data_manager.get_server_settings(interaction.guild_id)
        if not settings.get("team_role_id"):
            await interaction.response.send_message(i18n.t(interaction, "team_role_missing_cfg"), ephemeral=True)
            return
        embed, view = build_decision_poll_embed(interaction.guild_id, "admission", name, deadline_hours)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="votekick", description="Starts an anonymous team exclusion vote")
    @app_commands.describe(name="Member's name", deadline_hours="Optional: Hours until poll closes (default: server setting)")
    @app_commands.check(is_authorized_decisions)
    async def votekick(self, interaction: discord.Interaction, name: str, deadline_hours: int = None):
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return
        settings = data_manager.get_server_settings(interaction.guild_id)
        if not settings.get("team_role_id"):
            await interaction.response.send_message(i18n.t(interaction, "team_role_missing_cfg"), ephemeral=True)
            return
        embed, view = build_decision_poll_embed(interaction.guild_id, "votekick", name, deadline_hours)
        await interaction.response.send_message(embed=embed, view=view)

    @admission.error
    @votekick.error
    async def error_handler(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)

async def setup(bot):
    await bot.add_cog(TeamDecisions(bot))
