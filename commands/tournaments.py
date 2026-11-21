import discord
from discord import ui, app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import urllib.parse
import re
import io
import asyncio
import data_manager
import i18n

async def check_tournament_hub_auth(interaction: discord.Interaction) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if not interaction.guild_id or not isinstance(interaction.user, discord.Member):
        return False
    if interaction.user.guild_permissions.administrator:
        return True
    allowed_create = data_manager.get_allowed_roles(str(interaction.guild_id), "tournament")
    allowed_manage = data_manager.get_allowed_roles(str(interaction.guild_id), "tournament_participants")
    user_roles = [str(r.id) for r in interaction.user.roles]
    return bool((set(allowed_create) | set(allowed_manage)) & set(user_roles))

def is_developer(interaction: discord.Interaction) -> bool:
    return interaction.user.id in data_manager.DEVELOPER_IDS

def get_recent_tournaments(guild_id):
    try:
        conn = data_manager.get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT custom_id, event_title, channel_id, message_id FROM tournament_events WHERE guild_id=%s", (str(guild_id),))
        rows = c.fetchall()
        c.close(); conn.close()
        return rows
    except:
        return []

async def resolve_tournament_category_and_overwrites(guild: discord.Guild):
    """Ermittelt die konfigurierte Turnier-Kategorie und Teamrollen-Berechtigungen für neue Turnier-Kanäle."""
    settings = data_manager.get_server_settings(guild.id)
    cat = None
    cat_id = settings.get("tournament_category_id")
    if cat_id:
        cat = guild.get_channel(int(cat_id))
    if not cat:
        cat = discord.utils.get(guild.categories, name="Tournaments")
        if not cat:
            cat = await guild.create_category("Tournaments")

    ow = {}
    team_role_id = settings.get("team_role_id")
    if team_role_id:
        team_role = guild.get_role(int(team_role_id))
        if team_role:
            ow[guild.default_role] = discord.PermissionOverwrite(read_messages=False)
            ow[team_role] = discord.PermissionOverwrite(read_messages=True)
            if guild.me:
                ow[guild.me] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
    return cat, ow

def extract_ort(emb):
    for f in emb.fields:
        if "📍" in f.name or any(k in f.name.lower() for k in ["ort", "location", "místo", "luogo"]):
            return re.sub(r'\[(.*?)\].*', r'\1', f.value)
    return ""

def extract_dl(emb, default_dl=48):
    try:
        if not emb.footer or not emb.footer.text:
            return default_dl
        match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})\s+(\d{1,2}:\d{2})', emb.footer.text)
        if not match:
            return default_dl
        dl = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%d.%m.%Y %H:%M")
        for f in emb.fields:
            if "📅" in f.name or any(k in f.name.lower() for k in ["termin", "date", "termín", "data"]):
                val = f.value.split(',')[0]
                st_match = re.search(r'(\d{1,2})\.(\d{1,2})\.?(\d{4})?', val)
                t_match = re.search(r'(\d{1,2}:\d{2})', f.value)
                if st_match and t_match:
                    y = st_match.group(3) or datetime.now().year
                    st = datetime.strptime(f"{st_match.group(1)}.{st_match.group(2)}.{y} {t_match.group(1)}", "%d.%m.%Y %H:%M")
                    return max(0, int((st - dl).total_seconds() / 3600))
    except:
        pass
    return default_dl

def extract_times(emb):
    d, t, e = "", "", ""
    for f in emb.fields:
        if "📅" in f.name or any(k in f.name.lower() for k in ["termin", "date", "termín", "data"]):
            val = f.value.replace(" Uhr", "")
            m_new = re.search(r'(.*?),\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})', val)
            if m_new:
                d, t, e = m_new.group(1), m_new.group(2), m_new.group(3)
    return d, t, e

def get_start_info(date_str, time_str):
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.?(\d{2,4})?', date_str)
    if not match:
        return None, None
    d, m = int(match.group(1)), int(match.group(2))
    year_match = re.search(r'(\d{4})', date_str)
    y = int(year_match.group(1)) if year_match else datetime.now().year
    try:
        st = datetime.strptime(f"{d:02d}.{m:02d}.{y} {time_str.strip()}", "%d.%m.%Y %H:%M")
        return st, y
    except:
        return None, None

def parse_dates_for_ics(date_val, time_val):
    year_match = re.search(r'(\d{4})', date_val)
    year = int(year_match.group(1)) if year_match else datetime.now().year
    found_dates = []
    if "," in date_val:
        for d in date_val.split(","):
            m = re.search(r'(\d{1,2})\.(\d{1,2})', d)
            if m:
                found_dates.append(datetime.strptime(f"{m.group(1)}.{m.group(2)}.{year} {time_val}", "%d.%m.%Y %H:%M"))
    elif " - " in date_val:
        parts = date_val.split(" - ")
        m1 = re.search(r'(\d{1,2})\.(\d{1,2})', parts[0])
        m2 = re.search(r'(\d{1,2})\.(\d{1,2})', parts[1])
        if m1 and m2:
            curr = datetime.strptime(f"{m1.group(1)}.{m1.group(2)}.{year} {time_val}", "%d.%m.%Y %H:%M")
            end = datetime.strptime(f"{m2.group(1)}.{m2.group(2)}.{year} {time_val}", "%d.%m.%Y %H:%M")
            while curr <= end:
                found_dates.append(curr)
                curr += timedelta(days=1)
    else:
        m = re.search(r'(\d{1,2})\.(\d{1,2})', date_val)
        if m:
            found_dates.append(datetime.strptime(f"{m.group(1)}.{m.group(2)}.{year} {time_val}", "%d.%m.%Y %H:%M"))
    return found_dates

async def apply_tournament_absences(guild: discord.Guild, cid: str, title: str, start_dt: datetime, msg: discord.Message):
    absences = data_manager.get_absences_for_date(start_dt)
    if not absences:
        return
    applied = False
    for uid, reason in absences:
        if not str(uid).isdigit():
            continue
        member = guild.get_member(int(uid))
        if not member or data_manager.is_member_observer(member):
            continue
        data_manager.set_tournament_status(guild.id, cid, uid, member.name, member.display_name, title, "Absagen", manual=False)
        data_manager.set_tournament_note(guild.id, cid, uid, reason)
        applied = True
    if applied:
        await TournamentView(i18n.get_guild_lang(guild.id)).update_embed(msg)

# --- ERSTELLUNG & BEARBEITUNG ---

class TournamentDateModal(ui.Modal):
    def __init__(self, metadata, mode):
        t_map = {"single": "Single Day", "range": "Date Range", "series": "Series", "add_playday": "Add Series Playday"}
        super().__init__(title=t_map.get(mode, "Schedule"))
        self.meta = metadata
        self.mode = mode

        self.datum_input = ui.TextInput(label="Date / Date Range (e.g. 14.11.2026)", required=True)
        self.uhrzeit_input = ui.TextInput(label="Start Time (HH:MM)", placeholder="09:00", required=True)
        self.end_uhrzeit_input = ui.TextInput(label="End Time (HH:MM)", placeholder="19:00", required=True)
        self.add_item(self.datum_input)
        self.add_item(self.uhrzeit_input)
        self.add_item(self.end_uhrzeit_input)

        if mode == "add_playday":
            self.opt_title = ui.TextInput(label="Custom Title (optional)", required=False)
            self.opt_desc = ui.TextInput(label="Description (optional)", style=discord.TextStyle.paragraph, required=False)
            self.add_item(self.opt_title)
            self.add_item(self.opt_desc)

    async def on_submit(self, i: discord.Interaction):
        st, year = get_start_info(self.datum_input.value, self.uhrzeit_input.value)
        if not st:
            await i.response.send_message("❌ Invalid date or time format.", ephemeral=True)
            return

        await i.response.defer(thinking=True, ephemeral=True)
        cog = i.client.get_cog("Tournaments")
        g_lang = i18n.get_guild_lang(i.guild.id)

        if self.mode == "add_playday":
            cid = data_manager.get_next_sub_id(i.guild.id, self.meta['base_cid'])
            final_title = self.opt_title.value.strip() if self.opt_title.value.strip() else self.meta['title']
            final_desc = self.opt_desc.value if self.opt_desc.value else self.meta['description']

            embed = cog.create_tournament_embed(i.guild.id, final_title, final_desc, st, self.datum_input.value, self.uhrzeit_input.value, self.end_uhrzeit_input.value, self.meta['ort'], self.meta['deadline_stunden'], cid)
            ch = i.guild.get_channel(int(self.meta['channel_id'])) or await i.guild.fetch_channel(int(self.meta['channel_id']))
            msg = await ch.send(embed=embed, view=TournamentView(g_lang))
            data_manager.save_tournament_event(final_title, cid, i.guild.id, ch.id, msg.id)
            await apply_tournament_absences(i.guild, cid, final_title, st, msg)
            await i.followup.send(f"✅ Playday **{cid}** added to {ch.mention}!", ephemeral=True)
        else:
            cid = data_manager.get_next_event_id(i.guild.id, year, "tournaments")
            title_with_marker = self.meta['title'] + ("\u200b" if self.mode == "series" else "")
            embed = cog.create_tournament_embed(i.guild.id, title_with_marker, self.meta['description'], st, self.datum_input.value, self.uhrzeit_input.value, self.end_uhrzeit_input.value, self.meta['ort'], self.meta['deadline_stunden'], cid)

            if self.meta.get('channel_name'):
                cat, ow = await resolve_tournament_category_and_overwrites(i.guild)
                ch = await i.guild.create_text_channel(name=self.meta['channel_name'], category=cat, overwrites=ow)
            else:
                ch = i.channel

            msg = await ch.send(embed=embed, view=TournamentView(g_lang))
            try:
                await msg.pin()
            except:
                pass

            data_manager.save_tournament_event(title_with_marker, cid, i.guild.id, ch.id, msg.id)
            await apply_tournament_absences(i.guild, cid, title_with_marker, st, msg)
            await i.followup.send(f"✅ Tournament **{cid}** created in {ch.mention}!", ephemeral=True)

class AddPlaydayHelperView(ui.View):
    def __init__(self, meta):
        super().__init__(timeout=120)
        self.meta = meta

    @ui.button(label="Enter Schedule Details", style=discord.ButtonStyle.success, emoji="📅")
    async def go(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(TournamentDateModal(self.meta, "add_playday"))

class AddPlaydaySelect(ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="➕ Add playday to series...", options=options)

    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        cid, ch_id = self.values[0].split('|')
        evt = data_manager.get_tournament_event_by_custom_id(i.guild.id, cid)
        default_dl = int(data_manager.get_server_settings(i.guild.id).get("tournament_deadline_hours", 48))
        try:
            ch = i.guild.get_channel(int(ch_id)) or await i.guild.fetch_channel(int(ch_id))
            msg = await ch.fetch_message(int(evt[1]))
            emb = msg.embeds[0]
            base_t = re.sub(r'\s*\(.*\)$', '', emb.title).replace('\u200b', '')
            meta = {"base_cid": cid, "channel_id": ch_id, "title": base_t, "description": emb.description, "ort": extract_ort(emb), "deadline_stunden": extract_dl(emb, default_dl)}
            await i.followup.send(f"New playday for **{base_t}** (`{cid}`):", view=AddPlaydayHelperView(meta), ephemeral=True)
        except:
            await i.followup.send("❌ Failed to load base series tournament.", ephemeral=True)

class TournamentBaseModal(ui.Modal, title="New Tournament"):
    ch = ui.TextInput(label="Channel Name", placeholder="e.g. ebl-prague", required=True)
    tt = ui.TextInput(label="Tournament Title", placeholder="e.g. European Laserball Cup", required=True)
    ds = ui.TextInput(label="Description", style=discord.TextStyle.paragraph, required=False)
    ot = ui.TextInput(label="Location / City", required=True)
    dl = ui.TextInput(label="Deadline (hours before start)", required=True)

    def __init__(self, default_dl: int = 48):
        super().__init__()
        self.dl.default = str(default_dl)
        self.default_dl = default_dl

    async def on_submit(self, i: discord.Interaction):
        try:
            dl_h = int(self.dl.value)
        except ValueError:
            dl_h = self.default_dl
        meta = {"channel_name": self.ch.value, "title": self.tt.value, "description": self.ds.value, "ort": self.ot.value, "deadline_stunden": dl_h}
        await i.response.send_message("Select tournament type:", view=TournamentTypeView(meta), ephemeral=True)

class TournamentTypeView(ui.View):
    def __init__(self, m):
        super().__init__(timeout=120)
        self.m = m

    @ui.button(label="Single Day", emoji="📅")
    async def b1(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(TournamentDateModal(self.m, "single"))

    @ui.button(label="Date Range", emoji="🗓️")
    async def b2(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(TournamentDateModal(self.m, "range"))

    @ui.button(label="Series", emoji="🔁")
    async def b3(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(TournamentDateModal(self.m, "series"))

class NewTournamentButton(ui.Button):
    def __init__(self, default_dl: int = 48):
        super().__init__(label="New Tournament", style=discord.ButtonStyle.success, emoji="🏆", row=0)
        self.default_dl = default_dl

    async def callback(self, i: discord.Interaction):
        await i.response.send_modal(TournamentBaseModal(self.default_dl))

class EditBaseModal(ui.Modal, title="Edit Tournament Details"):
    def __init__(self, meta, msg):
        super().__init__()
        self.msg = msg
        self.meta = meta
        self.t = ui.TextInput(label="Title", default=meta['title'])
        self.d = ui.TextInput(label="Description", default=meta['desc'] or "", style=discord.TextStyle.paragraph, required=False)
        self.o = ui.TextInput(label="Location", default=meta['ort'])
        self.add_item(self.t); self.add_item(self.d); self.add_item(self.o)

    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        g_lang = i18n.get_guild_lang(i.guild.id)
        emb = self.msg.embeds[0]
        emb.title = self.t.value + ('\u200b' if self.meta.get('is_series') else '')
        emb.description = self.d.value

        conn = data_manager.get_main_db_connection(); c = conn.cursor()
        c.execute("UPDATE tournament_events SET event_title=%s WHERE guild_id=%s AND custom_id=%s", (emb.title, str(i.guild.id), self.meta['cid']))
        c.execute("UPDATE tournaments SET event_title=%s WHERE guild_id=%s AND custom_id=%s", (emb.title, str(i.guild.id), self.meta['cid']))
        conn.commit(); c.close(); conn.close()

        for idx, f in enumerate(emb.fields):
            if "📍" in f.name or any(k in f.name.lower() for k in ["ort", "location", "místo", "luogo"]):
                emb.set_field_at(idx, name=i18n.t(g_lang, "tourn_fld_loc"), value=f"[{self.o.value}](https://maps.google.com/?q={urllib.parse.quote(self.o.value)})", inline=True)

        await self.msg.edit(embed=emb)
        await i.followup.send("✅ Updated!", ephemeral=True)

class EditDateModal(ui.Modal, title="Edit Dates & Deadline"):
    def __init__(self, meta, msg):
        super().__init__()
        self.msg = msg
        self.meta = meta
        self.d = ui.TextInput(label="Date(s)", default=meta['datum'])
        self.s = ui.TextInput(label="Start Time (HH:MM)", default=meta['start'])
        self.e = ui.TextInput(label="End Time (HH:MM)", default=meta['ende'])
        self.dl = ui.TextInput(label="Deadline (hours before)", default=str(meta.get('dl', 48)))
        self.add_item(self.d); self.add_item(self.s); self.add_item(self.e); self.add_item(self.dl)

    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        g_lang = i18n.get_guild_lang(i.guild.id)
        emb = self.msg.embeds[0]
        st, _ = get_start_info(self.d.value, self.s.value)
        if not st:
            await i.followup.send("❌ Invalid date/time.", ephemeral=True)
            return

        try:
            dl_hours = int(self.dl.value)
        except ValueError:
            dl_hours = self.meta.get('dl', 48)

        new_dl = st - timedelta(hours=dl_hours)
        emb.set_footer(text=i18n.t(g_lang, "tourn_footer", cid=self.meta['cid'], dl=new_dl.strftime('%d.%m.%Y %H:%M')))

        for idx, f in enumerate(emb.fields):
            if "📅" in f.name or any(k in f.name.lower() for k in ["termin", "date", "termín", "data"]):
                emb.set_field_at(idx, name=i18n.t(g_lang, "tourn_fld_dates"), value=f"{self.d.value}, {self.s.value} - {self.e.value}", inline=True)

        await self.msg.edit(embed=emb)
        await i.followup.send("✅ Schedule & deadline updated!", ephemeral=True)

class EditButtonView(ui.View):
    def __init__(self, m, o):
        super().__init__(timeout=120)
        self.m = m; self.o = o

    @ui.button(label="Title, Description & Location", emoji="📝")
    async def b1(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(EditBaseModal(self.m, self.o))

    @ui.button(label="Dates & Deadline", emoji="⏰")
    async def b2(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(EditDateModal(self.m, self.o))

class EditTournamentSelect(ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="📝 Edit tournament...", options=options)

    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        evt = data_manager.get_tournament_event_by_custom_id(i.guild.id, self.values[0])
        default_dl = int(data_manager.get_server_settings(i.guild.id).get("tournament_deadline_hours", 48))
        try:
            ch = i.guild.get_channel(int(evt[0])) or await i.guild.fetch_channel(int(evt[0]))
            msg = await ch.fetch_message(int(evt[1]))
            emb = msg.embeds[0]
            d, t, e = extract_times(emb)
            meta = {"cid": self.values[0], "title": emb.title.replace('\u200b', ''), "is_series": emb.title.endswith('\u200b'), "desc": emb.description, "datum": d, "start": t, "ende": e, "ort": extract_ort(emb), "dl": extract_dl(emb, default_dl)}
            await i.followup.send(f"Editing: **{meta['title']}**", view=EditButtonView(meta, msg), ephemeral=True)
        except:
            await i.followup.send("❌ Could not load tournament message.", ephemeral=True)

class CancelConfirmView(ui.View):
    def __init__(self, cid):
        super().__init__(timeout=60)
        self.cid = cid

    @ui.button(label="Yes, Cancel Tournament", style=discord.ButtonStyle.danger)
    async def conf(self, i: discord.Interaction, b: ui.Button):
        await i.response.defer(ephemeral=True)
        g_lang = i18n.get_guild_lang(i.guild.id)
        evt = data_manager.get_tournament_event_by_custom_id(i.guild.id, self.cid)
        try:
            ch = i.guild.get_channel(int(evt[0])) or await i.guild.fetch_channel(int(evt[0]))
            msg = await ch.fetch_message(int(evt[1]))
            e = msg.embeds[0]
            e.color = discord.Color.red()
            prefix = i18n.t(g_lang, "tourn_canceled_prefix")
            if not e.title.startswith("❌"):
                e.title = f"{prefix}{e.title.replace(chr(8203), '')}"
            v = TournamentView(g_lang)
            for child in v.children:
                child.disabled = True
            await msg.edit(embed=e, view=v)
            await i.followup.send("✅ Tournament canceled.", ephemeral=True)
        except:
            await i.followup.send("❌ Failed to cancel tournament.", ephemeral=True)

class CancelTournamentSelect(ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="❌ Cancel tournament...", options=options)

    async def callback(self, i: discord.Interaction):
        await i.response.send_message(f"Really cancel tournament **{self.values[0]}**?", view=CancelConfirmView(self.values[0]), ephemeral=True)

class TournamentMainMenu(ui.View):
    def __init__(self, events, can_create, can_manage, default_dl=48):
        super().__init__(timeout=180)

        def extract_id(item):
            return [int(p) if p.isdigit() else 0 for p in str(item[0]).split('-')]

        sorted_events = sorted(events, key=extract_id, reverse=True) if events else []

        if can_create:
            self.add_item(NewTournamentButton(default_dl))
            if sorted_events:
                has_children = {str(cid).rsplit('-', 1)[0] for cid, _, _, _ in sorted_events if str(cid).count('-') >= 2}
                add_opts = []
                for cid, title, ch_id, _ in sorted_events:
                    cid_str = str(cid)
                    if cid_str.count('-') == 1 and ((title or "").endswith('\u200b') or cid_str in has_children):
                        clean_title = (title or "").replace('\u200b', '')
                        add_opts.append(discord.SelectOption(label=clean_title[:90], description=f"ID: {cid_str}", value=f"{cid_str}|{ch_id}", emoji="➕"))
                    if len(add_opts) == 25:
                        break
                if add_opts:
                    self.add_item(AddPlaydaySelect(add_opts))

                edit_opts, canc_opts = [], []
                for c, t, _, _ in sorted_events[:25]:
                    clean_t = (t or "").replace('\u200b', '')[:90]
                    c_str = str(c)
                    edit_opts.append(discord.SelectOption(label=clean_t, description=f"ID: {c_str}", value=c_str, emoji="📝"))
                    canc_opts.append(discord.SelectOption(label=clean_t, description=f"ID: {c_str}", value=c_str, emoji="❌"))
                if edit_opts:
                    self.add_item(EditTournamentSelect(edit_opts))
                    self.add_item(CancelTournamentSelect(canc_opts))

        if can_manage and sorted_events:
            manage_opts = [
                discord.SelectOption(label=(t or "").replace('\u200b', '')[:90], description=f"ID: {c}", value=str(c), emoji="👥")
                for c, t, _, _ in sorted_events[:25]
            ]
            if manage_opts:
                self.add_item(ManageTournPartsSelect(manage_opts))

# --- TEILNEHMER & REISE MODALS ---

class TravelPlanModal(ui.Modal, title="Travel & Accommodation"):
    hotel_input = ui.TextInput(label="Accommodation (Hotel / Private / Venue)", default="Hotel", required=True, max_length=50)
    car_input = ui.TextInput(label="Offer car for carpool? (Yes / No)", default="No", required=True, max_length=30)
    arrival_input = ui.TextInput(label="Arrival Day", placeholder="e.g. Friday", default="Friday", required=True, max_length=50)
    departure_input = ui.TextInput(label="Departure Day", placeholder="e.g. Sunday", default="Sunday", required=True, max_length=50)

    def __init__(self, parent_view, message, tourn_id, event_title, user_profile, existing_response):
        super().__init__()
        self.parent_view = parent_view
        self.message = message
        self.tourn_id = tourn_id
        self.event_title = event_title
        self.user_profile = user_profile

        if existing_response:
            self.hotel_input.default = "Hotel" if existing_response["needs_hotel"] else existing_response["alt_accommodation"]
            self.car_input.default = "Yes" if existing_response["has_car"] else "No"
            self.arrival_input.default = existing_response["arrival"]
            self.departure_input.default = existing_response["departure"]

        if not user_profile.get("has_license", False):
            self.car_input.default = "No (No driver's license)"

    async def on_submit(self, interaction: discord.Interaction):
        hotel_val = self.hotel_input.value.strip().lower()
        needs_hotel = hotel_val in ("hotel", "ja", "yes", "j", "y", "ano", "si", "sì")
        alt_acc = self.hotel_input.value.strip() if not needs_hotel else ""

        car_val = self.car_input.value.strip().lower()
        has_car = car_val in ("ja", "yes", "j", "y", "ano", "si", "sì") and bool(self.user_profile.get("has_license", False))

        data_manager.save_travel_response(interaction.guild_id, self.tourn_id, interaction.user.id, needs_hotel, alt_acc, has_car, self.arrival_input.value.strip(), self.departure_input.value.strip())
        data_manager.set_tournament_status(interaction.guild_id, self.tourn_id, interaction.user.id, interaction.user.name, interaction.user.display_name, self.event_title, "Zusagen")

        await self.parent_view.update_embed(interaction)
        await interaction.followup.send("✅ Commitment & travel details saved!", ephemeral=True)

class ManualTravelPlanModal(ui.Modal, title="Travel Details (Manual Entry)"):
    hotel_input = ui.TextInput(label="Accommodation (Hotel / Private / Venue)", default="Hotel", required=True, max_length=50)
    car_input = ui.TextInput(label="Offer car for carpool? (Yes / No)", default="No", required=True, max_length=30)
    arrival_input = ui.TextInput(label="Arrival Day", default="Friday", required=True, max_length=50)
    departure_input = ui.TextInput(label="Departure Day", default="Sunday", required=True, max_length=50)

    def __init__(self, tourn_id, event_title, target_user_id, target_user_name, target_display_name, channel_id, msg_id, user_profile, existing_response):
        super().__init__()
        self.tourn_id = tourn_id
        self.event_title = event_title
        self.target_user_id = target_user_id
        self.target_user_name = target_user_name
        self.target_display_name = target_display_name
        self.channel_id = channel_id
        self.msg_id = msg_id
        self.user_profile = user_profile

        if existing_response:
            self.hotel_input.default = "Hotel" if existing_response["needs_hotel"] else existing_response["alt_accommodation"]
            self.car_input.default = "Yes" if existing_response["has_car"] else "No"
            self.arrival_input.default = existing_response["arrival"]
            self.departure_input.default = existing_response["departure"]

        if not user_profile.get("has_license", False):
            self.car_input.default = "No"

    async def on_submit(self, interaction: discord.Interaction):
        hotel_val = self.hotel_input.value.strip().lower()
        needs_hotel = hotel_val in ("hotel", "ja", "yes", "j", "y", "ano", "si", "sì")
        alt_acc = self.hotel_input.value.strip() if not needs_hotel else ""
        car_val = self.car_input.value.strip().lower()
        has_car = car_val in ("ja", "yes", "j", "y", "ano", "si", "sì") and bool(self.user_profile.get("has_license", False))

        data_manager.save_travel_response(interaction.guild_id, self.tourn_id, self.target_user_id, needs_hotel, alt_acc, has_car, self.arrival_input.value.strip(), self.departure_input.value.strip())
        data_manager.set_tournament_status(interaction.guild_id, self.tourn_id, self.target_user_id, self.target_user_name, self.target_display_name, self.event_title, "Zusagen", manual=True)

        await interaction.response.defer(ephemeral=True)
        try:
            ch = interaction.guild.get_channel(int(self.channel_id)) or await interaction.guild.fetch_channel(int(self.channel_id))
            msg = await ch.fetch_message(int(self.msg_id))
            await TournamentView(i18n.get_guild_lang(interaction.guild_id)).update_embed(msg)
            await interaction.followup.send(f"✅ Saved for **{self.target_display_name}**!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ Saved in DB, could not refresh message: {e}", ephemeral=True)

class ManageTournPartsSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="👥 Manage participants manually...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        event_data = data_manager.get_tournament_event_by_custom_id(interaction.guild_id, self.values[0])
        if not event_data:
            await interaction.followup.send("❌ Event not found.", ephemeral=True)
            return
        await interaction.followup.send(f"👥 **Participant Manager** — {event_data[4]}", view=TournPartManageView(event_data, interaction.guild), ephemeral=True)

class TournManualStatusSelect(discord.ui.Select):
    def __init__(self, member, event_data, guild):
        options = [
            discord.SelectOption(label="Commit", value="Zusagen", emoji="✅"),
            discord.SelectOption(label="Maybe", value="Vielleicht", emoji="❔"),
            discord.SelectOption(label="Decline", value="Absagen", emoji="❌"),
            discord.SelectOption(label="Remove Entry Completely", value="Delete", emoji="🗑️")
        ]
        super().__init__(placeholder=f"Action for {member.display_name[:50]}...", options=options)
        self.member = member
        self.event_data = event_data
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        cid = self.event_data[2]
        title = self.event_data[4]
        if self.values[0] == "Zusagen":
            user_profile = data_manager.get_travel_profile(self.member.id)
            existing_response = data_manager.get_travel_response(interaction.guild_id, cid, self.member.id)
            await interaction.response.send_modal(ManualTravelPlanModal(
                tourn_id=cid, event_title=title, target_user_id=str(self.member.id),
                target_user_name=self.member.name, target_display_name=self.member.display_name,
                channel_id=self.event_data[0], msg_id=self.event_data[1],
                user_profile=user_profile, existing_response=existing_response
            ))
        else:
            await interaction.response.defer(ephemeral=True)
            if self.values[0] == "Delete":
                data_manager.delete_tournament_entry(interaction.guild_id, cid, str(self.member.id))
                data_manager.delete_tournament_note(interaction.guild_id, cid, str(self.member.id))
            else:
                data_manager.set_tournament_status(interaction.guild_id, cid, self.member.id, self.member.name, self.member.display_name, title, self.values[0], manual=True)
            try:
                ch = self.guild.get_channel(int(self.event_data[0])) or await self.guild.fetch_channel(int(self.event_data[0]))
                msg = await ch.fetch_message(int(self.event_data[1]))
                await TournamentView(i18n.get_guild_lang(self.guild.id)).update_embed(msg)
                await interaction.followup.send(f"✅ Updated {self.member.mention}.", ephemeral=True)
            except:
                await interaction.followup.send("⚠️ Saved in DB, message refresh failed.", ephemeral=True)

class TournGuestAddModal(ui.Modal, title="Add External Guest"):
    guest_name = ui.TextInput(label="Guest Name", required=True, max_length=50)
    hotel_input = ui.TextInput(label="Accommodation (Hotel / Private / Venue)", default="Hotel", required=True, max_length=50)
    car_input = ui.TextInput(label="Offers Car? (Yes / No)", default="No", required=True, max_length=30)
    arrival_input = ui.TextInput(label="Arrival Day", default="Friday", required=True, max_length=50)
    departure_input = ui.TextInput(label="Departure Day", default="Sunday", required=True, max_length=50)

    def __init__(self, event_data, guild):
        super().__init__()
        self.event_data = event_data
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction):
        d_name = self.guest_name.value.strip()
        guest_id = f"ext_{d_name}"
        hotel_val = self.hotel_input.value.strip().lower()
        needs_hotel = hotel_val in ("hotel", "ja", "yes", "j", "y", "ano", "si", "sì")
        alt_acc = self.hotel_input.value.strip() if not needs_hotel else ""
        has_car = self.car_input.value.strip().lower() in ("ja", "yes", "j", "y", "ano", "si", "sì")

        cid = self.event_data[2]
        title = self.event_data[4]
        data_manager.save_travel_response(interaction.guild_id, cid, guest_id, needs_hotel, alt_acc, has_car, self.arrival_input.value.strip(), self.departure_input.value.strip())
        data_manager.set_tournament_status(interaction.guild_id, cid, guest_id, d_name, f"Guest: {d_name}", title, "Zusagen", manual=True)

        await interaction.response.defer(ephemeral=True)
        try:
            ch = self.guild.get_channel(int(self.event_data[0])) or await self.guild.fetch_channel(int(self.event_data[0]))
            msg = await ch.fetch_message(int(self.event_data[1]))
            await TournamentView(i18n.get_guild_lang(self.guild.id)).update_embed(msg)
            await interaction.followup.send(f"✅ Guest **{d_name}** added!", ephemeral=True)
        except:
            await interaction.followup.send("⚠️ Saved in DB, message refresh failed.", ephemeral=True)

class TournGuestRemoveSelect(discord.ui.Select):
    def __init__(self, guests, event_data, guild):
        options = []
        seen = set()
        for uid, name in guests:
            if uid in seen: continue
            seen.add(uid)
            options.append(discord.SelectOption(label=name[:90], value=str(uid)[:100], emoji="🗑️"))
            if len(options) >= 25: break
        super().__init__(placeholder="Select guest to remove...", options=options)
        self.event_data = event_data
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        cid = self.event_data[2]
        data_manager.delete_tournament_entry(interaction.guild_id, cid, self.values[0])
        data_manager.delete_tournament_note(interaction.guild_id, cid, self.values[0])
        await interaction.response.defer(ephemeral=True)
        try:
            ch = self.guild.get_channel(int(self.event_data[0])) or await self.guild.fetch_channel(int(self.event_data[0]))
            msg = await ch.fetch_message(int(self.event_data[1]))
            await TournamentView(i18n.get_guild_lang(self.guild.id)).update_embed(msg)
            await interaction.followup.send("✅ Guest removed.", ephemeral=True)
        except:
            await interaction.followup.send("⚠️ Removed from DB.", ephemeral=True)

class TournPartManageView(discord.ui.View):
    def __init__(self, event_data, guild):
        super().__init__(timeout=120)
        self.event_data = event_data
        self.guild = guild

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="1. Select member...", row=0)
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        member = select.values[0]
        v = discord.ui.View()
        v.add_item(TournManualStatusSelect(member, self.event_data, self.guild))
        await interaction.response.send_message(f"Step 2: Select status for {member.mention}:", view=v, ephemeral=True)

    @discord.ui.button(label="Add External Guest", style=discord.ButtonStyle.success, emoji="➕", row=1)
    async def btn_add_guest(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TournGuestAddModal(self.event_data, self.guild))

    @discord.ui.button(label="Remove External Guest", style=discord.ButtonStyle.danger, emoji="➖", row=1)
    async def btn_remove_guest(self, interaction: discord.Interaction, button: discord.ui.Button):
        parts = data_manager.get_tournament_participants(self.guild.id, self.event_data[2])
        guests = [(info['user_id'], name) for name, info in parts.items() if str(info['user_id']).startswith("ext_")]
        if not guests:
            await interaction.response.send_message("❌ No manual external guests found.", ephemeral=True)
            return
        v = discord.ui.View()
        v.add_item(TournGuestRemoveSelect(guests, self.event_data, self.guild))
        await interaction.response.send_message("Select guest to remove:", view=v, ephemeral=True)

# --- TEAM MANAGER (MIT GUILD_ID ISOLATION) ---

class TeamUserAddSelect(ui.UserSelect):
    def __init__(self, team_name, tourn_id, event_title, main_msg):
        super().__init__(placeholder="Select members to add...", min_values=1, max_values=25)
        self.team_name = team_name; self.tourn_id = tourn_id; self.event_title = event_title; self.main_msg = main_msg

    async def callback(self, i: discord.Interaction):
        parsed = [(str(m.id), m.name, m.display_name) for m in self.values]
        mentions = [m.mention for m in self.values]
        if data_manager.set_team_members(i.guild.id, self.tourn_id, self.team_name, parsed, self.event_title):
            await TournamentView(i18n.get_guild_lang(i.guild.id)).update_embed(self.main_msg)
            await i.response.send_message(f"✅ Added: {', '.join(mentions)}", ephemeral=True)
        else:
            await i.response.send_message(i18n.t(i, "db_error"), ephemeral=True)

class TeamGuestAddModal(ui.Modal, title="Add Guests to Team"):
    guests = ui.TextInput(label="Names (comma-separated)", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, tn, cid, et, msg):
        super().__init__()
        self.tn = tn; self.cid = cid; self.et = et; self.msg = msg

    async def on_submit(self, i: discord.Interaction):
        gs = [(f"ext_{x.strip()}", x.strip(), x.strip()) for x in self.guests.value.split(',') if x.strip()]
        if data_manager.set_team_members(i.guild.id, self.cid, self.tn, gs, self.et):
            await TournamentView(i18n.get_guild_lang(i.guild.id)).update_embed(self.msg)
            await i.response.send_message(f"✅ Guests added to **{self.tn}**.", ephemeral=True)
        else:
            await i.response.send_message(i18n.t(i, "db_error"), ephemeral=True)

class TeamMemberRemoveSelect(ui.Select):
    def __init__(self, members, tourn_id, main_msg):
        options = [discord.SelectOption(label=name[:90], value=str(uid), emoji="🗑️") for uid, name in members[:25]]
        super().__init__(placeholder="Select player to remove from team...", min_values=1, max_values=1, options=options)
        self.tourn_id = tourn_id; self.main_msg = main_msg

    async def callback(self, i: discord.Interaction):
        if data_manager.remove_team_member(i.guild.id, self.tourn_id, self.values[0]):
            await TournamentView(i18n.get_guild_lang(i.guild.id)).update_embed(self.main_msg)
            await i.response.send_message("✅ Removed from team.", ephemeral=True)
        else:
            await i.response.send_message(i18n.t(i, "db_error"), ephemeral=True)

class RenameTeamModal(ui.Modal, title="Rename Team"):
    new_name = ui.TextInput(label="New Team Name", required=True)

    def __init__(self, tn, cid, et, msg):
        super().__init__()
        self.on = tn; self.cid = cid; self.et = et; self.msg = msg
        self.new_name.default = tn

    async def on_submit(self, i: discord.Interaction):
        conn = data_manager.get_main_db_connection(); c = conn.cursor()
        c.execute("UPDATE tournaments SET team_name=%s WHERE guild_id=%s AND custom_id=%s AND team_name=%s",
                  (self.new_name.value.strip(), str(i.guild.id), str(self.cid), self.on))
        conn.commit(); c.close(); conn.close()
        await TournamentView(i18n.get_guild_lang(i.guild.id)).update_embed(self.msg)
        await i.response.send_message(f"✅ Team renamed to **{self.new_name.value.strip()}**.", ephemeral=True)

class TeamEditOptionsView(ui.View):
    def __init__(self, tn, cid, et, msg):
        super().__init__(timeout=120)
        self.tn = tn; self.cid = cid; self.et = et; self.msg = msg

    @ui.button(label="Add Members", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def add(self, i: discord.Interaction, b: ui.Button):
        v = ui.View(timeout=60)
        v.add_item(TeamUserAddSelect(self.tn, self.cid, self.et, self.msg))
        await i.response.send_message("Select members:", view=v, ephemeral=True)

    @ui.button(label="Add Guests", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def add_guest(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(TeamGuestAddModal(self.tn, self.cid, self.et, self.msg))

    @ui.button(label="Remove Player", style=discord.ButtonStyle.danger, emoji="➖", row=0)
    async def rem(self, i: discord.Interaction, b: ui.Button):
        m = data_manager.get_team_members_data(i.guild.id, self.cid, self.tn)
        if not m:
            await i.response.send_message("Team is empty.", ephemeral=True)
            return
        v = ui.View(timeout=60)
        v.add_item(TeamMemberRemoveSelect(m, self.cid, self.msg))
        await i.response.send_message("Select player to remove:", view=v, ephemeral=True)

    @ui.button(label="Rename Team", style=discord.ButtonStyle.secondary, emoji="✏️", row=1)
    async def ren(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(RenameTeamModal(self.tn, self.cid, self.et, self.msg))

class TeamCreationModal(ui.Modal, title="Create Team"):
    name = ui.TextInput(label="Team Name", required=True)
    guests = ui.TextInput(label="External Guests (optional, comma-separated)", style=discord.TextStyle.paragraph, required=False)

    def __init__(self, msg):
        super().__init__()
        self.msg = msg

    async def on_submit(self, i: discord.Interaction):
        emb = self.msg.embeds[0]
        rid = data_manager.get_event_id_by_message(self.msg.id, i.guild.id) or emb.footer.text.split("|")[0].replace("ID: ", "").strip()
        tname = self.name.value.strip()
        if self.guests.value.strip():
            gs = [(f"ext_{x.strip()}", x.strip(), x.strip()) for x in self.guests.value.split(',') if x.strip()]
            data_manager.set_team_members(i.guild.id, rid, tname, gs, emb.title)
            await TournamentView(i18n.get_guild_lang(i.guild.id)).update_embed(self.msg)
        await i.response.send_message(f"✅ Team **{tname}** ready.", view=TeamEditOptionsView(tname, rid, emb.title, self.msg), ephemeral=True)

class ConfirmDeleteView(ui.View):
    def __init__(self, t, m):
        super().__init__(timeout=60)
        self.t = t; self.m = m

    @ui.button(label="Delete Team", style=discord.ButtonStyle.danger)
    async def conf(self, i: discord.Interaction, b: ui.Button):
        rid = data_manager.get_event_id_by_message(self.m.id, i.guild.id) or self.m.embeds[0].footer.text.split("|")[0].replace("ID: ", "").strip()
        if data_manager.delete_team(i.guild.id, rid, self.t):
            await TournamentView(i18n.get_guild_lang(i.guild.id)).update_embed(self.m)
            await i.response.edit_message(content="✅ Team deleted.", view=None)
        else:
            await i.response.edit_message(content="❌ Error.", view=None)

class TeamManagerView(ui.View):
    def __init__(self, msg, ts):
        super().__init__(timeout=90)
        self.msg = msg
        btn = ui.Button(label="New Team", style=discord.ButtonStyle.success, emoji="➕")
        btn.callback = lambda inter: inter.response.send_modal(TeamCreationModal(msg))
        self.add_item(btn)

        if ts:
            sel_edit = ui.Select(placeholder="✏️ Edit team...", options=[discord.SelectOption(label=t[:90], value=t[:90], emoji="✏️") for t in ts[:25]])
            async def edit_cb(inter: discord.Interaction):
                rid = data_manager.get_event_id_by_message(msg.id, inter.guild.id) or msg.embeds[0].footer.text.split("|")[0].replace("ID: ", "").strip()
                await inter.response.send_message(f"⚙️ **{sel_edit.values[0]}**", view=TeamEditOptionsView(sel_edit.values[0], rid, msg.embeds[0].title, msg), ephemeral=True)
            sel_edit.callback = edit_cb
            self.add_item(sel_edit)

            sel_del = ui.Select(placeholder="🗑️ Delete team...", options=[discord.SelectOption(label=t[:90], value=t[:90], emoji="🗑️") for t in ts[:25]])
            sel_del.callback = lambda inter: inter.response.send_message(f"🗑️ Delete **{sel_del.values[0]}**?", view=ConfirmDeleteView(sel_del.values[0], msg), ephemeral=True)
            self.add_item(sel_del)

class TournamentNoteModal(discord.ui.Modal, title="Note"):
    note = discord.ui.TextInput(label="Note (max 50 chars, empty = clear)", style=discord.TextStyle.short, required=False, max_length=50)

    def __init__(self, guild_id, tourn_id, message):
        super().__init__()
        self.guild_id = guild_id
        self.tourn_id = tourn_id
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        if not self.note.value.strip():
            data_manager.delete_tournament_note(self.guild_id, self.tourn_id, str(interaction.user.id))
            msg = "✅ Note deleted!"
        else:
            data_manager.set_tournament_note(self.guild_id, self.tourn_id, str(interaction.user.id), self.note.value.strip())
            msg = "✅ Note saved!"
        await TournamentView(i18n.get_guild_lang(self.guild_id)).update_embed(self.message)
        await interaction.response.send_message(msg, ephemeral=True)

# --- PERSISTENTE TOURNAMENT VIEW ---

class TournamentView(discord.ui.View):
    def __init__(self, lang: str = "en"):
        super().__init__(timeout=None)
        self.b1.label = i18n.t(lang, "btn_commit")
        self.b2.label = i18n.t(lang, "btn_maybe")
        self.b3.label = i18n.t(lang, "btn_cancel")
        self.b_note.label = i18n.t(lang, "btn_note")
        self.b4.label = i18n.t(lang, "tourn_btn_teams")
        self.b8.label = i18n.t(lang, "tourn_btn_car")
        self.b5.label = i18n.t(lang, "tourn_btn_ics")
        self.b6.label = i18n.t(lang, "tourn_btn_orga")
        self.b7.label = i18n.t(lang, "btn_refresh")

    async def update_embed(self, i):
        msg = i if isinstance(i, discord.Message) else i.message
        guild_id = str(msg.guild.id)
        lang = i18n.get_guild_lang(guild_id)

        # Notfall-Wiederherstellung auf dem Aktualisieren-Button
        if not msg.embeds:
            cid = data_manager.get_event_id_by_message(msg.id, guild_id)
            if not cid:
                if not isinstance(i, discord.Message):
                    await i.response.send_message(i18n.t(i, "db_error"), ephemeral=True)
                return
            evt = data_manager.get_tournament_event_by_custom_id(guild_id, cid)
            title = evt[4] if evt else "Restored Tournament"

            emb = discord.Embed(title=title, description=i18n.t(lang, "tourn_restored_desc"), color=discord.Color.blue())
            emb.set_footer(text=i18n.t(lang, "tourn_footer", cid=cid, dl="01.01.2099 00:00"))
            emb.add_field(name=i18n.t(lang, "tourn_fld_dates"), value="*Missing*", inline=True)
            emb.add_field(name=i18n.t(lang, "tourn_fld_loc"), value="*Missing*", inline=True)
        else:
            emb = msg.embeds[0]

        cid = data_manager.get_event_id_by_message(msg.id, guild_id) or emb.footer.text.split("|")[0].replace("ID: ", "").strip()
        data = data_manager.get_tournament_participants(guild_id, cid)
        notes = data_manager.get_tournament_notes(guild_id, cid)

        teams, s, m, n = {}, [], [], []
        freitext_lines = []

        def fmt(x, y):
            uid = str(y['user_id'])
            asterisk = "*" if notes.get(uid) else ""
            return f"• {x}{asterisk}" + (" Ⓜ️" if y['manual'] else "")

        for nm, inf in data.items():
            l = fmt(nm, inf)
            uid = str(inf['user_id'])
            note = notes.get(uid)
            if note:
                clean_note = note.replace('*', '').replace('`', '').replace('_', '').replace('\n', ' ')
                freitext_lines.append(f"**{nm}:** {clean_note}")

            if inf['status'] == 'Zusagen':
                if inf['team']:
                    teams.setdefault(inf['team'], []).append(l)
                else:
                    s.append(l)
            elif inf['status'] == 'Vielleicht':
                m.append(l)
            elif inf['status'] == 'Absagen':
                n.append(l)

        tt = "".join([f"**🏆 {t}**\n" + "\n".join(mem) + "\n\n" for t, mem in teams.items()])
        static = [f for f in emb.fields if "📅" in f.name or "📍" in f.name or any(k in f.name.lower() for k in ["termin", "ort", "date", "location", "termín", "místo", "luogo"])]
        emb.clear_fields()

        for f in static:
            emb.add_field(name=f.name, value=f.value, inline=f.inline)
        emb.add_field(name="\u200b", value="\u200b", inline=False)

        if tt:
            emb.add_field(name=i18n.t(lang, "tourn_fld_teams"), value=tt.strip()[:1024], inline=False)

        none_txt = i18n.t(lang, "none_list")
        c_count = len(s) + sum(len(x) for x in teams.values())
        emb.add_field(name=i18n.t(lang, "tourn_fld_commit", solo=len(s), total=c_count), value="\n".join(s)[:1024] if s else none_txt, inline=False)
        emb.add_field(name=f"❔ ({len(m)})", value="\n".join(m)[:1024] if m else none_txt, inline=True)
        emb.add_field(name=f"❌ ({len(n)})", value="\n".join(n)[:1024] if n else none_txt, inline=True)

        planning_data = data_manager.get_travel_planning_data(guild_id, cid)
        hotels_db = {h[0]: h[2] for h in data_manager.get_hotels(guild_id)}
        hotel_text, alt_text = "", ""
        rooms, cars_out, cars_ret = {}, {}, {}

        for row in planning_data:
            uid, name, n_hotel, alt, h_car, arr, dep, lic, pref, partner_id, def_pass, h_id, r_name, c_out, drv_out, c_ret, drv_ret = row
            if h_id and r_name:
                h_name = hotels_db.get(h_id, "Hotel")
                rooms.setdefault(h_name, {}).setdefault(r_name, []).append(name)
            elif alt:
                alt_text += f"• {name} ({alt})\n"

            if c_out:
                cars_out.setdefault(c_out, []).append({"name": name, "is_owner": bool(h_car), "can_drive": bool(lic)})
            if c_ret:
                cars_ret.setdefault(c_ret, []).append({"name": name, "is_owner": bool(h_car), "can_drive": bool(lic)})

        for h_name, r_dict in rooms.items():
            hotel_text += f"**{h_name}**\n"
            for r_name, users in r_dict.items():
                hotel_text += f"*{r_name}:* {', '.join(users)}\n"
            hotel_text += "\n"

        def build_embed_car_text(car_dict):
            text = ""
            for c_id, users_list in car_dict.items():
                users_list.sort(key=lambda x: (not x["is_owner"], not x["can_drive"]))
                prefix = "" if c_id.lower().startswith(("auto", "car", "bus", "kfz", "van")) else "Car "
                text += f"**{prefix}{c_id}:**\n"
                for u in users_list:
                    marker = " 🚗" if u["is_owner"] else (" 🛞" if u["can_drive"] else "")
                    text += f"    {u['name']}{marker}\n"
                text += "\n"
            return text.strip()

        out_text = build_embed_car_text(cars_out)
        ret_text = build_embed_car_text(cars_ret)

        if hotel_text:
            emb.add_field(name=i18n.t(lang, "tourn_fld_hotel"), value=hotel_text.strip()[:1024], inline=False)
        if alt_text:
            emb.add_field(name=i18n.t(lang, "tourn_fld_alt"), value=alt_text.strip()[:1024], inline=False)
        if out_text or ret_text:
            emb.add_field(name="\u200b", value=i18n.t(lang, "tourn_car_legend"), inline=False)
        if out_text:
            emb.add_field(name=i18n.t(lang, "tourn_fld_car_out"), value=out_text[:1024], inline=True)
        if ret_text:
            emb.add_field(name=i18n.t(lang, "tourn_fld_car_ret"), value=ret_text[:1024], inline=True)
        if freitext_lines:
            emb.add_field(name=i18n.t(lang, "train_fld_notes"), value="\n".join(freitext_lines)[:1024], inline=False)

        new_view = TournamentView(lang)
        if isinstance(i, discord.Message):
            await msg.edit(embed=emb, view=new_view, suppress=False)
        else:
            await i.response.edit_message(embed=emb, view=new_view)
            await msg.edit(suppress=False)

    def _check_dl_open(self, embed) -> bool:
        if not embed.footer or not embed.footer.text:
            return True
        match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})\s+(\d{1,2}:\d{2})', embed.footer.text)
        if match:
            dl = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%d.%m.%Y %H:%M")
            if datetime.now() > dl:
                return False
        return True

    async def set_status(self, i: discord.Interaction, s: str):
        u_lang = i18n.get_interaction_lang(i, prefer_guild=False)
        if not i.message.embeds:
            await i.response.send_message(i18n.t(u_lang, "tourn_embed_missing"), ephemeral=True)
            return
        if isinstance(i.user, discord.Member) and data_manager.is_member_observer(i.user):
            await i.response.send_message(i18n.t(u_lang, "observer_blocked"), ephemeral=True)
            return
        if not self._check_dl_open(i.message.embeds[0]):
            await i.response.send_message(i18n.t(u_lang, "tourn_dl_passed"), ephemeral=True)
            return

        rid = data_manager.get_event_id_by_message(i.message.id, i.guild_id) or i.message.embeds[0].footer.text.split("|")[0].replace("ID: ", "").strip()
        if s == "Zusagen":
            user_profile = data_manager.get_travel_profile(i.user.id)
            existing_response = data_manager.get_travel_response(i.guild_id, rid, i.user.id)
            await i.response.send_modal(TravelPlanModal(self, i.message, rid, i.message.embeds[0].title, user_profile, existing_response))
        else:
            data_manager.set_tournament_status(i.guild_id, rid, i.user.id, i.user.name, i.user.display_name, i.message.embeds[0].title, s)
            await self.update_embed(i)

    @discord.ui.button(label="Commit", style=discord.ButtonStyle.success, emoji="✅", custom_id="tourn_commit", row=0)
    async def b1(self, i: discord.Interaction, b: discord.ui.Button):
        await self.set_status(i, "Zusagen")

    @discord.ui.button(label="Maybe", style=discord.ButtonStyle.secondary, emoji="❔", custom_id="tourn_maybe", row=0)
    async def b2(self, i: discord.Interaction, b: discord.ui.Button):
        await self.set_status(i, "Vielleicht")

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="❌", custom_id="tourn_cancel", row=0)
    async def b3(self, i: discord.Interaction, b: discord.ui.Button):
        await self.set_status(i, "Absagen")

    @discord.ui.button(label="Note", style=discord.ButtonStyle.primary, emoji="💬", custom_id="tourn_note", row=0)
    async def b_note(self, i: discord.Interaction, b: discord.ui.Button):
        u_lang = i18n.get_interaction_lang(i, prefer_guild=False)
        if not i.message.embeds:
            await i.response.send_message(i18n.t(u_lang, "tourn_embed_missing"), ephemeral=True)
            return
        if isinstance(i.user, discord.Member) and data_manager.is_member_observer(i.user):
            await i.response.send_message(i18n.t(u_lang, "observer_blocked"), ephemeral=True)
            return
        if not self._check_dl_open(i.message.embeds[0]):
            await i.response.send_message(i18n.t(u_lang, "tourn_dl_passed"), ephemeral=True)
            return

        cid = data_manager.get_event_id_by_message(i.message.id, i.guild_id) or i.message.embeds[0].footer.text.split("|")[0].replace("ID: ", "").strip()
        data = data_manager.get_tournament_participants(i.guild_id, cid)
        if str(i.user.id) not in [str(info['user_id']) for info in data.values()]:
            await i.response.send_message(i18n.t(u_lang, "train_note_need_status"), ephemeral=True)
            return
        await i.response.send_modal(TournamentNoteModal(str(i.guild_id), cid, i.message))

    @discord.ui.button(label="Manage Teams", style=discord.ButtonStyle.secondary, emoji="👥", custom_id="tourn_teams", row=1)
    async def b4(self, i: discord.Interaction, b: discord.ui.Button):
        u_lang = i18n.get_interaction_lang(i, prefer_guild=False)
        if not i.message.embeds:
            await i.response.send_message(i18n.t(u_lang, "tourn_embed_missing"), ephemeral=True)
            return
        cid = data_manager.get_event_id_by_message(i.message.id, i.guild_id) or i.message.embeds[0].footer.text.split("|")[0].replace("ID: ", "").strip()
        ts = data_manager.get_existing_teams(i.guild_id, cid)
        await i.response.send_message("**Team Manager**", view=TeamManagerView(i.message, ts), ephemeral=True)

    @discord.ui.button(label="Manage Car", style=discord.ButtonStyle.secondary, emoji="🚗", custom_id="tourn_manage_car", row=1)
    async def b8(self, i: discord.Interaction, b: discord.ui.Button):
        u_lang = i18n.get_interaction_lang(i, prefer_guild=False)
        if not i.message.embeds:
            await i.response.send_message(i18n.t(u_lang, "tourn_embed_missing"), ephemeral=True)
            return
        cid = data_manager.get_event_id_by_message(i.message.id, i.guild_id) or i.message.embeds[0].footer.text.split("|")[0].replace("ID: ", "").strip()

        is_orga = i.user.id in data_manager.DEVELOPER_IDS or (isinstance(i.user, discord.Member) and i.user.guild_permissions.administrator)
        if not is_orga and isinstance(i.user, discord.Member):
            allowed = data_manager.get_allowed_roles(str(i.guild_id), "orgateam")
            if allowed and set(allowed) & set([str(r.id) for r in i.user.roles]):
                is_orga = True

        planning_data = data_manager.get_travel_planning_data(i.guild_id, cid)
        user_row = next((r for r in planning_data if str(r[0]) == str(i.user.id)), None)
        has_car = bool(user_row and user_row[4])

        if not (is_orga or has_car):
            await i.response.send_message(i18n.t(u_lang, "no_permission"), ephemeral=True)
            return

        from commands.orgateam import UserAssignCarSelect, UserRemoveCarSelect, CarDeleteSelect
        v = ui.View(timeout=120)
        v.add_item(UserAssignCarSelect(i.guild_id, cid, i.message.embeds[0].title))
        v.add_item(UserRemoveCarSelect(i.guild_id, cid, i.message.embeds[0].title))
        if is_orga:
            v.add_item(CarDeleteSelect(i.guild_id, cid, i.message.embeds[0].title))
        await i.response.send_message("🚗 **Manage Carpool**", view=v, ephemeral=True)

    @discord.ui.button(label="Calendar (.ics)", style=discord.ButtonStyle.secondary, emoji="📅", custom_id="tourn_ics", row=1)
    async def b5(self, i: discord.Interaction, b: discord.ui.Button):
        u_lang = i18n.get_interaction_lang(i, prefer_guild=False)
        if not i.message.embeds:
            await i.response.send_message(i18n.t(u_lang, "tourn_embed_missing"), ephemeral=True)
            return

        emb = i.message.embeds[0]
        date_val, time_val, end_time_val = extract_times(emb)
        ort_val = extract_ort(emb) or "Unknown"
        dates = parse_dates_for_ics(date_val, time_val or "09:00")
        if not dates:
            await i.response.send_message("❌ Could not parse tournament date.", ephemeral=True)
            return

        bot_brand = data_manager.BOT_NAME
        ics_content = f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//{bot_brand}//EN\n"
        for dt in dates:
            if end_time_val:
                try:
                    eh, em = map(int, end_time_val.split(":"))
                    end_dt = dt.replace(hour=eh, minute=em)
                    if end_dt <= dt:
                        end_dt += timedelta(days=1)
                except:
                    end_dt = dt + timedelta(hours=8)
            else:
                end_dt = dt + timedelta(hours=8)

            fid = emb.footer.text.split('|')[0].strip() if emb.footer and emb.footer.text else ""
            ics_content += (
                "BEGIN:VEVENT\n"
                f"SUMMARY:{emb.title.replace(chr(8203), '')}\n"
                f"DTSTART:{dt.strftime('%Y%m%dT%H%M%S')}\n"
                f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}\n"
                f"LOCATION:{ort_val}\n"
                f"DESCRIPTION:{(emb.description or '').replace(chr(10), '\\n')}\\n\\n{fid}\\nPowered by {bot_brand}\n"
                "END:VEVENT\n"
            )
        ics_content += "END:VCALENDAR"
        file = discord.File(fp=io.BytesIO(ics_content.encode("utf-8")), filename=f"Tournament_{dates[0].strftime('%Y_%m_%d')}.ics")
        await i.response.send_message("📅 Calendar file:", file=file, ephemeral=True)

    @discord.ui.button(label="Orga Dashboard", style=discord.ButtonStyle.primary, emoji="📋", custom_id="tourn_orga", row=2)
    async def b6(self, i: discord.Interaction, b: discord.ui.Button):
        u_lang = i18n.get_interaction_lang(i, prefer_guild=False)
        if not i.message.embeds:
            await i.response.send_message(i18n.t(u_lang, "tourn_embed_missing"), ephemeral=True)
            return

        from commands.orgateam import is_authorized_orgateam, generate_dashboard_embed, DashboardView
        if not await is_authorized_orgateam(i):
            await i.response.send_message(i18n.t(u_lang, "no_permission"), ephemeral=True)
            return

        emb = i.message.embeds[0]
        cid = data_manager.get_event_id_by_message(i.message.id, i.guild_id) or emb.footer.text.split("|")[0].replace("ID: ", "").strip()
        event_ort = extract_ort(emb)
        dashboard_emb = generate_dashboard_embed(i.guild_id, cid, emb.title, event_ort)
        await i.response.send_message(embed=dashboard_emb, view=DashboardView(i.guild_id, cid, emb.title, event_ort), ephemeral=True)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="tourn_refresh", row=2)
    async def b7(self, i: discord.Interaction, b: discord.ui.Button):
        await self.update_embed(i)

# --- COG ---

class Tournaments(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TournamentView())

    def create_tournament_embed(self, guild_id, title, description, start_time, dates_str, uhrzeit, end_uhrzeit, ort, dl_h, cid):
        lang = i18n.get_guild_lang(guild_id)
        none_txt = i18n.t(lang, "none_list")
        embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
        dl_t = start_time - timedelta(hours=dl_h)
        embed.set_footer(text=i18n.t(lang, "tourn_footer", cid=cid, dl=dl_t.strftime('%d.%m.%Y %H:%M')))

        embed.add_field(name=i18n.t(lang, "tourn_fld_dates"), value=f"{dates_str}, {uhrzeit} - {end_uhrzeit}", inline=True)
        embed.add_field(name=i18n.t(lang, "tourn_fld_loc"), value=f"[{ort}](https://maps.google.com/?q={urllib.parse.quote(ort)})", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(name=i18n.t(lang, "tourn_fld_commit", solo=0, total=0), value=none_txt, inline=False)
        embed.add_field(name="❔ (0)", value=none_txt, inline=True)
        embed.add_field(name="❌ (0)", value=none_txt, inline=True)
        return embed

    @app_commands.command(name="tournament", description="Central dashboard for tournaments, series & participants")
    @app_commands.check(check_tournament_hub_auth)
    async def tournament(self, i: discord.Interaction):
        if not i.guild_id:
            await i.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return

        u_lang = i18n.get_interaction_lang(i, prefer_guild=False)
        settings = data_manager.get_server_settings(i.guild_id)
        default_dl = int(settings.get("tournament_deadline_hours", 48))

        can_create = can_manage = False
        if i.user.id in data_manager.DEVELOPER_IDS or i.user.guild_permissions.administrator:
            can_create = can_manage = True
        elif isinstance(i.user, discord.Member):
            allowed_c = data_manager.get_allowed_roles(str(i.guild.id), "tournament")
            allowed_m = data_manager.get_allowed_roles(str(i.guild.id), "tournament_participants")
            user_roles = [str(r.id) for r in i.user.roles]
            if set(allowed_c) & set(user_roles): can_create = True
            if set(allowed_m) & set(user_roles): can_manage = True

        events = get_recent_tournaments(i.guild.id)
        embed = discord.Embed(
            title=i18n.t(u_lang, "tourn_hub_title"),
            description=i18n.t(u_lang, "tourn_hub_desc"),
            color=discord.Color.blue()
        )
        await i.response.send_message(embed=embed, view=TournamentMainMenu(events, can_create, can_manage, default_dl), ephemeral=True)

    @app_commands.command(name="tournament_manual", description="[Developer] Creates a tournament in the current or specified channel")
    @app_commands.describe(title="Tournament title", description="Description", location="Location / City", deadline_hours="Deadline hours before start", channel_name="Optional channel name")
    @app_commands.check(is_developer)
    async def tournament_manual(self, i: discord.Interaction, title: str, description: str, location: str, deadline_hours: int, channel_name: str = None):
        meta = {"channel_name": channel_name, "title": title, "description": description, "ort": location, "deadline_stunden": deadline_hours}
        await i.response.send_message(f"⚙️ **Manual Tournament: {title}**\nSelect schedule type:", view=TournamentTypeView(meta), ephemeral=True)

    @app_commands.command(name="tournament_update_old", description="[Developer] Refreshes all tournament messages on this server")
    @app_commands.check(is_developer)
    async def tournament_update_old(self, i: discord.Interaction):
        if not i.guild_id:
            return
        await i.response.defer(ephemeral=True)
        rows = get_recent_tournaments(i.guild_id)
        g_lang = i18n.get_guild_lang(i.guild_id)

        count, errors = 0, 0
        for _, title, ch_id, msg_id in rows:
            try:
                ch = i.guild.get_channel(int(ch_id)) or await i.guild.fetch_channel(int(ch_id))
                msg = await ch.fetch_message(int(msg_id))
                if msg.author.id != self.bot.user.id:
                    errors += 1
                    continue
                view = TournamentView(g_lang)
                await view.update_embed(msg)
                count += 1
                await asyncio.sleep(2.5)
            except Exception as e:
                print(f"Refresh error for {title}: {e}")
                errors += 1
        await i.followup.send(f"✅ Updated `{count}` tournaments on **{i.guild.name}** (`{errors}` skipped).", ephemeral=True)

    @tournament.error
    @tournament_manual.error
    @tournament_update_old.error
    async def tournament_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Tournaments(bot))
