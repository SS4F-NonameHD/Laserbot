import discord
from discord import ui, app_commands
from discord.ext import commands
from datetime import datetime
import re
import aiohttp
import csv
import io
import data_manager
import i18n
from commands.tournaments import TournamentView, resolve_tournament_category_and_overwrites, apply_tournament_absences

FALLBACK_MODES = ["Laserball", "Space Marines", "Team Deathmatch", "Highlander", "Gladiator", "Domination", "5v5", "4v4", "3v3", "2v2"]

def _to_csv_url(sheet_url: str) -> str | None:
    if not sheet_url:
        return None
    if "/edit" in sheet_url:
        return sheet_url.split("/edit")[0] + "/export?format=csv"
    return sheet_url

async def get_known_modes(guild_id) -> list[str]:
    settings = data_manager.get_server_settings(guild_id)
    csv_url = _to_csv_url(settings.get("google_sheet_url"))
    if csv_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(csv_url, timeout=1.5) as resp:
                    if resp.status == 200:
                        text = await resp.text(encoding='utf-8')
                        rows = list(csv.reader(io.StringIO(text)))
                        if len(rows) > 2:
                            modes = {r[1].strip() for r in rows[2:] if len(r) > 1 and r[1].strip()}
                            if modes:
                                return list(modes)
        except:
            pass
    return list(FALLBACK_MODES)

async def is_authorized_tournament_import(interaction: discord.Interaction) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if interaction.guild_id and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
        allowed = data_manager.get_allowed_roles(str(interaction.guild_id), "tournament")
        if set(allowed) & set([str(r.id) for r in interaction.user.roles]):
            return True
    return False

class CombinedImportModal(ui.Modal, title="Import as Tournament"):
    titel = ui.TextInput(label="Tournament Title", required=True, max_length=100)
    modus = ui.TextInput(label="Game Mode", required=True, max_length=50)
    ort = ui.TextInput(label="Location / City", required=True, max_length=100)
    termin = ui.TextInput(label="Schedule (DD.MM.YYYY HH:MM-HH:MM)", required=True, max_length=50)
    beschreibung = ui.TextInput(label="Description", style=discord.TextStyle.paragraph, required=False, max_length=4000)

    def __init__(self, pre_titel, pre_modus, pre_ort, pre_termin, pre_desc):
        super().__init__()
        self.titel.default = pre_titel
        self.modus.default = pre_modus
        self.ort.default = pre_ort
        self.termin.default = pre_termin
        self.beschreibung.default = pre_desc

    async def on_submit(self, interaction: discord.Interaction):
        termin_str = self.termin.value.strip()
        match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{2,4})\s+(\d{1,2}:\d{2})\s*(?:-|bis|to|\s)\s*(\d{1,2}:\d{2})', termin_str)
        if match:
            datum_str, start_str, end_str = match.groups()
        else:
            parts = termin_str.split()
            datum_str = parts[0] if parts else datetime.now().strftime("%d.%m.%Y")
            start_str, end_str = "10:00", "18:00"

        try:
            st = datetime.strptime(f"{datum_str} {start_str}", "%d.%m.%Y %H:%M")
        except ValueError:
            await interaction.response.send_message("❌ Invalid schedule format! Please use `DD.MM.YYYY HH:MM-HH:MM`.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        cog = interaction.client.get_cog("Tournaments")
        if not cog:
            await interaction.followup.send("❌ Tournament module not loaded.", ephemeral=True)
            return

        settings = data_manager.get_server_settings(interaction.guild.id)
        g_lang = settings["language"]
        dl_h = int(settings.get("tournament_deadline_hours", 48))

        cat, ow = await resolve_tournament_category_and_overwrites(interaction.guild)

        d_str = st.strftime("%d-%m-%y")
        raw_name = f"{d_str}-{self.modus.value}-{self.ort.value}"
        clean_name = re.sub(r'[^a-zA-Z0-9\s-]', '', raw_name).strip().replace(' ', '-').lower()
        clean_name = re.sub(r'-+', '-', clean_name)[:100] or f"tournament-{d_str}"

        new_ch = await interaction.guild.create_text_channel(name=clean_name, category=cat, overwrites=ow)
        cid = data_manager.get_next_event_id(interaction.guild.id, st.year, "tournaments")

        embed = cog.create_tournament_embed(
            guild_id=interaction.guild.id,
            title=self.titel.value,
            description=self.beschreibung.value,
            start_time=st,
            dates_str=datum_str,
            uhrzeit=start_str,
            end_uhrzeit=end_str,
            ort=self.ort.value,
            dl_h=dl_h,
            cid=cid
        )

        msg = await new_ch.send(embed=embed, view=TournamentView(g_lang))
        try:
            await msg.pin()
        except:
            pass

        data_manager.save_tournament_event(self.titel.value, cid, interaction.guild.id, new_ch.id, msg.id)
        await apply_tournament_absences(interaction.guild, cid, self.titel.value, st, msg)

        await interaction.followup.send(f"✅ Tournament **{cid}** imported into {new_ch.mention}!", ephemeral=True)

class TournamentImport(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(
            name="Import as Tournament",
            callback=self.import_tournament,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def import_tournament(self, interaction: discord.Interaction, message: discord.Message):
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return
        if not await is_authorized_tournament_import(interaction):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)
            return

        content = message.content or ""
        if hasattr(message, 'message_snapshots'):
            for snap in message.message_snapshots:
                snap_content = getattr(snap, 'content', None) or (getattr(snap.message, 'content', None) if hasattr(snap, 'message') else None)
                if snap_content:
                    content += "\n" + snap_content

        if not content.strip() and message.embeds:
            for emb in message.embeds:
                if emb.description: content += "\n" + emb.description
                if emb.title: content = emb.title + "\n" + content

        content = content.strip()
        pre_datum = ""
        pre_titel = "New Tournament"
        pre_ort = "Unknown"
        pre_zeit = "10:00-18:00"
        pre_modus = "Laserball"

        if content:
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            first_line = lines[0] if lines else ""
            pre_titel = re.sub(r'[*_~`]', '', first_line)[:100] or "New Tournament"

            modes = await get_known_modes(interaction.guild_id)
            modes.sort(key=len, reverse=True)
            found_mode = next((m for m in modes if m.lower() in first_line.lower()), None)
            if not found_mode:
                found_mode = next((m for m in modes if m.lower() in content.lower()), None)
            if found_mode:
                pre_modus = found_mode

            date_match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', content)
            if date_match:
                d, m, y = date_match.groups()
                if len(y) == 2: y = "20" + y
                pre_datum = f"{int(d):02d}.{int(m):02d}.{y}"

            time_match = re.search(r'(\d{1,2}:\d{2})\s*(?:-|bis|to|\s)\s*(\d{1,2}:\d{2})', content)
            if time_match:
                pre_zeit = f"{time_match.group(1)}-{time_match.group(2)}"

            loc_match = re.search(r'(?i)(?:ort|location|wo|místo|luogo|lasergame|laserzone|arena)\s*[:\-]\s*([^\n]+)', content)
            if loc_match:
                pre_ort = loc_match.group(1).strip()[:100]
            else:
                known_locations = [
                    "Beroun", "Zell am Main", "Lüneburg", "Ricany", "Říčany", "Prague", "Praha",
                    "Neufahrn", "Munich", "München", "Augsburg", "Ingolstadt", "Kassel", "Würzburg",
                    "Nürnberg", "Berlin", "Frankfurt", "Leipzig", "Stuttgart", "Milan", "Milano", "Rome", "Bologna"
                ]
                for loc in known_locations:
                    if loc.lower() in first_line.lower() or loc.lower() in content.lower():
                        pre_ort = loc
                        break

        pre_termin = f"{pre_datum} {pre_zeit}".strip()
        await interaction.response.send_modal(CombinedImportModal(pre_titel, pre_modus, pre_ort, pre_termin, content[:4000]))

async def setup(bot):
    await bot.add_cog(TournamentImport(bot))
