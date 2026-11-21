import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import random
import string
import re
import data_manager
import i18n

async def is_authorized_captain(interaction: discord.Interaction) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if interaction.guild_id and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
        allowed_ids = data_manager.get_allowed_roles(str(interaction.guild_id), "captain_election")
        user_role_ids = [str(r.id) for r in interaction.user.roles]
        if set(allowed_ids) & set(user_role_ids):
            return True
    return False

def generate_election_id():
    return ''.join(random.choices(string.digits, k=10))

class VotingModalView(discord.ui.View):
    def __init__(self, guild_id, lang, candidates, election_id, max_for, max_against, current_votes=None):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.lang = lang
        self.election_id = election_id

        pre_for = current_votes['for'] if current_votes else []
        pre_against = current_votes['against'] if current_votes else []

        actual_max_for = max(1, min(max_for, len(candidates)))
        options_for = [
            discord.SelectOption(label=c[:100], emoji="👍", default=(c in pre_for))
            for c in candidates
        ]
        self.select_for = discord.ui.Select(
            placeholder=i18n.t(lang, "cap_ph_for", max_for=actual_max_for),
            min_values=0,
            max_values=actual_max_for,
            options=options_for,
            row=0
        )
        self.select_for.callback = self.select_for_callback
        self.add_item(self.select_for)

        self.select_against = None
        if max_against > 0:
            actual_max_against = min(max_against, len(candidates))
            options_against = [
                discord.SelectOption(label=c[:100], emoji="👎", default=(c in pre_against))
                for c in candidates
            ]
            self.select_against = discord.ui.Select(
                placeholder=i18n.t(lang, "cap_ph_against", max_against=actual_max_against),
                min_values=0,
                max_values=actual_max_against,
                options=options_against,
                row=1
            )
            self.select_against.callback = self.select_against_callback
            self.add_item(self.select_against)

        submit_btn = discord.ui.Button(
            label=i18n.t(lang, "cap_btn_submit"),
            style=discord.ButtonStyle.green,
            row=2
        )
        submit_btn.callback = self.submit_callback
        self.add_item(submit_btn)

        self.selected_for = list(pre_for)
        self.selected_against = list(pre_against) if max_against > 0 else []

    async def select_for_callback(self, interaction: discord.Interaction):
        self.selected_for = self.select_for.values
        await interaction.response.defer()

    async def select_against_callback(self, interaction: discord.Interaction):
        self.selected_against = self.select_against.values
        await interaction.response.defer()

    async def submit_callback(self, interaction: discord.Interaction):
        overlap = set(self.selected_for) & set(self.selected_against)
        if overlap:
            await interaction.response.send_message(i18n.t(self.lang, "cap_err_overlap"), ephemeral=True)
            return

        success = data_manager.save_votes(
            self.guild_id,
            self.election_id,
            interaction.user.id,
            self.selected_for,
            self.selected_against
        )

        if success:
            msg = i18n.t(self.lang, "cap_saved_title")
            if self.selected_for:
                msg += f"👍 +1: {', '.join(self.selected_for)}\n"
            if self.selected_against:
                msg += f"👎 -1: {', '.join(self.selected_against)}"
            if not self.selected_for and not self.selected_against:
                msg += i18n.t(self.lang, "cap_saved_empty")
            await interaction.response.edit_message(content=msg, view=None)
        else:
            await interaction.response.send_message(i18n.t(self.lang, "db_error"), ephemeral=True)

class PersistentElectionView(discord.ui.View):
    def __init__(self, lang="en"):
        super().__init__(timeout=None)
        self.btn_vote.label = i18n.t(lang, "cap_btn_booth")
        self.btn_res.label = i18n.t(lang, "cap_btn_results")

    def get_election_info(self, embed):
        if not embed.footer or not embed.footer.text:
            return None, None
        text = embed.footer.text
        id_m = re.search(r'ID:\s*(\d+)', text)
        dt_m = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})\s+(\d{1,2}:\d{2})', text)
        e_id = id_m.group(1) if id_m else None
        dl = datetime.strptime(f"{dt_m.group(1)} {dt_m.group(2)}", "%d.%m.%Y %H:%M") if dt_m else None
        return e_id, dl

    def get_candidates(self, embed):
        if embed.fields:
            return [x.strip() for x in embed.fields[0].value.split("\n") if x.strip()]
        return []

    @discord.ui.button(label="Voting Booth", style=discord.ButtonStyle.primary, emoji="🗳️", custom_id="enter_vote")
    async def btn_vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.message.embeds:
            return
        lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        settings = data_manager.get_server_settings(interaction.guild_id)
        e_id, dl = self.get_election_info(interaction.message.embeds[0])

        if not e_id:
            await interaction.response.send_message(i18n.t(lang, "db_error"), ephemeral=True)
            return
        if dl and datetime.now() > dl:
            await interaction.response.send_message(i18n.t(lang, "cap_ended"), ephemeral=True)
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

        current_votes = data_manager.get_user_captain_votes(interaction.guild_id, e_id, interaction.user.id)
        msg_text = i18n.t(lang, "cap_booth_title", eid=e_id)
        if current_votes and (current_votes['for'] or current_votes['against']):
            msg_text += i18n.t(lang, "cap_booth_edit")
        else:
            msg_text += i18n.t(lang, "cap_booth_new")

        view = VotingModalView(
            guild_id=interaction.guild_id,
            lang=lang,
            candidates=self.get_candidates(interaction.message.embeds[0]),
            election_id=e_id,
            max_for=int(settings.get("captain_max_for", 3)),
            max_against=int(settings.get("captain_max_against", 1)),
            current_votes=current_votes
        )
        await interaction.response.send_message(msg_text, view=view, ephemeral=True)

    @discord.ui.button(label="Results", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="calc_res")
    async def btn_res(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.message.embeds:
            return
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        g_lang = i18n.get_guild_lang(interaction.guild_id)
        e_id, dl = self.get_election_info(interaction.message.embeds[0])

        if dl and datetime.now() < dl:
            await interaction.response.send_message(i18n.t(u_lang, "cap_running", dl=dl.strftime('%d.%m.%Y %H:%M')), ephemeral=True)
            return
        if not await is_authorized_captain(interaction):
            await interaction.response.send_message(i18n.t(u_lang, "no_permission"), ephemeral=True)
            return

        raw = data_manager.get_election_results(interaction.guild_id, e_id)
        if not raw:
            await interaction.response.send_message(i18n.t(u_lang, "cap_no_votes"), ephemeral=True)
            return

        candidates = self.get_candidates(interaction.message.embeds[0])
        stats = {c: {"for": 0, "against": 0, "score": 0} for c in candidates}
        voters = set()
        for cand, vtype, voter in raw:
            voters.add(voter)
            if cand in stats:
                if vtype == 'FOR':
                    stats[cand]["score"] += 1
                    stats[cand]["for"] += 1
                elif vtype == 'AGAINST':
                    stats[cand]["score"] -= 1
                    stats[cand]["against"] += 1

        title = interaction.message.embeds[0].title
        res = discord.Embed(
            title=i18n.t(g_lang, "cap_res_title", title=title),
            description=i18n.t(g_lang, "cap_res_voters", count=len(voters)),
            color=discord.Color.gold()
        )
        sorted_cands = sorted(stats.items(), key=lambda x: (x[1]['score'], x[1]['for']), reverse=True)
        for rank, (name, d) in enumerate(sorted_cands, 1):
            res.add_field(
                name=f"#{rank} {name}",
                value=f"Score: **{d['score']}** (+{d['for']} / -{d['against']})",
                inline=True
            )

        await interaction.response.send_message(embed=res)

class CaptainElection(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(PersistentElectionView())

    @app_commands.command(name="captain_election", description="Starts an anonymous Captain Election using server rules")
    @app_commands.describe(
        title="Title of the election",
        deadline_hours="Optional: Duration in hours (leave empty for server default)"
    )
    @app_commands.check(is_authorized_captain)
    async def captain_election(self, interaction: discord.Interaction, title: str, deadline_hours: int = None):
        if not interaction.guild:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return

        settings = data_manager.get_server_settings(interaction.guild_id)
        g_lang = settings["language"]
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)

        team_role_id = settings.get("team_role_id")
        if not team_role_id:
            await interaction.response.send_message(i18n.t(u_lang, "team_role_missing_cfg"), ephemeral=True)
            return

        team_role = interaction.guild.get_role(int(team_role_id))
        if not team_role:
            await interaction.response.send_message(i18n.t(u_lang, "team_role_missing_cfg"), ephemeral=True)
            return

        c_list = []
        for member in interaction.guild.members:
            if member.bot:
                continue
            if data_manager.is_member_observer(member):
                continue
            if team_role not in member.roles:
                continue
            if not data_manager.get_captain_status(interaction.guild_id, member.id):
                continue
            c_list.append(member.display_name)

        c_list.sort(key=lambda s: s.lower())
        if len(c_list) > 25:
            c_list = c_list[:25]

        if len(c_list) < 2:
            await interaction.response.send_message(i18n.t(u_lang, "cap_not_enough", role=team_role.mention), ephemeral=True)
            return

        hours = deadline_hours if deadline_hours is not None else int(settings.get("captain_default_hours", 48))
        dl = datetime.now() + timedelta(hours=max(1, hours))
        e_id = generate_election_id()

        max_for = int(settings.get("captain_max_for", 3))
        max_against = int(settings.get("captain_max_against", 1))
        desc = (
            i18n.t(g_lang, "cap_desc", max_for=max_for, max_against=max_against)
            if max_against > 0
            else i18n.t(g_lang, "cap_desc_no_against", max_for=max_for)
        )

        embed = discord.Embed(title=title, description=desc, color=discord.Color.dark_red())
        embed.add_field(name=i18n.t(g_lang, "cap_candidates"), value="\n".join(c_list), inline=False)
        embed.set_footer(text=i18n.t(g_lang, "cap_footer", eid=e_id, dl=dl.strftime('%d.%m.%Y %H:%M')))

        await interaction.response.send_message(embed=embed, view=PersistentElectionView(g_lang))

    @captain_election.error
    async def error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)

async def setup(bot):
    await bot.add_cog(CaptainElection(bot))
