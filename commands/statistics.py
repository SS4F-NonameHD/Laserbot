import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import aiohttp
import csv
import io
import re
import data_manager
import i18n

def get_csv_export_url(url):
    if not url:
        return None
    if "/edit" in url:
        return url.split("/edit")[0] + "/export?format=csv"
    return url

async def is_authorized_stats(interaction: discord.Interaction) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if interaction.guild_id and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
        allowed = data_manager.get_allowed_roles(str(interaction.guild_id), "statistics")
        if set(allowed) & set([str(r.id) for r in interaction.user.roles]):
            return True
    return False

async def is_authorized_details(interaction: discord.Interaction) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if interaction.guild_id and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
        allowed = data_manager.get_allowed_roles(str(interaction.guild_id), "statistics_details")
        if set(allowed) & set([str(r.id) for r in interaction.user.roles]):
            return True
    return False

async def fetch_and_build_historie(guild_id, mode_filter="All"):
    settings = data_manager.get_server_settings(guild_id)
    sheet_url = settings.get("google_sheet_url")
    csv_url = get_csv_export_url(sheet_url)
    lang = settings["language"]

    if not csv_url:
        return None, None, i18n.t(lang, "stat_sheet_missing")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(csv_url, timeout=8) as resp:
                if resp.status != 200:
                    return None, None, f"❌ Failed to fetch Google Sheet (HTTP {resp.status})."
                csv_text = await resp.text(encoding='utf-8')

        rows = list(csv.reader(io.StringIO(csv_text)))
        if len(rows) < 3:
            return None, None, "❌ Google Sheet does not contain enough rows."

        category_row, name_row, data = rows[0], rows[1], rows[2:]
        unique_modes = sorted(list({r[1].strip() for r in data if len(r) > 1 and r[1].strip()}))

        embed_historie = discord.Embed(title="📊 Player Statistics (Google Sheet)", color=discord.Color.gold())
        desc = f"[🔗 Open Google Sheet]({sheet_url})\n\n"
        if mode_filter != "All":
            desc += f"**Mode Filter:** `{mode_filter}`\n\n"
        embed_historie.description = desc

        player_stats = {}
        current_category = ""

        for i_col in range(len(name_row)):
            if i_col < len(category_row) and category_row[i_col].strip():
                current_category = category_row[i_col].strip()

            if current_category.lower() == "active players":
                player_name = name_row[i_col].strip()
                if not player_name or player_name.lower() in ('turnier', 'tournament', 'event', 'ort', 'location', 'modus', 'mode', 'datum', 'date', 'platzierung', 'rank', 'name', 'team'):
                    continue

                count, sum_platz = 0, 0
                for row in data:
                    if mode_filter != "All":
                        if len(row) <= 1 or row[1].strip().lower() != mode_filter.lower():
                            continue
                    if i_col < len(row):
                        match = re.search(r'\d+', row[i_col].strip())
                        if match:
                            count += 1
                            sum_platz += int(match.group())

                if count > 0:
                    player_stats[player_name] = {'count': count, 'avg': sum_platz / count}

        if not player_stats:
            embed_historie.description += "❌ No placements found for this filter."
        else:
            sorted_players = sorted(player_stats.items(), key=lambda x: (-x[1]['count'], x[1]['avg']))
            chunk = ""
            for name, stats in sorted_players:
                line = f"**{name}** ➔ {stats['count']} events | ⌀ Rank {stats['avg']:.1f}\n"
                if len(chunk) + len(line) > 1000:
                    embed_historie.add_field(name="Standings", value=chunk, inline=False)
                    chunk = line
                else:
                    chunk += line
            if chunk:
                embed_historie.add_field(name="Standings", value=chunk, inline=False)

        embed_historie.set_footer(text="Evaluated from 'Active Players' columns.")
        return embed_historie, unique_modes, None
    except Exception as e:
        return None, None, f"❌ Error reading sheet: {e}"

class CustomDateRangeModal(discord.ui.Modal, title="Custom Timeframe"):
    start_date = discord.ui.TextInput(label="Start Date (DD.MM.YYYY)", placeholder="01.01.2026", required=True, min_length=10, max_length=10)
    end_date = discord.ui.TextInput(label="End Date (DD.MM.YYYY)", placeholder="31.12.2026", required=True, min_length=10, max_length=10)

    def __init__(self, stat_select, current_mode):
        super().__init__()
        self.stat_select = stat_select
        self.current_mode = current_mode

    async def on_submit(self, interaction: discord.Interaction):
        try:
            st = datetime.strptime(self.start_date.value, "%d.%m.%Y")
            ed = datetime.strptime(self.end_date.value, "%d.%m.%Y").replace(hour=23, minute=59)
            if st > ed:
                await interaction.response.send_message("❌ Start date must be before end date.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            await self.stat_select.generate_training_stats(interaction, time_filter=("custom", st, ed), current_mode=self.current_mode)
        except ValueError:
            await interaction.response.send_message("❌ Invalid format! Use DD.MM.YYYY.", ephemeral=True)

class TrainingYearSelect(discord.ui.Select):
    def __init__(self, available_years, current_filter):
        options = [
            discord.SelectOption(label="All Time", value="All", default=(current_filter == "All"), emoji="📅"),
            discord.SelectOption(label="Last 6 Months", value="6m", default=(current_filter == "6m"), emoji="⏳"),
            discord.SelectOption(label="Last 12 Months", value="12m", default=(current_filter == "12m"), emoji="⌛"),
            discord.SelectOption(label="Custom Range...", value="custom", default=(current_filter == "custom"), emoji="✏️")
        ]
        for y in available_years[:21]:
            options.append(discord.SelectOption(label=f"Year {y}", value=y, default=(current_filter == y), emoji="📆"))
        super().__init__(placeholder="Filter by timeframe...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        stat_select = discord.utils.get(self.view.children, custom_id="stat_select_main") or StatistikSelect()
        if self.values[0] == "custom":
            await interaction.response.send_modal(CustomDateRangeModal(stat_select, self.view.current_mode))
        else:
            await interaction.response.defer(ephemeral=True)
            await stat_select.generate_training_stats(interaction, time_filter=self.values[0], current_mode=self.view.current_mode)

class TrainingStatsView(discord.ui.View):
    def __init__(self, embed_std, embed_det, embed_guest, available_years=None, current_filter="All", current_mode="std"):
        super().__init__(timeout=300)
        self.embed_std = embed_std
        self.embed_det = embed_det
        self.embed_guest = embed_guest
        self.current_mode = current_mode

        self.btn_std = discord.ui.Button(label="Attendance Rate", style=discord.ButtonStyle.primary, emoji="📊", disabled=(current_mode == "std"))
        self.btn_std.callback = self.show_std
        self.btn_det = discord.ui.Button(label="Detailed Breakdown", style=discord.ButtonStyle.secondary, emoji="🔍", disabled=(current_mode == "det"))
        self.btn_det.callback = self.show_det
        self.btn_guest = discord.ui.Button(label="Guests / Unassigned", style=discord.ButtonStyle.secondary, emoji="👤", disabled=(current_mode == "guest"))
        self.btn_guest.callback = self.show_guest

        self.add_item(self.btn_std)
        self.add_item(self.btn_det)
        self.add_item(self.btn_guest)
        if available_years:
            self.add_item(TrainingYearSelect(available_years, current_filter))
        self.add_item(StatistikSelect())

    async def show_std(self, interaction: discord.Interaction):
        self.current_mode = "std"
        self.btn_std.disabled, self.btn_det.disabled, self.btn_guest.disabled = True, False, False
        await interaction.response.edit_message(embed=self.embed_std, view=self)

    async def show_det(self, interaction: discord.Interaction):
        if not await is_authorized_details(interaction):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)
            return
        self.current_mode = "det"
        self.btn_det.disabled, self.btn_std.disabled, self.btn_guest.disabled = True, False, False
        await interaction.response.edit_message(embed=self.embed_det, view=self)

    async def show_guest(self, interaction: discord.Interaction):
        if not await is_authorized_details(interaction):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)
            return
        self.current_mode = "guest"
        self.btn_guest.disabled, self.btn_std.disabled, self.btn_det.disabled = True, False, False
        await interaction.response.edit_message(embed=self.embed_guest, view=self)

class ModusSelect(discord.ui.Select):
    def __init__(self, options, parent_view):
        self.parent_view = parent_view
        super().__init__(placeholder="Filter by game mode...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.update_historie_mode(interaction, self.values[0])

class TournamentStatsView(discord.ui.View):
    def __init__(self, guild_id, embed_beteiligung, show_sheet_btn=False):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.embed_beteiligung = embed_beteiligung
        self.show_sheet_btn = show_sheet_btn

        self.btn_beteiligung = discord.ui.Button(label="Participation Rate", style=discord.ButtonStyle.primary, emoji="📊", disabled=True)
        self.btn_beteiligung.callback = self.show_beteiligung

        self.btn_historie = discord.ui.Button(label="Google Sheet History", style=discord.ButtonStyle.secondary, emoji="📈")
        self.btn_historie.callback = self.show_historie

        self.stat_select = StatistikSelect()
        self.modus_select = None
        self.refresh_layout(False)

    def refresh_layout(self, show_modus_filter):
        self.clear_items()
        self.add_item(self.btn_beteiligung)
        if self.show_sheet_btn:
            self.add_item(self.btn_historie)
        if show_modus_filter and self.modus_select:
            self.add_item(self.modus_select)
        self.add_item(self.stat_select)

    async def show_beteiligung(self, interaction: discord.Interaction):
        self.btn_beteiligung.disabled = True
        self.btn_historie.disabled = False
        self.refresh_layout(False)
        await interaction.response.edit_message(embed=self.embed_beteiligung, view=self)

    async def show_historie(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed, modes, err = await fetch_and_build_historie(self.guild_id, "All")
        if err:
            await interaction.followup.send(err, ephemeral=True)
            return
        self.btn_beteiligung.disabled = False
        self.btn_historie.disabled = True
        options = [discord.SelectOption(label="All Modes", value="All", default=True)] + [
            discord.SelectOption(label=m[:95], value=m) for m in modes[:24]
        ]
        self.modus_select = ModusSelect(options, self)
        self.refresh_layout(True)
        await interaction.edit_original_response(embed=embed, view=self)

    async def update_historie_mode(self, interaction: discord.Interaction, mode: str):
        await interaction.response.defer(ephemeral=True)
        embed, _, err = await fetch_and_build_historie(self.guild_id, mode)
        if err:
            await interaction.followup.send(err, ephemeral=True)
            return
        for opt in self.modus_select.options:
            opt.default = (opt.value == mode)
        await interaction.edit_original_response(embed=embed, view=self)

class StatistikSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Trainings", description="Attendance rate & breakdown", emoji="🏟️", value="training"),
            discord.SelectOption(label="Tournaments", description="Participation & optional Sheet history", emoji="🏆", value="tournament"),
            discord.SelectOption(label="iPlayLaserforce", description="Server member profile directory", emoji="🔫", value="laserforce")
        ]
        super().__init__(placeholder="Choose category...", min_values=1, max_values=1, options=options, custom_id="stat_select_main")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.values[0] == "training":
            await self.generate_training_stats(interaction)
        elif self.values[0] == "tournament":
            await self.generate_tournament_stats(interaction)
        elif self.values[0] == "laserforce":
            await self.generate_lf_directory(interaction)

    async def generate_lf_directory(self, interaction: discord.Interaction):
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        tags = data_manager.get_all_lf_tags()

        # Datenschutz-Isolation: Zeige ausschließlich Mitglieder an, die tatsächlich auf DIESEM Server sind!
        player_links = []
        for uid, tag in tags.items():
            if not str(uid).isdigit():
                continue
            member = interaction.guild.get_member(int(uid))
            if member and not member.bot:
                url = f"https://v2.iplaylaserforce.com/iframe.php?t={tag}"
                player_links.append((member.display_name, uid, url))

        if not player_links:
            await interaction.followup.send(i18n.t(u_lang, "stat_lf_empty"), ephemeral=True)
            return

        player_links.sort(key=lambda x: x[0].lower())
        embed = discord.Embed(
            title=i18n.t(u_lang, "stat_lf_title", guild=interaction.guild.name),
            description=i18n.t(u_lang, "stat_lf_desc", count=len(player_links)),
            color=discord.Color.red()
        )

        chunk = ""
        for idx, (_, uid, url) in enumerate(player_links, 1):
            line = f"**#{idx}** <@{uid}> ➔ [Profile]({url})\n"
            if len(chunk) + len(line) > 1000:
                embed.add_field(name="Players", value=chunk, inline=False)
                chunk = line
            else:
                chunk += line
        if chunk:
            embed.add_field(name="Players", value=chunk, inline=False)

        await interaction.edit_original_response(embed=embed, view=StatistikView())

    async def generate_training_stats(self, interaction: discord.Interaction, time_filter="All", current_mode="std"):
        guild = interaction.guild
        settings = data_manager.get_server_settings(guild.id)
        allowed_roles = data_manager.get_allowed_roles(str(guild.id), "training_participate")
        team_role_id = settings.get("team_role_id")

        target_role_ids = set(allowed_roles) if allowed_roles else ({str(team_role_id)} if team_role_id else set())
        if not target_role_ids:
            await interaction.followup.send(i18n.t(interaction, "team_role_missing_cfg"), ephemeral=True)
            return

        eligible_members = [
            m for m in guild.members
            if not m.bot and not data_manager.is_member_observer(m) and (target_role_ids & {str(r.id) for r in m.roles})
        ]

        events, entries = data_manager.get_training_stats_full(guild.id)
        start_bound, end_bound = None, None
        title_desc, current_filter_val = "All Time", "All"
        now = datetime.now()

        if isinstance(time_filter, tuple) and time_filter[0] == "custom":
            start_bound, end_bound = time_filter[1], time_filter[2]
            title_desc = f"{start_bound.strftime('%d.%m.%Y')} – {end_bound.strftime('%d.%m.%Y')}"
            current_filter_val = "custom"
        elif time_filter == "6m":
            end_bound, start_bound = now, now - timedelta(days=183)
            title_desc, current_filter_val = "Last 6 Months", "6m"
        elif time_filter == "12m":
            end_bound, start_bound = now, now - timedelta(days=365)
            title_desc, current_filter_val = "Last 12 Months", "12m"
        elif time_filter != "All":
            try:
                start_bound = datetime(int(time_filter), 1, 1)
                end_bound = datetime(int(time_filter), 12, 31, 23, 59)
                title_desc, current_filter_val = f"Year {time_filter}", time_filter
            except:
                pass

        events_per_year_global, valid_cids = set(), set()
        total_events_in_range = 0

        for tid, cid in events:
            try:
                events_per_year_global.add(str(cid).split('-')[0])
                m = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}:\d{2})', tid or "")
                evt_date = datetime.strptime(m.group(1), "%d.%m.%Y %H:%M") if m else datetime(int(str(cid).split('-')[0]), 1, 1)
                if start_bound and evt_date < start_bound: continue
                if end_bound and evt_date > end_bound: continue
                valid_cids.add(cid)
                total_events_in_range += 1
            except:
                pass

        available_years = sorted(list(events_per_year_global), reverse=True)
        user_aggregated = {str(m.id): {'zusagen': 0, 'vielleicht': 0, 'absagen': 0, 'manuell': 0, 'answered': 0} for m in eligible_members}
        guest_aggregated = {}
        eligible_ids = set(user_aggregated.keys())

        for cid, uid, status, is_manual, dname in entries:
            if cid not in valid_cids:
                continue
            uid_s = str(uid)
            if uid_s in eligible_ids:
                user_aggregated[uid_s]['answered'] += 1
                if status == 'Zusagen': user_aggregated[uid_s]['zusagen'] += 1
                elif status == 'Vielleicht': user_aggregated[uid_s]['vielleicht'] += 1
                elif status == 'Absagen': user_aggregated[uid_s]['absagen'] += 1
                if is_manual: user_aggregated[uid_s]['manuell'] += 1
            else:
                if uid_s not in guest_aggregated:
                    mem = guild.get_member(int(uid_s)) if uid_s.isdigit() else None
                    final_name = mem.display_name if mem else (dname or uid_s)
                    guest_aggregated[uid_s] = {'name': final_name, 'zusagen': 0, 'absagen': 0, 'vielleicht': 0, 'manuell': 0, 'answered': 0}
                guest_aggregated[uid_s]['answered'] += 1
                if status == 'Zusagen': guest_aggregated[uid_s]['zusagen'] += 1
                elif status == 'Vielleicht': guest_aggregated[uid_s]['vielleicht'] += 1
                elif status == 'Absagen': guest_aggregated[uid_s]['absagen'] += 1
                if is_manual: guest_aggregated[uid_s]['manuell'] += 1

        embed_std = discord.Embed(title="📊 Training Statistics", color=discord.Color.blue())
        embed_det = discord.Embed(title="📊 Training Statistics (Detailed)", color=discord.Color.purple())
        embed_guest = discord.Embed(title="📊 Training Statistics (Guests)", color=discord.Color.teal())

        if total_events_in_range == 0:
            embed_std.description = embed_det.description = embed_guest.description = f"No trainings found in **{title_desc}**."
        else:
            embed_std.description = f"Attendance of **{len(eligible_members)}** members • **{title_desc}** ({total_events_in_range} trainings)"
            embed_det.description = f"**{title_desc}** ({total_events_in_range} trainings)\n✅ Commit | ❌ Decline | ❔ Maybe | 👻 No Response | Ⓜ️ Manual"
            embed_guest.description = f"Guests / Unassigned (**{len(guest_aggregated)}**) • **{title_desc}** ({total_events_in_range} trainings)"

            user_rates = []
            for m in eligible_members:
                s = user_aggregated[str(m.id)]
                ohne = max(0, total_events_in_range - s['answered'])
                rate = (s['zusagen'] / total_events_in_range) * 100
                user_rates.append((m.display_name, rate, s['zusagen'], s['absagen'], s['vielleicht'], ohne, s['manuell']))
            user_rates.sort(key=lambda x: (-x[1], x[0].lower()))

            c_std, c_det, idx_s, idx_d = "", "", 1, 1
            for name, rate, z, a, v, o, mc in user_rates:
                ls = f"**{name}:** {rate:.1f}% ({z}/{total_events_in_range})\n"
                ld = f"**{name}:** ✅ {z} | ❌ {a} | ❔ {v} | 👻 {o} | Ⓜ️ {mc}\n"
                if len(c_std) + len(ls) > 1000:
                    embed_std.add_field(name=f"Ranking ({idx_s})", value=c_std, inline=False)
                    c_std = ls; idx_s += 1
                else: c_std += ls
                if len(c_det) + len(ld) > 1000:
                    embed_det.add_field(name=f"Details ({idx_d})", value=c_det, inline=False)
                    c_det = ld; idx_d += 1
                else: c_det += ld
            if c_std: embed_std.add_field(name="Ranking", value=c_std, inline=False)
            if c_det: embed_det.add_field(name="Details", value=c_det, inline=False)

            guest_rates = [
                (s['name'], (s['zusagen'] / total_events_in_range) * 100, s['zusagen'], s['absagen'], s['vielleicht'], s['manuell'])
                for s in guest_aggregated.values() if s['answered'] > 0
            ]
            guest_rates.sort(key=lambda x: (-x[1], x[0].lower()))
            c_g = ""
            for name, rate, z, a, v, mc in guest_rates:
                lg = f"**{name}:** {rate:.1f}% ({z}/{total_events_in_range}) | ✅ {z} ❌ {a} ❔ {v} Ⓜ️ {mc}\n"
                if len(c_g) + len(lg) > 1000:
                    embed_guest.add_field(name="Guests", value=c_g, inline=False)
                    c_g = lg
                else: c_g += lg
            embed_guest.add_field(name="Guests", value=c_g if c_g else "None", inline=False)

        view = TrainingStatsView(embed_std, embed_det, embed_guest, available_years, current_filter_val, current_mode)
        active_embed = embed_det if current_mode == "det" else (embed_guest if current_mode == "guest" else embed_std)
        await interaction.edit_original_response(embed=active_embed, view=view)

    async def generate_tournament_stats(self, interaction: discord.Interaction):
        guild = interaction.guild
        settings = data_manager.get_server_settings(guild.id)
        team_role_id = settings.get("team_role_id")
        has_sheet = bool(settings.get("google_sheet_url"))

        team_role = guild.get_role(int(team_role_id)) if team_role_id else None
        if team_role:
            eligible_members = [m for m in guild.members if not m.bot and not data_manager.is_member_observer(m) and team_role in m.roles]
        else:
            eligible_members = [m for m in guild.members if not m.bot and not data_manager.is_member_observer(m)]

        events, zusagen = data_manager.get_tournament_stats(guild.id)
        events_per_year = {}
        for ev in events:
            y = str(ev[0]).split('-')[0]
            events_per_year[y] = events_per_year.get(y, 0) + 1

        zusagen_per_user_year = {}
        for cid, uid in zusagen:
            y = str(cid).split('-')[0]
            zusagen_per_user_year.setdefault(str(uid), {})[y] = zusagen_per_user_year.get(str(uid), {}).get(y, 0) + 1

        embed = discord.Embed(title="🏆 Tournament Participation", color=discord.Color.blue())
        if not events_per_year:
            embed.description = "No tournaments recorded on this server yet."
            await interaction.edit_original_response(embed=embed, view=TournamentStatsView(guild.id, embed, has_sheet))
            return

        embed.description = f"Participation rate across **{len(eligible_members)}** members."
        for year in sorted(events_per_year.keys(), reverse=True):
            total = events_per_year[year]
            if total == 0:
                continue
            user_rates = [
                (m.display_name, (zusagen_per_user_year.get(str(m.id), {}).get(year, 0) / total) * 100, zusagen_per_user_year.get(str(m.id), {}).get(year, 0))
                for m in eligible_members
            ]
            user_rates.sort(key=lambda x: (-x[1], x[0].lower()))
            chunk = ""
            for name, rate, zc in user_rates:
                line = f"**{name}:** {rate:.1f}% ({zc}/{total})\n"
                if len(chunk) + len(line) > 1000:
                    embed.add_field(name=f"📅 {year}", value=chunk, inline=False)
                    chunk = line
                else:
                    chunk += line
            if chunk:
                embed.add_field(name=f"📅 {year}", value=chunk, inline=False)

        await interaction.edit_original_response(embed=embed, view=TournamentStatsView(guild.id, embed, has_sheet))

class StatistikView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(StatistikSelect())

class Statistics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="statistics", description="Opens the server statistics dashboard (Trainings, Tournaments, Laserforce)")
    @app_commands.check(is_authorized_stats)
    async def statistics(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return
        u_lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        embed = discord.Embed(
            title=i18n.t(u_lang, "stat_hub_title"),
            description=i18n.t(u_lang, "stat_hub_desc"),
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, view=StatistikView(), ephemeral=True)

    @app_commands.command(name="lf_set", description="Links a Discord member with their iPlayLaserforce profile tag")
    @app_commands.describe(member="Discord member", tag="Tag from iPlayLaserforce URL (e.g. Y6xKhWK)")
    @app_commands.check(is_authorized_stats)
    async def lf_set(self, interaction: discord.Interaction, member: discord.Member, tag: str):
        if data_manager.set_lf_tag(member.id, tag.strip()):
            await interaction.response.send_message(f"✅ Linked tag `{tag.strip()}` to {member.mention}!", ephemeral=True)
        else:
            await interaction.response.send_message(i18n.t(interaction, "db_error"), ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Statistics(bot))
