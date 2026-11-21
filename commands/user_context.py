import discord
from discord import ui, app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import io
import data_manager
import i18n
from commands.team_decisions import build_decision_poll_embed
from commands.profile import build_profile_dashboard
from commands.setup import format_gdpr_report

def check_auth(interaction: discord.Interaction, permission_name: str) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if interaction.guild_id and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
        allowed = data_manager.get_allowed_roles(str(interaction.guild_id), permission_name)
        if set(allowed) & set([str(r.id) for r in interaction.user.roles]):
            return True
    return False

class ProfileInspectView(discord.ui.View):
    def __init__(self, invoker: discord.Member, target_member: discord.Member, is_dev: bool, lang: str):
        super().__init__(timeout=120)
        self.invoker = invoker
        self.target_member = target_member
        self.lang = lang

        if self.invoker.id == self.target_member.id:
            btn_edit = discord.ui.Button(label="Edit Profile", style=discord.ButtonStyle.primary, emoji="⚙️")
            btn_edit.callback = self.edit_profile
            self.add_item(btn_edit)

        if is_dev:
            btn_dsgvo = discord.ui.Button(label="[Dev] GDPR Export", style=discord.ButtonStyle.danger, emoji="🗃️")
            btn_dsgvo.callback = self.generate_dsgvo
            self.add_item(btn_dsgvo)

    async def edit_profile(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_member.id:
            return
        embed, view = build_profile_dashboard(interaction.user, interaction.guild_id, self.lang)
        await interaction.response.edit_message(embed=embed, view=view)

    async def generate_dsgvo(self, interaction: discord.Interaction):
        if interaction.user.id not in data_manager.DEVELOPER_IDS:
            await interaction.response.send_message(i18n.t(self.lang, "no_permission"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        raw_data = data_manager.get_dsgvo_data(self.target_member.id)
        output = format_gdpr_report(str(self.target_member.id), raw_data)
        file = discord.File(fp=io.BytesIO(output.encode('utf-8')), filename=f"GDPR_Export_{self.target_member.id}.txt")
        await interaction.followup.send(f"✅ GDPR Export for **{self.target_member.display_name}**:", file=file, ephemeral=True)

class ContextVoteModal(discord.ui.Modal):
    deadline_stunden = discord.ui.TextInput(label="Duration (in hours)", required=True)

    def __init__(self, target_member: discord.Member, default_hours: int = 48):
        super().__init__(title=f"Votekick: {target_member.display_name[:30]}")
        self.target_member = target_member
        self.default_hours = default_hours
        self.deadline_stunden.default = str(default_hours)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            hours = int(self.deadline_stunden.value)
        except ValueError:
            hours = self.default_hours
        embed, view = build_decision_poll_embed(interaction.guild_id, "votekick", self.target_member.display_name, hours)
        await interaction.response.send_message(embed=embed, view=view)

class OrgaPingModal(discord.ui.Modal, title="Send Orga-Ping (DM)"):
    message_text = discord.ui.TextInput(label="Message to player", style=discord.TextStyle.paragraph, required=True, max_length=2000)

    def __init__(self, target_member: discord.Member):
        super().__init__()
        self.target_member = target_member

    async def on_submit(self, interaction: discord.Interaction):
        g_lang = i18n.get_guild_lang(interaction.guild_id)
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        embed = discord.Embed(
            title=i18n.t(g_lang, "ctx_ping_title"),
            description=self.message_text.value,
            color=discord.Color.gold()
        )
        embed.set_footer(text=i18n.t(g_lang, "ctx_ping_footer", sender=interaction.user.display_name, guild=interaction.guild.name))
        try:
            await self.target_member.send(embed=embed)
            await interaction.response.send_message(i18n.t(u_lang, "ctx_ping_sent", name=self.target_member.display_name), ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(i18n.t(u_lang, "ctx_ping_closed", name=self.target_member.display_name), ephemeral=True)

class UserManagementView(discord.ui.View):
    def __init__(self, target_member: discord.Member, can_ping: bool, can_manage_guests: bool):
        super().__init__(timeout=120)
        self.target_member = target_member

        if can_ping:
            btn_ping = discord.ui.Button(label="Send Orga-Ping", style=discord.ButtonStyle.primary, emoji="🔔", row=0)
            btn_ping.callback = self.send_ping
            self.add_item(btn_ping)

        if can_manage_guests:
            btn_grant = discord.ui.Button(label="Grant Guest Role", style=discord.ButtonStyle.success, emoji="👋", row=1)
            btn_grant.callback = self.grant_guest
            self.add_item(btn_grant)

            btn_revoke = discord.ui.Button(label="Revoke Guest Role", style=discord.ButtonStyle.danger, emoji="❌", row=1)
            btn_revoke.callback = self.revoke_guest
            self.add_item(btn_revoke)

    async def send_ping(self, interaction: discord.Interaction):
        await interaction.response.send_modal(OrgaPingModal(self.target_member))

    async def grant_guest(self, interaction: discord.Interaction):
        g_lang = i18n.get_guild_lang(interaction.guild_id)
        role_id, default_days = data_manager.get_guest_settings(interaction.guild.id)
        role = interaction.guild.get_role(int(role_id)) if role_id else None
        if not role:
            await interaction.response.send_message(i18n.t(interaction, "guest_not_cfg"), ephemeral=True)
            return

        expires_at = datetime.now() + timedelta(days=default_days) if default_days > 0 else datetime.now() + timedelta(days=3650)
        try:
            await self.target_member.add_roles(role)
            if default_days > 0:
                data_manager.add_active_guest(interaction.guild.id, self.target_member.id, expires_at)
            expiry_text = "Permanent" if default_days <= 0 else expires_at.strftime('%d.%m.%Y %H:%M')
            try:
                dm = discord.Embed(
                    title=i18n.t(g_lang, "guest_dm_approved_t"),
                    description=i18n.t(g_lang, "guest_dm_approved_d", guild=interaction.guild.name),
                    color=discord.Color.green()
                )
                if default_days > 0:
                    dm.add_field(name=i18n.t(g_lang, "guest_dm_exp"), value=expiry_text, inline=False)
                await self.target_member.send(embed=dm)
            except:
                pass
            await interaction.response.edit_message(content=f"✅ Granted {role.mention} to {self.target_member.mention} ({expiry_text}).", view=None, embed=None)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Missing role hierarchy permissions.", ephemeral=True)

    async def revoke_guest(self, interaction: discord.Interaction):
        role_id, _ = data_manager.get_guest_settings(interaction.guild.id)
        role = interaction.guild.get_role(int(role_id)) if role_id else None
        if role and role in self.target_member.roles:
            try:
                await self.target_member.remove_roles(role)
                data_manager.remove_active_guest(interaction.guild.id, self.target_member.id)
                await interaction.response.edit_message(content=f"✅ Revoked {role.mention} from {self.target_member.mention}.", view=None, embed=None)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Missing role hierarchy permissions.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Member does not hold the guest role.", ephemeral=True)

class ContextMenus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ctx_votekick = app_commands.ContextMenu(name="Votekick", callback=self.votekick)
        self.ctx_profil = app_commands.ContextMenu(name="View Profile", callback=self.profil_ansehen)
        self.ctx_verwaltung = app_commands.ContextMenu(name="Manage Member", callback=self.user_verwaltung)
        self.ctx_report = app_commands.ContextMenu(name="Report Message", callback=self.report_message)

        for ctx in [self.ctx_votekick, self.ctx_profil, self.ctx_verwaltung, self.ctx_report]:
            self.bot.tree.add_command(ctx)

    async def cog_unload(self) -> None:
        for ctx in [self.ctx_votekick, self.ctx_profil, self.ctx_verwaltung, self.ctx_report]:
            self.bot.tree.remove_command(ctx.name, type=ctx.type)

    async def report_message(self, interaction: discord.Interaction, message: discord.Message):
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t(u_lang, "server_only"), ephemeral=True)
            return

        settings = data_manager.get_server_settings(interaction.guild_id)
        rep_ch_id = settings.get("report_channel_id")
        target_ch = interaction.guild.get_channel(int(rep_ch_id)) if rep_ch_id else None

        if not target_ch:
            await interaction.response.send_message(i18n.t(u_lang, "ctx_rep_missing"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="🚨 Message Report", color=discord.Color.red(), timestamp=datetime.now())
        embed.add_field(name="Reporter", value=f"{interaction.user.mention} ({interaction.user.display_name})", inline=True)
        embed.add_field(name="Author", value=f"{message.author.mention} ({message.author.display_name})", inline=True)
        embed.add_field(name="Channel", value=message.channel.mention if hasattr(message.channel, "mention") else "Thread", inline=True)
        embed.add_field(name="Content", value=(message.content or "*No text*")[:1020], inline=False)

        if message.attachments:
            images = [a.url for a in message.attachments if a.content_type and a.content_type.startswith('image/')]
            files = [f"[{a.filename}]({a.url})" for a in message.attachments if not (a.content_type and a.content_type.startswith('image/'))]
            if images:
                embed.set_image(url=images[0])
                if len(images) > 1:
                    embed.add_field(name="Additional Images", value="\n".join([f"[Image {idx+1}]({u})" for idx, u in enumerate(images)])[:1024], inline=False)
            if files:
                embed.add_field(name="Attachments", value="\n".join(files)[:1024], inline=False)

        embed.add_field(name="Jump Link", value=f"[Jump to Message]({message.jump_url})", inline=False)
        await target_ch.send(embed=embed)
        await interaction.followup.send(i18n.t(u_lang, "ctx_rep_sent"), ephemeral=True)

    async def votekick(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild_id:
            return
        if not check_auth(interaction, "team_decisions"):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)
            return
        settings = data_manager.get_server_settings(interaction.guild_id)
        if not settings.get("team_role_id"):
            await interaction.response.send_message(i18n.t(interaction, "team_role_missing_cfg"), ephemeral=True)
            return
        await interaction.response.send_modal(ContextVoteModal(member, int(settings.get("decision_default_hours", 48))))

    async def user_verwaltung(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild_id:
            return
        can_ping = check_auth(interaction, "orga_ping")
        can_manage_guests = check_auth(interaction, "manage_guests")
        if not (can_ping or can_manage_guests):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)
            return

        embed = discord.Embed(title=f"⚙️ Manage: {member.display_name}", color=discord.Color.dark_theme())
        expiry = data_manager.get_guest_expiry(interaction.guild_id, member.id)
        if expiry:
            embed.add_field(name="Guest Role Expires", value=expiry.strftime('%d.%m.%Y %H:%M'), inline=False)
        await interaction.response.send_message(embed=embed, view=UserManagementView(member, can_ping, can_manage_guests), ephemeral=True)

    async def profil_ansehen(self, interaction: discord.Interaction, member: discord.Member):
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        is_self = (interaction.user.id == member.id)
        is_dev = (interaction.user.id in data_manager.DEVELOPER_IDS)

        if not (is_self or is_dev):
            await interaction.response.send_message(i18n.t(u_lang, "ctx_self_only"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        tags = data_manager.get_all_lf_tags()
        lf_tag = tags.get(str(member.id))
        lf_text = f"[Open Profile ({lf_tag})](https://v2.iplaylaserforce.com/iframe.php?t={lf_tag})" if lf_tag else "None"

        travel_prof = data_manager.get_travel_profile(member.id)
        auto_text = "Yes 🚗" if travel_prof.get("has_license") else "No ❌"
        pref = travel_prof.get("room_pref", "shared")
        if pref == "single":
            zimmer_text = "Single"
        elif pref == "double":
            zimmer_text = f"Double (<@{travel_prof.get('partner_id')}>)" if travel_prof.get("partner_id") else "Double"
        else:
            zimmer_text = "Shared"

        p_raw = travel_prof.get("default_passengers")
        passengers_text = ", ".join([f"<@{uid.strip()}>" for uid in p_raw.split(',') if uid.strip()]) if p_raw else "None"

        absences = data_manager.get_user_absences(member.id)
        today = datetime.now().date()
        valid_abs = [a for a in absences if a[2].date() >= today]
        abs_text = "\n".join([f"• {s.strftime('%d.%m.%Y')} – {e.strftime('%d.%m.%Y')} ({r})" for _, s, e, r in valid_abs]) if valid_abs else "None"

        embed = discord.Embed(title=f"Profile: {member.display_name}", color=member.color)
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Laserforce", value=lf_text, inline=False)
        embed.add_field(name="Travel Preferences", value=f"**License:** {auto_text}\n**Room:** {zimmer_text}\n**Passengers:** {passengers_text}", inline=False)
        embed.add_field(name="Upcoming Absences", value=abs_text, inline=False)

        await interaction.followup.send(embed=embed, view=ProfileInspectView(interaction.user, member, is_dev, u_lang), ephemeral=True)

async def setup(bot):
    await bot.add_cog(ContextMenus(bot))
