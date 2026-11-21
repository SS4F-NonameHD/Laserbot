import discord
from discord import app_commands, ui
from discord.ext import commands
from datetime import datetime
import io
import data_manager
import i18n
from commands.setup import format_gdpr_report

async def is_authorized_profile(interaction: discord.Interaction) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if not interaction.guild_id:
        return True
    if isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
        allowed = data_manager.get_allowed_roles(str(interaction.guild_id), "profile")
        if not allowed:
            return True  # Standardmäßig für alle Spieler offen, sofern nicht eingeschränkt
        if set(allowed) & set([str(r.id) for r in interaction.user.roles]):
            return True
    return False

# --- SELF-SERVICE GDPR / DSGVO HELPER & VIEWS ---

async def handle_self_gdpr_export(interaction: discord.Interaction):
    lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
    is_dev = interaction.user.id in data_manager.DEVELOPER_IDS

    if not is_dev:
        allowed, next_time = data_manager.check_and_record_dsgvo_export(interaction.user.id, cooldown_hours=24)
        if not allowed and next_time:
            await interaction.response.send_message(
                i18n.t(lang, "gdpr_cooldown", time=next_time.strftime("%d.%m.%Y %H:%M")),
                ephemeral=True
            )
            return

    await interaction.response.defer(ephemeral=True)
    raw = data_manager.get_dsgvo_data(interaction.user.id)
    report_txt = format_gdpr_report(str(interaction.user.id), raw)
    file = discord.File(
        fp=io.BytesIO(report_txt.encode("utf-8")),
        filename=f"{data_manager.BOT_NAME}_GDPR_Data_{interaction.user.id}.txt"
    )
    await interaction.followup.send(i18n.t(lang, "gdpr_export_done"), file=file, ephemeral=True)

class EraseConfirmView(ui.View):
    def __init__(self, lang: str):
        super().__init__(timeout=60)
        self.lang = lang
        self.confirm_btn.label = i18n.t(lang, "gdpr_erase_btn_confirm")

    @ui.button(label="Confirm Erasure", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_btn(self, interaction: discord.Interaction, button: ui.Button):
        ok = data_manager.delete_all_user_data(interaction.user.id)
        if ok:
            await interaction.response.edit_message(content=i18n.t(self.lang, "gdpr_erase_done"), view=None)
        else:
            await interaction.response.edit_message(content=i18n.t(self.lang, "db_error"), view=None)

class SelfPrivacyView(ui.View):
    """Kompakte DSGVO-Self-Service-View für /privacy (auch per DM nutzbar) und /legal."""
    def __init__(self, lang: str = "en"):
        super().__init__(timeout=180)
        self.lang = lang
        self.btn_exp.label = i18n.t(lang, "prof_btn_export")
        self.btn_del.label = i18n.t(lang, "prof_btn_erase")

    @ui.button(label="GDPR Data Export", style=discord.ButtonStyle.secondary, emoji="🗃️")
    async def btn_exp(self, interaction: discord.Interaction, button: ui.Button):
        await handle_self_gdpr_export(interaction)

    @ui.button(label="Delete All My Data", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def btn_del(self, interaction: discord.Interaction, button: ui.Button):
        lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        await interaction.response.send_message(i18n.t(lang, "gdpr_erase_prompt"), view=EraseConfirmView(lang), ephemeral=True)

# --- PROFIL MODALS & SELECTS ---

class AbsenceModal(ui.Modal):
    def __init__(self, lang: str):
        super().__init__(title=i18n.t(lang, "prof_abs_modal_title"))
        self.lang = lang
        self.start_str = ui.TextInput(label=i18n.t(lang, "prof_abs_start"), placeholder="DD.MM.YYYY", required=True, min_length=10, max_length=10)
        self.end_str = ui.TextInput(label=i18n.t(lang, "prof_abs_end"), placeholder="DD.MM.YYYY", required=True, min_length=10, max_length=10)
        self.reason = ui.TextInput(label=i18n.t(lang, "prof_abs_reason"), required=True, max_length=50)
        self.add_item(self.start_str)
        self.add_item(self.end_str)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            start_date = datetime.strptime(self.start_str.value, "%d.%m.%Y")
            end_date = datetime.strptime(self.end_str.value, "%d.%m.%Y").replace(hour=23, minute=59)
            if start_date > end_date:
                await interaction.response.send_message(i18n.t(self.lang, "prof_abs_err_order"), ephemeral=True)
                return
            if data_manager.add_absence(interaction.user.id, start_date, end_date, self.reason.value):
                await interaction.response.send_message(
                    i18n.t(self.lang, "prof_abs_saved", start=self.start_str.value, end=self.end_str.value),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(i18n.t(self.lang, "db_error"), ephemeral=True)
        except ValueError:
            await interaction.response.send_message(i18n.t(self.lang, "prof_abs_err_fmt"), ephemeral=True)

class AbsenceDeleteSelect(ui.Select):
    def __init__(self, absences, lang: str):
        self.lang = lang
        options = []
        for a_id, start, end, reason in absences[:25]:
            label = f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
            options.append(discord.SelectOption(label=label, description=reason[:50], value=str(a_id), emoji="🗑️"))
        super().__init__(placeholder=i18n.t(lang, "prof_abs_del_ph"), options=options, row=4)

    async def callback(self, interaction: discord.Interaction):
        if data_manager.delete_absence(self.values[0], interaction.user.id):
            await interaction.response.send_message(i18n.t(self.lang, "prof_abs_deleted"), ephemeral=True)
        else:
            await interaction.response.send_message(i18n.t(self.lang, "db_error"), ephemeral=True)

class PartnerSelectView(ui.View):
    def __init__(self, profile_view, original_interaction, lang: str):
        super().__init__(timeout=60)
        self.profile_view = profile_view
        self.original_interaction = original_interaction
        self.lang = lang

    @ui.select(cls=ui.UserSelect, placeholder="...", min_values=1, max_values=1)
    async def sel_user(self, interaction: discord.Interaction, select: ui.UserSelect):
        partner_id = str(select.values[0].id)
        data_manager.update_travel_profile(interaction.user.id, room_pref="double", partner_id=partner_id)
        await interaction.response.edit_message(
            content=i18n.t(self.lang, "prof_partner_saved", mention=select.values[0].mention),
            view=None
        )
        self.profile_view.build_buttons()
        try: await self.original_interaction.edit_original_response(view=self.profile_view)
        except: pass

class DefaultPassengerView(ui.View):
    def __init__(self, profile_view, original_interaction, lang: str):
        super().__init__(timeout=60)
        self.profile_view = profile_view
        self.original_interaction = original_interaction
        self.lang = lang

    @ui.select(cls=ui.UserSelect, placeholder="...", min_values=1, max_values=10, row=0)
    async def sel_pass(self, interaction: discord.Interaction, select: ui.UserSelect):
        p_ids = [str(u.id) for u in select.values]
        data_manager.update_travel_profile(interaction.user.id, default_passengers=",".join(p_ids))
        mentions = ", ".join([u.mention for u in select.values])
        await interaction.response.edit_message(
            content=i18n.t(self.lang, "prof_pass_saved", mentions=mentions),
            view=None
        )
        self.profile_view.build_buttons()
        try: await self.original_interaction.edit_original_response(view=self.profile_view)
        except: pass

    @ui.button(label="Clear List", style=discord.ButtonStyle.danger, row=1)
    async def clear_btn(self, interaction: discord.Interaction, button: ui.Button):
        data_manager.update_travel_profile(interaction.user.id, default_passengers="CLEAR")
        await interaction.response.edit_message(content=i18n.t(self.lang, "prof_pass_cleared"), view=None)
        self.profile_view.build_buttons()
        try: await self.original_interaction.edit_original_response(view=self.profile_view)
        except: pass

class ProfileView(ui.View):
    def __init__(self, guild_id, user_id, lang: str = "en", valid_absences=None):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user_id = user_id
        self.lang = lang
        self.valid_absences = valid_absences or []
        self.build_buttons()

    def build_buttons(self):
        self.clear_items()
        travel_prof = data_manager.get_travel_profile(self.user_id)

        if self.guild_id:
            is_cap = data_manager.get_captain_status(self.guild_id, self.user_id)
            btn_captain = ui.Button(
                label=i18n.t(self.lang, "prof_cap_on" if is_cap else "prof_cap_off"),
                style=discord.ButtonStyle.success if is_cap else discord.ButtonStyle.danger,
                emoji="👑", row=0
            )
            btn_captain.callback = self.toggle_captain
            self.add_item(btn_captain)

        btn_absence = ui.Button(label=i18n.t(self.lang, "prof_btn_abs"), style=discord.ButtonStyle.primary, emoji="🌴", row=0)
        btn_absence.callback = self.open_absence_modal
        self.add_item(btn_absence)

        has_lic = travel_prof["has_license"]
        btn_lic = ui.Button(
            label=i18n.t(self.lang, "prof_lic_yes" if has_lic else "prof_lic_no"),
            style=discord.ButtonStyle.success if has_lic else discord.ButtonStyle.secondary,
            emoji="🚗", row=1
        )
        btn_lic.callback = self.toggle_license
        self.add_item(btn_lic)

        pref = travel_prof["room_pref"]
        if pref == "single":
            lbl_room, st_room = i18n.t(self.lang, "prof_room_single"), discord.ButtonStyle.primary
        elif pref == "double":
            lbl_room, st_room = i18n.t(self.lang, "prof_room_double"), discord.ButtonStyle.success
        else:
            lbl_room, st_room = i18n.t(self.lang, "prof_room_shared"), discord.ButtonStyle.secondary

        btn_room = ui.Button(label=lbl_room, style=st_room, emoji="🛏️", row=1)
        btn_room.callback = self.toggle_room
        self.add_item(btn_room)

        if self.guild_id:
            btn_partner = ui.Button(label=i18n.t(self.lang, "prof_btn_partner"), style=discord.ButtonStyle.secondary, emoji="👫", row=2)
            btn_partner.callback = self.open_partner_select
            self.add_item(btn_partner)

            btn_passengers = ui.Button(label=i18n.t(self.lang, "prof_btn_pass"), style=discord.ButtonStyle.secondary, emoji="👨‍👩‍👧‍👦", row=2)
            btn_passengers.callback = self.open_passenger_select
            self.add_item(btn_passengers)

        # Row 3: GDPR Self-Service
        btn_export = ui.Button(label=i18n.t(self.lang, "prof_btn_export"), style=discord.ButtonStyle.secondary, emoji="🗃️", row=3)
        btn_export.callback = handle_self_gdpr_export
        self.add_item(btn_export)

        btn_erase = ui.Button(label=i18n.t(self.lang, "prof_btn_erase"), style=discord.ButtonStyle.danger, emoji="🗑️", row=3)
        btn_erase.callback = self.open_erase_confirm
        self.add_item(btn_erase)

        if self.valid_absences:
            self.add_item(AbsenceDeleteSelect(self.valid_absences, self.lang))

    async def refresh_view(self, interaction: discord.Interaction):
        self.build_buttons()
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=self)
        else:
            await interaction.edit_original_response(view=self)

    async def toggle_captain(self, interaction: discord.Interaction):
        data_manager.toggle_captain_status(self.guild_id, interaction.user.id)
        await self.refresh_view(interaction)

    async def toggle_license(self, interaction: discord.Interaction):
        current = data_manager.get_travel_profile(interaction.user.id)
        data_manager.update_travel_profile(interaction.user.id, has_license=not current["has_license"])
        await self.refresh_view(interaction)

    async def toggle_room(self, interaction: discord.Interaction):
        current = data_manager.get_travel_profile(interaction.user.id)
        next_pref = "single" if current["room_pref"] in ("shared", "double") else "shared"
        data_manager.update_travel_profile(interaction.user.id, room_pref=next_pref, partner_id="CLEAR")
        await self.refresh_view(interaction)

    async def open_partner_select(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            i18n.t(self.lang, "prof_partner_prompt"),
            view=PartnerSelectView(self, interaction, self.lang),
            ephemeral=True
        )

    async def open_passenger_select(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            i18n.t(self.lang, "prof_pass_prompt"),
            view=DefaultPassengerView(self, interaction, self.lang),
            ephemeral=True
        )

    async def open_absence_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AbsenceModal(self.lang))

    async def open_erase_confirm(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            i18n.t(self.lang, "gdpr_erase_prompt"),
            view=EraseConfirmView(self.lang),
            ephemeral=True
        )

def build_profile_dashboard(user, guild_id, lang: str):
    embed = discord.Embed(
        title=i18n.t(lang, "prof_title", name=user.display_name),
        description=i18n.t(lang, "prof_desc"),
        color=discord.Color.dark_theme()
    )
    absences = data_manager.get_user_absences(user.id)
    today = datetime.now().date()
    valid_absences = [a for a in absences if a[2].date() >= today]

    if valid_absences:
        abs_text = "\n".join([f"• **{s.strftime('%d.%m.%Y')} – {e.strftime('%d.%m.%Y')}** ({r})" for _, s, e, r in valid_absences])
    else:
        abs_text = i18n.t(lang, "prof_abs_none")
    embed.add_field(name=i18n.t(lang, "prof_abs_title"), value=abs_text, inline=False)

    view = ProfileView(guild_id, user.id, lang, valid_absences)
    return embed, view

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Opens your personal profile, travel preferences, absences & GDPR controls")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_authorized_profile)
    async def profile(self, interaction: discord.Interaction):
        lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        embed, view = build_profile_dashboard(interaction.user, interaction.guild_id, lang)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="privacy", description="Self-service GDPR Data Export (Art. 15) and Account Data Erasure (Art. 17)")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def privacy(self, interaction: discord.Interaction):
        lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        embed = discord.Embed(
            title=f"🔒 GDPR / Privacy Self-Service — {data_manager.BOT_NAME}",
            description=i18n.t(lang, "legal_desc"),
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, view=SelfPrivacyView(lang), ephemeral=True)

    @profile.error
    async def error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Profile(bot))
