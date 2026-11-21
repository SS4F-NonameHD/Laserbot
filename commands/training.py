import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import re
import data_manager
import i18n

async def is_authorized_training(interaction: discord.Interaction) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if interaction.guild_id and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
        allowed = data_manager.get_allowed_roles(str(interaction.guild_id), "training")
        if set(allowed) & set([str(r.id) for r in interaction.user.roles]):
            return True
    return False

async def _check_dashboard_auth(interaction: discord.Interaction) -> bool:
    if not await is_authorized_training(interaction):
        await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)
        return False
    return True

async def get_upcoming_tournaments(guild: discord.Guild, training_date: datetime, lang: str):
    try:
        conn = data_manager.get_main_db_connection()
        c = conn.cursor()
        c.execute("SELECT custom_id, channel_id, message_id FROM tournament_events WHERE guild_id=%s ORDER BY custom_id DESC LIMIT 30", (str(guild.id),))
        rows = c.fetchall()
        c.close(); conn.close()
        upcoming = []
        two_weeks_later = training_date + timedelta(days=14)
        for _, ch_id, msg_id in rows:
            try:
                ch = guild.get_channel(int(ch_id)) or await guild.fetch_channel(int(ch_id))
                msg = await ch.fetch_message(int(msg_id))
                if not msg.embeds:
                    continue
                emb = msg.embeds[0]
                if emb.title and emb.title.startswith("❌"):
                    continue

                term_str = ""
                for f in emb.fields:
                    if "📅" in f.name or any(k in f.name.lower() for k in ["termin", "date", "termín", "data"]):
                        term_str = f.value
                        break

                if term_str:
                    m = re.search(r'(\d{1,2})\.(\d{1,2})\.?(\d{2,4})?', term_str)
                    if m:
                        y = datetime.now().year
                        if m.group(3):
                            y_str = m.group(3)
                            y = int(y_str) if len(y_str) == 4 else 2000 + int(y_str)
                        t_date = datetime(y, int(m.group(2)), int(m.group(1)))
                        if training_date.date() <= t_date.date() <= two_weeks_later.date():
                            clean_title = emb.title.replace('\u200b', '').strip()
                            if clean_title:
                                upcoming.append(i18n.t(lang, "train_preview_line", title=clean_title, date=t_date.strftime('%d.%m.%Y')))
            except:
                continue
        return upcoming
    except Exception as e:
        print(f"Preview Error: {e}")
        return []

class TrainingView(discord.ui.View):
    def __init__(self, lang: str = "en"):
        super().__init__(timeout=None)
        self.commit_button.label = i18n.t(lang, "btn_commit")
        self.maybe_button.label = i18n.t(lang, "btn_maybe")
        self.reject_button.label = i18n.t(lang, "btn_cancel")
        self.note_button.label = i18n.t(lang, "btn_note")
        self.refresh_button.label = i18n.t(lang, "btn_refresh")

    def get_event_time(self, embed):
        try:
            m = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}:\d{2})', embed.title or "")
            if m:
                return datetime.strptime(m.group(1), "%d.%m.%Y %H:%M")
        except:
            pass
        return None

    def get_custom_id(self, embed):
        if not embed.footer or not embed.footer.text:
            return "Unknown"
        try:
            return embed.footer.text.split("|")[0].replace("ID: ", "").strip()
        except:
            return "Unknown"

    async def check_deadline(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0]
        event_time = self.get_event_time(embed)
        if not event_time:
            return True
        settings = data_manager.get_server_settings(interaction.guild_id)
        dl_hours = float(settings.get("training_deadline_hours", 30.5))
        deadline = event_time - timedelta(hours=dl_hours)
        if datetime.now() > deadline:
            u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
            for c in self.children:
                c.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(i18n.t(u_lang, "train_dl_passed", dl=deadline.strftime('%d.%m.%Y %H:%M')), ephemeral=True)
            return False
        return True

    async def check_participation_auth(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        allowed = data_manager.get_allowed_roles(guild_id, "training_participate")
        guest_role_id, _ = data_manager.get_guest_settings(interaction.guild_id)

        if not allowed:
            return True
        if isinstance(interaction.user, discord.Member):
            user_role_ids = [str(r.id) for r in interaction.user.roles]
            if set(allowed) & set(user_role_ids):
                return True
            if guest_role_id and str(guest_role_id) in user_role_ids:
                return True

        await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)
        return False

    async def update_embed(self, interaction_or_msg):
        msg = interaction_or_msg if isinstance(interaction_or_msg, discord.Message) else interaction_or_msg.message
        if not msg.embeds:
            return
        embed = msg.embeds[0]
        custom_id = self.get_custom_id(embed)
        guild = msg.guild
        guild_id = str(guild.id)
        lang = i18n.get_guild_lang(guild_id)
        settings = data_manager.get_server_settings(guild_id)
        team_role_id = settings.get("team_role_id")

        data = data_manager.get_training_participants(guild_id, custom_id)
        notes = data_manager.get_training_notes(guild_id, custom_id)
        freitext_lines = []

        def format_line(name, info):
            uid = str(info['user_id'])
            is_manual = info.get('manual', False)
            is_guest = False

            if uid.startswith("ext_"):
                is_guest = True
                for prefix in ("Gast: ", "Guest: "):
                    if name.startswith(prefix):
                        name = name[len(prefix):]
            elif uid.isdigit() and team_role_id:
                member = guild.get_member(int(uid))
                if member and not any(str(r.id) == str(team_role_id) for r in member.roles):
                    is_guest = True

            marks = []
            if is_manual: marks.append("Ⓜ️")
            if is_guest: marks.append("🇬")
            mark_str = f" {''.join(marks)}" if marks else ""

            note = notes.get(uid)
            asterisk = "*" if note else ""
            line = f"• **{name}**{asterisk}{mark_str}"

            if note:
                clean_note = note.replace('*', '').replace('`', '').replace('_', '').replace('\n', ' ')
                freitext_lines.append(f"**{name}:** {clean_note}")
            return line

        zusagen = [format_line(n, inf) for n, inf in data.items() if inf['status'] == "Zusagen"]
        vielleicht = [format_line(n, inf) for n, inf in data.items() if inf['status'] == "Vielleicht"]
        absagen = [format_line(n, inf) for n, inf in data.items() if inf['status'] == "Absagen"]
        interessiert = [format_line(n, inf) for n, inf in data.items() if inf['status'] == "Interessiert"]

        none_txt = i18n.t(lang, "none_list")
        fmt_list = lambda l: "\n".join(l) if l else none_txt

        static_fields = [f for f in embed.fields if not any(x in f.name for x in ["✅", "❔", "❌", "❓", "💬", "ℹ️"])]
        embed.clear_fields()
        for f in static_fields:
            embed.add_field(name=f.name, value=f.value, inline=f.inline)

        embed.add_field(name=i18n.t(lang, "train_fld_commit", count=len(zusagen)), value=fmt_list(zusagen), inline=True)
        embed.add_field(name=i18n.t(lang, "train_fld_maybe", count=len(vielleicht)), value=fmt_list(vielleicht), inline=True)
        embed.add_field(name=i18n.t(lang, "train_fld_cancel", count=len(absagen)), value=fmt_list(absagen), inline=True)

        if interessiert:
            embed.add_field(name=i18n.t(lang, "train_fld_interested", count=len(interessiert)), value=fmt_list(interessiert), inline=False)
        if freitext_lines:
            embed.add_field(name=i18n.t(lang, "train_fld_notes"), value="\n".join(freitext_lines), inline=False)
        embed.add_field(name=i18n.t(lang, "train_fld_legend"), value=i18n.t(lang, "train_legend_val"), inline=False)

        new_view = TrainingView(lang)
        if isinstance(interaction_or_msg, discord.Message):
            await msg.edit(embed=embed, view=new_view)
        elif interaction_or_msg.response.is_done():
            await interaction_or_msg.edit_original_response(embed=embed, view=new_view)
        else:
            await interaction_or_msg.response.edit_message(embed=embed, view=new_view)

    async def set_status(self, interaction: discord.Interaction, status: str):
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        if isinstance(interaction.user, discord.Member) and data_manager.is_member_observer(interaction.user):
            await interaction.response.send_message(i18n.t(u_lang, "observer_blocked"), ephemeral=True)
            return

        if not await self.check_deadline(interaction):
            return
        if not await self.check_participation_auth(interaction):
            return

        settings = data_manager.get_server_settings(interaction.guild_id)
        team_role_id = settings.get("team_role_id")
        is_team_member = True
        if team_role_id and isinstance(interaction.user, discord.Member):
            is_team_member = any(str(r.id) == str(team_role_id) for r in interaction.user.roles)

        cid = self.get_custom_id(interaction.message.embeds[0])
        final_status = status

        if not is_team_member and status == "Zusagen":
            participants = data_manager.get_training_participants(interaction.guild_id, cid)
            already_approved = any(
                str(info['user_id']) == str(interaction.user.id) and info['status'] == "Zusagen"
                for info in participants.values()
            )
            if not already_approved:
                final_status = "Interessiert"

        data_manager.set_training_status(
            interaction.guild_id,
            cid,
            interaction.user.id,
            interaction.user.name,
            interaction.user.display_name,
            interaction.message.embeds[0].title,
            final_status,
            manual=False
        )
        await self.update_embed(interaction)

        if not is_team_member and final_status == "Interessiert" and status == "Zusagen":
            await interaction.followup.send(i18n.t(u_lang, "train_guest_queued"), ephemeral=True)

    @discord.ui.button(label="Commit", style=discord.ButtonStyle.success, emoji="✅", custom_id="train_commit")
    async def commit_button(self, i: discord.Interaction, b: discord.ui.Button):
        await self.set_status(i, "Zusagen")

    @discord.ui.button(label="Maybe", style=discord.ButtonStyle.secondary, emoji="❔", custom_id="train_maybe")
    async def maybe_button(self, i: discord.Interaction, b: discord.ui.Button):
        await self.set_status(i, "Vielleicht")

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="❌", custom_id="train_cancel")
    async def reject_button(self, i: discord.Interaction, b: discord.ui.Button):
        await self.set_status(i, "Absagen")

    @discord.ui.button(label="Note", style=discord.ButtonStyle.primary, emoji="💬", custom_id="train_note")
    async def note_button(self, i: discord.Interaction, b: discord.ui.Button):
        u_lang = i18n.get_interaction_lang(i, prefer_guild=False)
        if isinstance(i.user, discord.Member) and data_manager.is_member_observer(i.user):
            await i.response.send_message(i18n.t(u_lang, "observer_blocked"), ephemeral=True)
            return
        if not await self.check_deadline(i):
            return
        if not await self.check_participation_auth(i):
            return

        cid = self.get_custom_id(i.message.embeds[0])
        data = data_manager.get_training_participants(i.guild_id, cid)
        if str(i.user.id) not in [str(info['user_id']) for info in data.values()]:
            await i.response.send_message(i18n.t(u_lang, "train_note_need_status"), ephemeral=True)
            return

        await i.response.send_modal(NoteModal(str(i.guild_id), cid, i.message))

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="btn_refresh_training")
    async def refresh_button(self, i: discord.Interaction, b: discord.ui.Button):
        await self.update_embed(i)

class NoteModal(discord.ui.Modal, title="Note"):
    note = discord.ui.TextInput(label="Note (max 50 chars, empty = clear)", style=discord.TextStyle.short, required=False, max_length=50)

    def __init__(self, guild_id, custom_id, message):
        super().__init__()
        self.guild_id = guild_id
        self.custom_id = custom_id
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        if not self.note.value.strip():
            data_manager.delete_training_note(self.guild_id, self.custom_id, str(interaction.user.id))
            msg = "✅ Note cleared!"
        else:
            data_manager.set_training_note(self.guild_id, self.custom_id, str(interaction.user.id), self.note.value.strip())
            msg = "✅ Note saved!"
        await TrainingView(i18n.get_guild_lang(self.guild_id)).update_embed(self.message)
        await interaction.response.send_message(msg, ephemeral=True)

class CreateTrainingModal(discord.ui.Modal, title="New Training"):
    datum = discord.ui.TextInput(label="Date (DD.MM.YYYY)", placeholder="12.11.2026", required=True)
    uhrzeit = discord.ui.TextInput(label="Time (HH:MM)", placeholder="19:00", required=True)
    beschreibung = discord.ui.TextInput(label="Description (optional)", style=discord.TextStyle.paragraph, required=False)

    def __init__(self, image_url: str = None):
        super().__init__()
        self.image_url = image_url

    async def on_submit(self, interaction: discord.Interaction):
        if not await _check_dashboard_auth(interaction):
            return
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        settings = data_manager.get_server_settings(interaction.guild_id)
        g_lang = settings["language"]

        ch_id = settings.get("training_channel_id")
        ch = interaction.guild.get_channel(int(ch_id)) if ch_id else None
        if not ch:
            await interaction.response.send_message(i18n.t(u_lang, "train_ch_missing"), ephemeral=True)
            return

        try:
            pt = datetime.strptime(f"{self.datum.value.strip()} {self.uhrzeit.value.strip()}", "%d.%m.%Y %H:%M")
        except ValueError:
            await interaction.response.send_message("❌ Invalid format! Use DD.MM.YYYY and HH:MM.", ephemeral=True)
            return
        if pt < datetime.now():
            await interaction.response.send_message("❌ Date cannot be in the past.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        cid = data_manager.get_next_event_id(interaction.guild_id, pt.year, "trainings")
        dl_hours = float(settings.get("training_deadline_hours", 30.5))
        dl = pt - timedelta(hours=dl_hours)

        embed = discord.Embed(
            title=f"Training: {pt.strftime('%d.%m.%Y %H:%M')}",
            description=self.beschreibung.value or "",
            color=discord.Color.green()
        )
        if self.image_url:
            embed.set_image(url=self.image_url)

        embed.set_footer(text=i18n.t(g_lang, "train_footer", cid=cid, dl=dl.strftime('%d.%m.%Y %H:%M'), hours=dl_hours))

        upcoming = await get_upcoming_tournaments(interaction.guild, pt, g_lang)
        if upcoming:
            embed.add_field(name=i18n.t(g_lang, "train_preview_field"), value="\n".join(upcoming), inline=False)

        none_txt = i18n.t(g_lang, "none_list")
        embed.add_field(name=i18n.t(g_lang, "train_fld_commit", count=0), value=none_txt, inline=True)
        embed.add_field(name=i18n.t(g_lang, "train_fld_maybe", count=0), value=none_txt, inline=True)
        embed.add_field(name=i18n.t(g_lang, "train_fld_cancel", count=0), value=none_txt, inline=True)
        embed.add_field(name=i18n.t(g_lang, "train_fld_legend"), value=i18n.t(g_lang, "train_legend_val"), inline=False)

        view = TrainingView(g_lang)
        msg = await ch.send(embed=embed, view=view)
        data_manager.save_training_event(embed.title, cid, interaction.guild_id, ch.id, msg.id)

        # Automatische Abwesenheiten nur für echte Mitglieder dieses Servers eintragen
        absences = data_manager.get_absences_for_date(pt)
        if absences:
            applied = False
            for uid, reason in absences:
                if not str(uid).isdigit():
                    continue
                member = interaction.guild.get_member(int(uid))
                if not member or data_manager.is_member_observer(member):
                    continue
                data_manager.set_training_status(interaction.guild_id, cid, uid, member.name, member.display_name, embed.title, "Absagen", manual=False)
                data_manager.set_training_note(interaction.guild_id, cid, uid, reason)
                applied = True
            if applied:
                await view.update_embed(msg)

        await interaction.followup.send(f"✅ Training **{cid}** created in {ch.mention}!", ephemeral=True)

class EditTrainingModal(discord.ui.Modal, title="Edit Training"):
    datum = discord.ui.TextInput(label="New Date (empty = keep)", placeholder="DD.MM.YYYY", required=False)
    uhrzeit = discord.ui.TextInput(label="New Time (empty = keep)", placeholder="HH:MM", required=False)
    beschreibung = discord.ui.TextInput(label="New Description", style=discord.TextStyle.paragraph, required=False)
    bild_loeschen = discord.ui.TextInput(label="Remove image? ('yes')", placeholder="no", required=False)

    def __init__(self, event_data, guild, image_url: str = None):
        super().__init__()
        self.event_data = event_data
        self.guild = guild
        self.image_url = image_url

    async def on_submit(self, interaction: discord.Interaction):
        if not await _check_dashboard_auth(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            ch = self.guild.get_channel(int(self.event_data[0])) or await self.guild.fetch_channel(int(self.event_data[0]))
            msg = await ch.fetch_message(int(self.event_data[1]))
        except:
            await interaction.followup.send("❌ Training message not found.", ephemeral=True)
            return

        embed = msg.embeds[0]
        old_title = embed.title
        cid = self.event_data[2]
        settings = data_manager.get_server_settings(self.guild.id)
        g_lang = settings["language"]

        if self.beschreibung.value:
            embed.description = self.beschreibung.value

        if self.bild_loeschen.value and self.bild_loeschen.value.strip().lower() in ('ja', 'yes', 'j', 'y', 'ano', 'si', 'sì'):
            embed.set_image(url=None)
        elif self.image_url:
            embed.set_image(url=self.image_url)

        if self.datum.value or self.uhrzeit.value:
            m = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})\s+(\d{1,2}:\d{2})', old_title)
            cur_dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d.%m.%Y %H:%M") if m else datetime.now()
            new_d = self.datum.value.strip() if self.datum.value.strip() else cur_dt.strftime("%d.%m.%Y")
            new_t = self.uhrzeit.value.strip() if self.uhrzeit.value.strip() else cur_dt.strftime("%H:%M")
            try:
                new_st = datetime.strptime(f"{new_d} {new_t}", "%d.%m.%Y %H:%M")
            except ValueError:
                await interaction.followup.send("❌ Invalid date/time format!", ephemeral=True)
                return

            new_title = f"Training: {new_st.strftime('%d.%m.%Y %H:%M')}"
            conn = data_manager.get_main_db_connection(); c = conn.cursor()
            c.execute("UPDATE training_events SET training_id=%s WHERE guild_id=%s AND custom_id=%s", (new_title, str(self.guild.id), cid))
            c.execute("UPDATE trainings SET training_id=%s WHERE guild_id=%s AND custom_id=%s", (new_title, str(self.guild.id), cid))
            conn.commit(); c.close(); conn.close()

            dl_hours = float(settings.get("training_deadline_hours", 30.5))
            new_dl = new_st - timedelta(hours=dl_hours)
            embed.title = new_title
            embed.set_footer(text=i18n.t(g_lang, "train_footer", cid=cid, dl=new_dl.strftime('%d.%m.%Y %H:%M'), hours=dl_hours))

            upcoming = await get_upcoming_tournaments(self.guild, new_st, g_lang)
            embed.clear_fields()
            if upcoming:
                embed.add_field(name=i18n.t(g_lang, "train_preview_field"), value="\n".join(upcoming), inline=False)

            await msg.edit(embed=embed)
            await TrainingView(g_lang).update_embed(msg)
        else:
            await msg.edit(embed=embed)

        await interaction.followup.send("✅ Training updated!", ephemeral=True)

class GuestAddModal(discord.ui.Modal, title="Add External Guest"):
    guest_name = discord.ui.TextInput(label="Guest Name", required=True, max_length=50)

    def __init__(self, guild_id, custom_id, event_title, message):
        super().__init__()
        self.guild_id = guild_id
        self.custom_id = custom_id
        self.event_title = event_title
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        if not await _check_dashboard_auth(interaction):
            return
        name_clean = self.guest_name.value.strip()
        guest_id = f"ext_{name_clean}"
        data_manager.set_training_status(self.guild_id, self.custom_id, guest_id, name_clean, f"Guest: {name_clean}", self.event_title, "Zusagen", manual=True)
        if self.message:
            await TrainingView(i18n.get_guild_lang(self.guild_id)).update_embed(self.message)
        await interaction.response.send_message(f"✅ Guest **{name_clean}** added.", ephemeral=True)

class GuestRemoveSelect(discord.ui.Select):
    def __init__(self, guests, guild_id, custom_id, message):
        options = []
        seen = set()
        for uid, name in guests:
            if uid in seen: continue
            seen.add(uid)
            options.append(discord.SelectOption(label=name[:90], value=str(uid)[:100], emoji="🗑️"))
            if len(options) >= 25: break
        super().__init__(placeholder="Select guest to remove...", options=options)
        self.guild_id = guild_id
        self.custom_id = custom_id
        self.message = message

    async def callback(self, interaction: discord.Interaction):
        if not await _check_dashboard_auth(interaction):
            return
        data_manager.delete_training_entry(self.guild_id, self.custom_id, self.values[0])
        if self.message:
            await TrainingView(i18n.get_guild_lang(self.guild_id)).update_embed(self.message)
        await interaction.response.send_message("✅ Guest removed.", ephemeral=True)

class ManualStatusSelect(discord.ui.Select):
    def __init__(self, member, guild_id, custom_id, event_title, message):
        options = [
            discord.SelectOption(label="Commit (Confirmed)", value="Zusagen", emoji="✅"),
            discord.SelectOption(label="Interested / Guest", value="Interessiert", emoji="❓"),
            discord.SelectOption(label="Maybe", value="Vielleicht", emoji="❔"),
            discord.SelectOption(label="Decline", value="Absagen", emoji="❌"),
            discord.SelectOption(label="Delete Note", value="DeleteNote", emoji="💬"),
            discord.SelectOption(label="Remove Entry Completely", value="Delete", emoji="🗑️")
        ]
        super().__init__(placeholder=f"Action for {member.display_name[:50]}...", options=options)
        self.member = member
        self.guild_id = str(guild_id)
        self.custom_id = custom_id
        self.event_title = event_title
        self.message = message

    async def callback(self, interaction: discord.Interaction):
        if not await _check_dashboard_auth(interaction):
            return

        if self.values[0] == "Delete":
            data_manager.delete_training_entry(self.guild_id, self.custom_id, str(self.member.id))
            data_manager.delete_training_note(self.guild_id, self.custom_id, str(self.member.id))
            msg_text = f"✅ **{self.member.display_name}** removed."
        elif self.values[0] == "DeleteNote":
            allowed_mod = data_manager.get_allowed_roles(self.guild_id, "training_delete_notes")
            user_roles = [str(r.id) for r in interaction.user.roles] if isinstance(interaction.user, discord.Member) else []
            is_admin = interaction.user.id in data_manager.DEVELOPER_IDS or (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator)
            if not is_admin and not (set(allowed_mod) & set(user_roles)):
                await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)
                return
            data_manager.delete_training_note(self.guild_id, self.custom_id, str(self.member.id))
            msg_text = f"✅ Note of **{self.member.display_name}** deleted."
        else:
            data_manager.set_training_status(self.guild_id, self.custom_id, self.member.id, self.member.name, self.member.display_name, self.event_title, self.values[0], manual=True)
            msg_text = f"✅ Status for **{self.member.display_name}** updated."

        if self.message:
            await TrainingView(i18n.get_guild_lang(self.guild_id)).update_embed(self.message)
        await interaction.response.send_message(msg_text, ephemeral=True)

class ParticipantManageView(discord.ui.View):
    def __init__(self, event_data, guild):
        super().__init__(timeout=120)
        self.event_data = event_data
        self.guild = guild
        self.custom_id = event_data[2]
        self.event_title = event_data[4]

    async def get_message(self):
        try:
            ch = self.guild.get_channel(int(self.event_data[0])) or await self.guild.fetch_channel(int(self.event_data[0]))
            return await ch.fetch_message(int(self.event_data[1]))
        except:
            return None

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="1. Select server member...", row=0)
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if not await _check_dashboard_auth(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        msg = await self.get_message()
        member = select.values[0]
        v = discord.ui.View()
        v.add_item(ManualStatusSelect(member, interaction.guild_id, self.custom_id, self.event_title, msg))
        await interaction.followup.send(f"Step 2: Select status for {member.mention}:", view=v, ephemeral=True)

    @discord.ui.button(label="Add External Guest", style=discord.ButtonStyle.success, emoji="➕", row=1)
    async def btn_add_guest(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _check_dashboard_auth(interaction):
            return
        msg = await self.get_message()
        await interaction.response.send_modal(GuestAddModal(interaction.guild_id, self.custom_id, self.event_title, msg))

    @discord.ui.button(label="Remove External Guest", style=discord.ButtonStyle.danger, emoji="➖", row=1)
    async def btn_remove_guest(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _check_dashboard_auth(interaction):
            return
        msg = await self.get_message()
        parts = data_manager.get_training_participants(interaction.guild_id, self.custom_id)
        guests = [(info['user_id'], name) for name, info in parts.items() if str(info['user_id']).startswith("ext_")]
        if not guests:
            await interaction.response.send_message("❌ No manual external guests found.", ephemeral=True)
            return
        v = discord.ui.View()
        v.add_item(GuestRemoveSelect(guests, interaction.guild_id, self.custom_id, msg))
        await interaction.response.send_message("Select guest to remove:", view=v, ephemeral=True)

class GuestDurationModal(discord.ui.Modal, title="Default Guest Role Duration"):
    days = discord.ui.TextInput(label="Duration in days (0 = permanent)", placeholder="14", required=True, max_length=4)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            d = max(0, int(self.days.value))
        except ValueError:
            await interaction.response.send_message("❌ Invalid number.", ephemeral=True)
            return
        data_manager.set_guest_settings(interaction.guild.id, default_days=d)
        await interaction.response.send_message(f"✅ Default guest duration set to **{d} days**.", ephemeral=True)

class GuestRoleAssignSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Grant Guest role to member...", max_values=1)

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        g_lang = i18n.get_guild_lang(interaction.guild_id)
        role_id, default_days = data_manager.get_guest_settings(interaction.guild.id)
        if not role_id:
            await interaction.response.send_message(i18n.t(interaction, "guest_not_cfg"), ephemeral=True)
            return
        role = interaction.guild.get_role(int(role_id))
        if not role:
            await interaction.response.send_message(i18n.t(interaction, "guest_not_cfg"), ephemeral=True)
            return

        expires_at = datetime.now() + timedelta(days=default_days) if default_days > 0 else datetime.now() + timedelta(days=3650)
        try:
            await member.add_roles(role)
            if default_days > 0:
                data_manager.add_active_guest(interaction.guild.id, member.id, expires_at)
            expiry_text = "Permanent" if default_days <= 0 else expires_at.strftime('%d.%m.%Y %H:%M')
            try:
                dm = discord.Embed(
                    title=i18n.t(g_lang, "guest_dm_approved_t"),
                    description=i18n.t(g_lang, "guest_dm_approved_d", guild=interaction.guild.name),
                    color=discord.Color.green()
                )
                if default_days > 0:
                    dm.add_field(name=i18n.t(g_lang, "guest_dm_exp"), value=expiry_text, inline=False)
                await member.send(embed=dm)
            except:
                pass
            await interaction.response.send_message(f"✅ Granted {role.mention} to {member.mention} ({expiry_text}).", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Missing role hierarchy permissions.", ephemeral=True)

class ActiveTrainingsSelect(discord.ui.Select):
    def __init__(self, action_type, options, image_url=None):
        placeholders = {
            "edit": "📝 Edit training...",
            "manage": "👥 Manage participants...",
            "cancel": "❌ Cancel training..."
        }
        super().__init__(placeholder=placeholders[action_type], options=options)
        self.action_type = action_type
        self.image_url = image_url

    async def callback(self, interaction: discord.Interaction):
        if not await _check_dashboard_auth(interaction):
            return
        event = data_manager.get_training_event_by_custom_id(interaction.guild_id, self.values[0])
        if not event:
            await interaction.response.send_message("❌ Event not found.", ephemeral=True)
            return

        if self.action_type == "edit":
            await interaction.response.send_modal(EditTrainingModal(event, interaction.guild, self.image_url))
        elif self.action_type == "manage":
            await interaction.response.send_message(f"👥 **Participant Manager** — {event[4]}", view=ParticipantManageView(event, interaction.guild), ephemeral=True)
        elif self.action_type == "cancel":
            await interaction.response.defer(ephemeral=True)
            try:
                g_lang = i18n.get_guild_lang(interaction.guild_id)
                ch = interaction.guild.get_channel(int(event[0])) or await interaction.guild.fetch_channel(int(event[0]))
                msg = await ch.fetch_message(int(event[1]))
                embed = msg.embeds[0]
                embed.color = discord.Color.red()
                prefix = i18n.t(g_lang, "train_canceled_prefix")
                if not embed.title.startswith("❌"):
                    embed.title = f"{prefix}{embed.title}"
                view = TrainingView(g_lang)
                for c in view.children:
                    c.disabled = True
                await msg.edit(embed=embed, view=view)
                await interaction.followup.send("✅ Training canceled.", ephemeral=True)
            except:
                await interaction.followup.send("❌ Message could not be found in channel.", ephemeral=True)

class TrainingMainMenu(discord.ui.View):
    def __init__(self, active_trainings, attached_image_url, is_manage_guests_auth=False):
        super().__init__(timeout=180)
        self.attached_image_url = attached_image_url

        def extract_id(item):
            nums = [int(p) for p in str(item[1]).split('-') if p.isdigit()]
            return nums if nums else [0]

        sorted_trainings = sorted(active_trainings, key=extract_id, reverse=True)
        opts = []
        seen_cids = set()
        for tid, cid in sorted_trainings:
            safe_cid = str(cid)
            if safe_cid in seen_cids:
                continue
            seen_cids.add(safe_cid)
            opts.append(discord.SelectOption(label=str(tid)[:90], description=f"ID: {safe_cid}", value=safe_cid))
            if len(opts) >= 25:
                break

        if opts:
            self.add_item(ActiveTrainingsSelect("edit", opts, self.attached_image_url))
            self.add_item(ActiveTrainingsSelect("manage", opts))
            self.add_item(ActiveTrainingsSelect("cancel", opts))
        if is_manage_guests_auth:
            self.add_item(GuestRoleAssignSelect())

    @discord.ui.button(label="New Training", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def btn_new(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _check_dashboard_auth(interaction):
            return
        await interaction.response.send_modal(CreateTrainingModal(self.attached_image_url))

    @discord.ui.button(label="Guest Duration", style=discord.ButtonStyle.secondary, emoji="⏱️", row=0)
    async def btn_guest_duration(self, interaction: discord.Interaction, button: discord.ui.Button):
        allowed = data_manager.get_allowed_roles(str(interaction.guild_id), "manage_guests")
        is_adm = interaction.user.id in data_manager.DEVELOPER_IDS or interaction.user.guild_permissions.administrator
        if not is_adm and not (allowed and set(allowed) & set([str(r.id) for r in interaction.user.roles])):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)
            return
        await interaction.response.send_modal(GuestDurationModal())

class Training(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TrainingView())
        if not self.training_reminder_loop.is_running():
            self.training_reminder_loop.start()

    async def cog_unload(self):
        self.training_reminder_loop.cancel()

    @tasks.loop(minutes=5)
    async def training_reminder_loop(self):
        all_events = data_manager.get_all_training_events()
        now = datetime.now()
        for guild_id, custom_id, title, channel_id, message_id, reminder_sent in all_events:
            if reminder_sent:
                continue
            settings = data_manager.get_server_settings(guild_id)
            rem_hours = float(settings.get("training_reminder_hours", 2.0))
            if rem_hours <= 0:
                continue

            m = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}:\d{2})', title or "")
            if not m:
                continue
            try:
                event_time = datetime.strptime(m.group(1), "%d.%m.%Y %H:%M")
            except:
                continue

            dl_hours = float(settings.get("training_deadline_hours", 30.5))
            deadline = event_time - timedelta(hours=dl_hours)

            if (deadline - timedelta(hours=rem_hours)) <= now < deadline:
                try:
                    ch = self.bot.get_channel(int(channel_id)) or await self.bot.fetch_channel(int(channel_id))
                    if not ch:
                        continue
                    msg = await ch.fetch_message(int(message_id))
                    guild = ch.guild
                    g_lang = settings["language"]

                    allowed_role_ids = data_manager.get_allowed_roles(str(guild.id), "training_participate")
                    team_role_id = settings.get("team_role_id")
                    guest_role_id = settings.get("guest_role_id")

                    participants_data = data_manager.get_training_participants(guild.id, custom_id)
                    confirmed_ids = {
                        str(info['user_id']) for info in participants_data.values()
                        if info['status'] in ("Zusagen", "Absagen", "Interessiert")
                    }

                    missing = []
                    for mem in guild.members:
                        if mem.bot or data_manager.is_member_observer(mem):
                            continue
                        u_roles = [str(r.id) for r in mem.roles]
                        if guest_role_id and str(guest_role_id) in u_roles:
                            continue

                        if allowed_role_ids:
                            has_auth = bool(set(allowed_role_ids) & set(u_roles))
                        elif team_role_id:
                            has_auth = str(team_role_id) in u_roles
                        else:
                            has_auth = False

                        if has_auth and str(mem.id) not in confirmed_ids:
                            missing.append(mem.mention)

                    if missing:
                        await ch.send(
                            i18n.t(g_lang, "train_reminder_msg", title=title, hours=rem_hours, mentions=", ".join(missing)),
                            reference=msg
                        )
                    data_manager.mark_training_reminder_sent(guild.id, custom_id)
                except Exception as e:
                    print(f"Training Reminder Error: {e}")

    @training_reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="training", description="Opens the Training Management Dashboard")
    @app_commands.describe(image="Optional image to attach when creating or editing a training")
    @app_commands.check(is_authorized_training)
    async def training(self, interaction: discord.Interaction, image: discord.Attachment = None):
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)

        image_url = image.url if image else None
        active_trainings = data_manager.get_active_trainings(interaction.guild_id)

        embed = discord.Embed(
            title=i18n.t(u_lang, "train_hub_title"),
            description=i18n.t(u_lang, "train_hub_desc"),
            color=discord.Color.blue()
        )
        allowed = data_manager.get_allowed_roles(str(interaction.guild_id), "manage_guests")
        is_guest_auth = (
            interaction.user.id in data_manager.DEVELOPER_IDS
            or interaction.user.guild_permissions.administrator
            or bool(allowed and set(allowed) & set([str(r.id) for r in interaction.user.roles]))
        )
        await interaction.followup.send(embed=embed, view=TrainingMainMenu(active_trainings, image_url, is_guest_auth), ephemeral=True)

    @training.error
    async def err(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Training(bot))
