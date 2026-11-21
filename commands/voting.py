import discord
from discord import app_commands
from discord.ext import commands
from collections import Counter
from datetime import datetime, timedelta
import random
import string
import re
import data_manager
import i18n

async def is_authorized_vote(interaction: discord.Interaction) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if interaction.guild_id and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
        allowed_ids = data_manager.get_allowed_roles(str(interaction.guild_id), "vote")
        user_role_ids = [str(r.id) for r in interaction.user.roles]
        if set(allowed_ids) & set(user_role_ids):
            return True
    return False

def generate_id():
    return ''.join(random.choices(string.digits, k=10))

class GeneralVoteView(discord.ui.View):
    def __init__(self, poll_id, options, max_votes, lang="en"):
        super().__init__(timeout=None)
        self.poll_id = poll_id
        actual_max = min(max_votes, len(options))
        self.select = discord.ui.Select(
            placeholder=i18n.t(lang, "vote_ph", max=actual_max),
            min_values=1,
            max_values=actual_max,
            custom_id=f"gen_vote_sel:{poll_id}",
            options=[discord.SelectOption(label=opt[:100], value=opt[:100]) for opt in options]
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    def get_deadline(self, embed):
        if not embed.footer or not embed.footer.text:
            return None
        match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})\s+(\d{1,2}:\d{2})', embed.footer.text)
        if match:
            try:
                return datetime.strptime(f"{match.group(1)} {match.group(2)}", "%d.%m.%Y %H:%M")
            except:
                pass
        return None

    async def select_callback(self, interaction: discord.Interaction):
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        g_lang = i18n.get_guild_lang(interaction.guild_id)

        if isinstance(interaction.user, discord.Member) and data_manager.is_member_observer(interaction.user):
            await interaction.response.send_message(i18n.t(u_lang, "observer_blocked"), ephemeral=True)
            return

        meta = data_manager.get_general_poll_meta(self.poll_id)
        if not meta:
            return
        _, is_anonymous, _, is_closed = meta

        deadline = self.get_deadline(interaction.message.embeds[0])
        if is_closed or (deadline and datetime.now() > deadline):
            self.select.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(i18n.t(u_lang, "vote_closed"), ephemeral=True)
            return

        selected_choices = interaction.data['values']
        success = data_manager.save_general_vote(
            self.poll_id,
            interaction.user.id,
            interaction.user.display_name,
            selected_choices,
            bool(is_anonymous)
        )

        if success:
            await self.update_poll_message(interaction, bool(is_anonymous), g_lang)
            await interaction.followup.send(i18n.t(u_lang, "vote_saved"), ephemeral=True)
        else:
            await interaction.response.send_message(i18n.t(u_lang, "db_error"), ephemeral=True)

    async def update_poll_message(self, interaction: discord.Interaction, is_anonymous: bool, lang: str):
        votes = data_manager.get_general_poll_votes(self.poll_id)
        total_votes_count = len(votes)
        counts = Counter([v[0] for v in votes])

        embed = interaction.message.embeds[0]
        old_dl = self.get_deadline(embed)
        embed.clear_fields()

        mode_str = i18n.t(lang, "vote_anon" if is_anonymous else "vote_public")
        embed.add_field(name=i18n.t(lang, "vote_mode"), value=f"**{mode_str}**", inline=False)

        all_options = [opt.label for opt in self.select.options]
        for option in all_options:
            count = counts[option]
            percent = (count / total_votes_count * 100) if total_votes_count > 0 else 0
            filled = int(percent / 10)
            bar = "▓" * filled + "░" * (10 - filled)
            field_value = f"`{bar}` {percent:.1f}%"

            if not is_anonymous and count > 0:
                voters = [v[1] for v in votes if v[0] == option]
                voters_str = ", ".join(voters[:12]) + ("..." if len(voters) > 12 else "")
                field_value += f"\n{i18n.t(lang, 'vote_voters')}: {voters_str}"

            embed.add_field(name=f"{option} ({count})", value=field_value, inline=False)

        footer_text = i18n.t(lang, "vote_footer_base", pid=self.poll_id, count=total_votes_count, mode=mode_str)
        if old_dl:
            footer_text += i18n.t(lang, "vote_footer_end", dl=old_dl.strftime('%d.%m.%Y %H:%M'))
        embed.set_footer(text=footer_text)

        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed)
        else:
            await interaction.message.edit(embed=embed)

class Voting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="vote", description="Creates a general poll (public or anonymous)")
    @app_commands.describe(
        title="Poll topic / question",
        options="Comma-separated options (e.g. Yes, No, Maybe)",
        anonymous="Hide voter names?",
        max_choices="Maximum choices per voter",
        deadline_hours="Optional: Hours until poll closes automatically"
    )
    @app_commands.check(is_authorized_vote)
    async def vote(self, interaction: discord.Interaction, title: str, options: str, anonymous: bool = False, max_choices: int = 1, deadline_hours: int = None):
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return

        g_lang = i18n.get_guild_lang(interaction.guild_id)
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)

        options_list = []
        for opt in options.split(","):
            clean = opt.strip()
            if clean and clean not in options_list:
                options_list.append(clean)

        if len(options_list) < 2 or len(options_list) > 25:
            await interaction.response.send_message(i18n.t(u_lang, "vote_invalid_opts"), ephemeral=True)
            return

        max_choices = max(1, min(max_choices, len(options_list)))
        poll_id = generate_id()
        await interaction.response.defer()

        embed = discord.Embed(
            title=f"📊 {title}",
            description=i18n.t(g_lang, "vote_desc", max=max_choices),
            color=discord.Color.purple()
        )

        mode_str = i18n.t(g_lang, "vote_anon" if anonymous else "vote_public")
        embed.add_field(name=i18n.t(g_lang, "vote_mode"), value=f"**{mode_str}**", inline=False)

        for opt in options_list:
            embed.add_field(name=f"{opt} (0)", value="`░░░░░░░░░░` 0.0%", inline=False)

        footer_text = i18n.t(g_lang, "vote_footer_base", pid=poll_id, count=0, mode=mode_str)
        if deadline_hours:
            dl = datetime.now() + timedelta(hours=max(1, deadline_hours))
            footer_text += i18n.t(g_lang, "vote_footer_end", dl=dl.strftime('%d.%m.%Y %H:%M'))
        embed.set_footer(text=footer_text)

        view = GeneralVoteView(poll_id, options_list, max_choices, g_lang)
        message = await interaction.followup.send(embed=embed, view=view)
        data_manager.create_general_poll(interaction.guild_id, poll_id, title, anonymous, max_choices, interaction.user.id, interaction.channel.id, message.id)

    @vote.error
    async def error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Voting(bot))
