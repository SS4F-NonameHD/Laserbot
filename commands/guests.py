import discord
from discord import ui, app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import re
import data_manager
import i18n

def set_trainer_channel(guild_id, channel_id):
    try:
        conn = data_manager.get_main_db_connection()
        c = conn.cursor()
        c.execute("REPLACE INTO guest_panels (guild_id, channel_id) VALUES (%s, %s)", (str(guild_id), str(channel_id)))
        conn.commit(); c.close(); conn.close()
    except Exception as e:
        print(f"DB Error Guest Panels: {e}")

def get_trainer_channel(guild_id):
    try:
        conn = data_manager.get_main_db_connection()
        c = conn.cursor()
        c.execute("SELECT channel_id FROM guest_panels WHERE guild_id=%s", (str(guild_id),))
        r = c.fetchone()
        c.close(); conn.close()
        return int(r[0]) if r else None
    except:
        return None

def is_authorized_manage_guests(interaction: discord.Interaction) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if interaction.guild_id and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
        allowed = data_manager.get_allowed_roles(str(interaction.guild_id), "manage_guests")
        if set(allowed) & set([str(r.id) for r in interaction.user.roles]):
            return True
    return False

class GuestApplicationModal(ui.Modal):
    def __init__(self, target_channel_id: int, u_lang: str, g_lang: str):
        super().__init__(title=i18n.t(u_lang, "guest_modal_title"))
        self.target_channel_id = target_channel_id
        self.u_lang = u_lang
        self.g_lang = g_lang

        self.timeframe = ui.TextInput(label=i18n.t(u_lang, "guest_modal_time"), required=True, max_length=100)
        self.home_arena = ui.TextInput(label=i18n.t(u_lang, "guest_modal_arena"), required=True, max_length=100)
        self.add_item(self.timeframe)
        self.add_item(self.home_arena)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        target_channel = interaction.guild.get_channel(self.target_channel_id)
        if not target_channel:
            await interaction.followup.send(i18n.t(self.u_lang, "guest_not_cfg"), ephemeral=True)
            return

        embed = discord.Embed(
            title=i18n.t(self.g_lang, "guest_rev_title"),
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        embed.add_field(name=i18n.t(self.g_lang, "guest_rev_user"), value=f"{interaction.user.mention} ({interaction.user.display_name})", inline=False)
        embed.add_field(name=i18n.t(self.g_lang, "guest_rev_time"), value=self.timeframe.value, inline=False)
        embed.add_field(name=i18n.t(self.g_lang, "guest_rev_arena"), value=self.home_arena.value, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        await target_channel.send(embed=embed, view=TrainerReviewView(self.g_lang))
        await interaction.followup.send(i18n.t(self.u_lang, "guest_submitted"), ephemeral=True)

class TrainerReviewView(ui.View):
    def __init__(self, lang: str = "en"):
        super().__init__(timeout=None)
        self.btn_approve.label = i18n.t(lang, "guest_btn_approve")
        self.btn_reject.label = i18n.t(lang, "guest_btn_reject")

    def get_applicant_id(self, embed):
        for f in embed.fields:
            match = re.search(r'<@!?(\d+)>', f.value)
            if match:
                return int(match.group(1))
        return None

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅", custom_id="guest_approve_global")
    async def btn_approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        g_lang = i18n.get_guild_lang(interaction.guild_id)

        if not is_authorized_manage_guests(interaction):
            await interaction.followup.send(i18n.t(u_lang, "no_permission"), ephemeral=True)
            return

        role_id, default_days = data_manager.get_guest_settings(interaction.guild.id)
        if not role_id:
            await interaction.followup.send(i18n.t(u_lang, "guest_not_cfg"), ephemeral=True)
            return

        applicant_id = self.get_applicant_id(interaction.message.embeds[0])
        member = interaction.guild.get_member(applicant_id) if applicant_id else None
        if not member:
            await interaction.followup.send("❌ Applicant is no longer on this server.", ephemeral=True)
            return

        role = interaction.guild.get_role(int(role_id))
        if not role:
            await interaction.followup.send(i18n.t(u_lang, "guest_not_cfg"), ephemeral=True)
            return

        expires_at = datetime.now() + timedelta(days=default_days) if default_days > 0 else datetime.now() + timedelta(days=3650)
        try:
            await member.add_roles(role)
            if default_days > 0:
                data_manager.add_active_guest(interaction.guild.id, member.id, expires_at)

            try:
                dm_embed = discord.Embed(
                    title=i18n.t(g_lang, "guest_dm_approved_t"),
                    description=i18n.t(g_lang, "guest_dm_approved_d", guild=interaction.guild.name),
                    color=discord.Color.green()
                )
                if default_days > 0:
                    dm_embed.add_field(name=i18n.t(g_lang, "guest_dm_exp"), value=expires_at.strftime('%d.%m.%Y %H:%M'), inline=False)
                await member.send(embed=dm_embed)
            except:
                pass

            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            exp_txt = "Permanent" if default_days <= 0 else expires_at.strftime('%d.%m.%Y')
            embed.add_field(name="Status", value=f"✅ {interaction.user.mention} ({exp_txt})", inline=False)

            for c in self.children:
                c.disabled = True
            await interaction.message.edit(embed=embed, view=self)
        except discord.Forbidden:
            await interaction.followup.send("❌ Missing Discord role hierarchy permissions to assign the Guest role.", ephemeral=True)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="❌", custom_id="guest_reject_global")
    async def btn_reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        g_lang = i18n.get_guild_lang(interaction.guild_id)

        if not is_authorized_manage_guests(interaction):
            await interaction.followup.send(i18n.t(u_lang, "no_permission"), ephemeral=True)
            return

        applicant_id = self.get_applicant_id(interaction.message.embeds[0])
        member = interaction.guild.get_member(applicant_id) if applicant_id else None
        if member:
            try:
                dm_embed = discord.Embed(
                    title=i18n.t(g_lang, "guest_dm_rejected_t"),
                    description=i18n.t(g_lang, "guest_dm_rejected_d", guild=interaction.guild.name),
                    color=discord.Color.red()
                )
                await member.send(embed=dm_embed)
            except:
                pass

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value=f"❌ {interaction.user.mention}", inline=False)
        for c in self.children:
            c.disabled = True
        await interaction.message.edit(embed=embed, view=self)

class GuestPanelView(ui.View):
    def __init__(self, lang: str = "en"):
        super().__init__(timeout=None)
        self.btn_apply.label = i18n.t(lang, "guest_btn_apply")

    @discord.ui.button(label="Apply for Training Participation", style=discord.ButtonStyle.primary, emoji="👋", custom_id="guest_apply_btn_global")
    async def btn_apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        g_lang = i18n.get_guild_lang(interaction.guild_id)

        role_id, _ = data_manager.get_guest_settings(interaction.guild.id)
        if not role_id:
            await interaction.response.send_message(i18n.t(u_lang, "guest_not_cfg"), ephemeral=True)
            return

        if any(str(r.id) == str(role_id) for r in interaction.user.roles):
            await interaction.response.send_message(i18n.t(u_lang, "guest_already"), ephemeral=True)
            return

        trainer_channel_id = get_trainer_channel(interaction.guild.id)
        if not trainer_channel_id:
            await interaction.response.send_message(i18n.t(u_lang, "guest_not_cfg"), ephemeral=True)
            return

        await interaction.response.send_modal(GuestApplicationModal(trainer_channel_id, u_lang, g_lang))

class Guests(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guest_expiry_loop.start()

    async def cog_load(self):
        self.bot.add_view(GuestPanelView())
        self.bot.add_view(TrainerReviewView())

    def cog_unload(self):
        self.guest_expiry_loop.cancel()

    @app_commands.command(name="send_training_guest_panel", description="Posts the application panel for visiting training guests")
    @app_commands.describe(
        trainer_channel="Internal channel where guest applications will be posted",
        panel_language="Optional: Override language for this panel (default: server language)"
    )
    @app_commands.choices(panel_language=[
        app_commands.Choice(name=lbl, value=code) for code, lbl in i18n.SUPPORTED_LANGUAGES.items()
    ])
    async def send_training_guest_panel(self, interaction: discord.Interaction, trainer_channel: discord.TextChannel, panel_language: app_commands.Choice[str] = None):
        if not interaction.guild:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return
        if not (interaction.user.guild_permissions.administrator or interaction.user.id in data_manager.DEVELOPER_IDS):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        set_trainer_channel(interaction.guild.id, trainer_channel.id)
        lang = panel_language.value if panel_language else i18n.get_guild_lang(interaction.guild.id)

        embed = discord.Embed(
            title=i18n.t(lang, "guest_panel_title"),
            description=i18n.t(lang, "guest_panel_desc"),
            color=discord.Color.blue()
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        await interaction.channel.send(embed=embed, view=GuestPanelView(lang))
        await interaction.followup.send(f"✅ Panel created! Applications will be forwarded to {trainer_channel.mention}.", ephemeral=True)

    @tasks.loop(minutes=30)
    async def guest_expiry_loop(self):
        expired = data_manager.get_expired_guests()
        for guild_id_str, user_id_str, _ in expired:
            try:
                guild = self.bot.get_guild(int(guild_id_str))
                if not guild:
                    continue
                g_lang = i18n.get_guild_lang(guild.id)
                role_id, _ = data_manager.get_guest_settings(guild.id)
                if role_id:
                    role = guild.get_role(int(role_id))
                    member = guild.get_member(int(user_id_str))
                    if role and member and role in member.roles:
                        await member.remove_roles(role)
                        try:
                            dm = discord.Embed(
                                title=i18n.t(g_lang, "guest_dm_expired_t"),
                                description=i18n.t(g_lang, "guest_dm_expired_d", guild=guild.name),
                                color=discord.Color.orange()
                            )
                            await member.send(embed=dm)
                        except:
                            pass
                data_manager.remove_active_guest(guild.id, int(user_id_str))
            except Exception as e:
                print(f"Guest Expiry Loop Error: {e}")

    @guest_expiry_loop.before_loop
    async def before_guest_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Guests(bot))
