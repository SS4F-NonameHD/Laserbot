import discord
from discord import app_commands, ui
from discord.ext import commands
import uuid
import data_manager
import i18n

async def is_authorized_orgateam(interaction: discord.Interaction) -> bool:
    if interaction.user.id in data_manager.DEVELOPER_IDS:
        return True
    if interaction.guild_id and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
        allowed = data_manager.get_allowed_roles(str(interaction.guild_id), "orgateam")
        if set(allowed) & set([str(r.id) for r in interaction.user.roles]):
            return True
    return False

# --- ZIMMER ---
class RoomNameModal(ui.Modal, title="Assign Room Name"):
    room_name = ui.TextInput(label="Room (e.g. Double 1, Single Smith)", required=True, max_length=50)

    def __init__(self, guild_id, tourn_id, user_ids, hotel_id, event_title):
        super().__init__()
        self.guild_id = guild_id
        self.tourn_id = tourn_id
        self.user_ids = user_ids
        self.hotel_id = hotel_id
        self.event_title = event_title

    async def on_submit(self, i: discord.Interaction):
        success = True
        for uid in self.user_ids:
            if not data_manager.assign_hotel_room(self.guild_id, self.tourn_id, uid, self.hotel_id, self.room_name.value.strip()):
                success = False
        if success:
            await i.response.send_message(f"✅ Assigned {len(self.user_ids)} player(s) to **{self.room_name.value}**! *(Click Refresh)*", ephemeral=True)
        else:
            await i.response.send_message(i18n.t(i, "db_error"), ephemeral=True)

class HotelSelect(ui.Select):
    def __init__(self, guild_id, tourn_id, user_ids, event_title, event_ort):
        self.guild_id = guild_id
        self.tourn_id = tourn_id
        self.user_ids = user_ids
        self.event_title = event_title

        hotels = data_manager.get_hotels(guild_id)
        sorted_hotels = sorted(
            hotels,
            key=lambda h: 0 if (h[1].lower() in (event_ort or "").lower() or h[1].lower() in (event_title or "").lower()) else 1
        )
        options = [
            discord.SelectOption(label=f"{h[1].capitalize()} — {h[2][:75]}", value=str(h[0]), emoji="🏨")
            for h in sorted_hotels[:25]
        ]
        if not options:
            options = [discord.SelectOption(label="No hotels configured (/hotel_add)", value="0")]

        super().__init__(placeholder="Step 2: Select hotel...", options=options, custom_id=f"hot_sel_{uuid.uuid4().hex[:8]}")

    async def callback(self, i: discord.Interaction):
        if self.values[0] == "0":
            await i.response.send_message("❌ Please add a hotel via `/hotel_add` first.", ephemeral=True)
            return
        await i.response.send_modal(RoomNameModal(self.guild_id, self.tourn_id, self.user_ids, int(self.values[0]), self.event_title))

class UserAssignSelect(ui.Select):
    def __init__(self, guild_id, tourn_id, event_title, event_ort):
        self.guild_id = guild_id
        self.tourn_id = tourn_id
        self.event_title = event_title
        self.event_ort = event_ort

        data = data_manager.get_travel_planning_data(guild_id, tourn_id)
        users = [r for r in data if not r[11] and not r[3]]

        options = []
        for r in users[:25]:
            pref = r[8]
            pref_text = "Single Room" if pref == "single" else ("Double Room" if pref == "double" else "Shared OK")
            options.append(discord.SelectOption(label=r[1][:100], description=pref_text, value=str(r[0]), emoji="👤"))

        if not options:
            options = [discord.SelectOption(label="Everyone assigned", value="0")]

        max_val = min(len(options), 25) if options[0].value != "0" else 1
        super().__init__(placeholder="Step 1: Select player(s)...", min_values=1, max_values=max_val, options=options, custom_id=f"rm_add_{uuid.uuid4().hex[:8]}")

    async def callback(self, i: discord.Interaction):
        if self.values[0] == "0":
            await i.response.send_message("❌ Nobody unassigned.", ephemeral=True)
            return
        v = ui.View()
        v.add_item(HotelSelect(self.guild_id, self.tourn_id, self.values, self.event_title, self.event_ort))
        await i.response.send_message(f"**{len(self.values)} player(s) selected.**", view=v, ephemeral=True)

class UserRemoveSelect(ui.Select):
    def __init__(self, guild_id, tourn_id, event_title):
        self.guild_id = guild_id
        self.tourn_id = tourn_id
        data = data_manager.get_travel_planning_data(guild_id, tourn_id)
        users = [r for r in data if r[11] is not None]

        options = [
            discord.SelectOption(label=r[1][:100], description=f"Room: {r[12]}", value=str(r[0]), emoji="🗑️")
            for r in users[:25]
        ]
        if not options:
            options = [discord.SelectOption(label="No rooms assigned", value="0")]
        max_val = min(len(options), 25) if options[0].value != "0" else 1
        super().__init__(placeholder="Remove room assignment...", min_values=1, max_values=max_val, options=options, custom_id=f"rm_rem_{uuid.uuid4().hex[:8]}")

    async def callback(self, i: discord.Interaction):
        if self.values[0] == "0":
            await i.response.send_message("❌ No room assignments.", ephemeral=True)
            return
        for uid in self.values:
            data_manager.remove_hotel_room(self.guild_id, self.tourn_id, uid)
        await i.response.send_message("✅ Room assignment(s) removed! *(Click Refresh)*", ephemeral=True)

# --- AUTOS ---
class CarDirectionSelect(ui.Select):
    def __init__(self, guild_id, tourn_id, user_ids, event_title, car_name):
        self.guild_id = guild_id
        self.tourn_id = tourn_id
        self.user_ids = user_ids
        self.car_name = car_name
        options = [
            discord.SelectOption(label="Outbound & Return", value="both", emoji="🔁"),
            discord.SelectOption(label="Outbound only", value="out", emoji="➡️"),
            discord.SelectOption(label="Return only", value="ret", emoji="⬅️")
        ]
        super().__init__(placeholder="Select route...", min_values=1, max_values=1, options=options, custom_id=f"car_dir_{uuid.uuid4().hex[:8]}")

    async def callback(self, i: discord.Interaction):
        data = data_manager.get_travel_planning_data(self.guild_id, self.tourn_id)
        success = True
        for uid in self.user_ids:
            u_row = next((r for r in data if str(r[0]) == str(uid)), None)
            is_drv = bool(u_row[7]) if u_row else False
            if not data_manager.assign_carpool(self.guild_id, self.tourn_id, uid, self.car_name, is_drv, self.values[0]):
                success = False
        if success:
            await i.response.send_message(f"✅ Assigned to **{self.car_name}**! *(Click Refresh)*", ephemeral=True)
        else:
            await i.response.send_message(i18n.t(i, "db_error"), ephemeral=True)

class CarNameModal(ui.Modal, title="Create New Car"):
    car_name = ui.TextInput(label="Car Name / Number (e.g. Van 1, Car 2)", required=True, max_length=50)

    def __init__(self, guild_id, tourn_id, user_ids, event_title):
        super().__init__()
        self.guild_id = guild_id
        self.tourn_id = tourn_id
        self.user_ids = user_ids
        self.event_title = event_title

    async def on_submit(self, i: discord.Interaction):
        v = ui.View()
        v.add_item(CarDirectionSelect(self.guild_id, self.tourn_id, self.user_ids, self.event_title, self.car_name.value.strip()))
        await i.response.send_message("Step 3: Select route:", view=v, ephemeral=True)

class CarSelect(ui.Select):
    def __init__(self, guild_id, tourn_id, user_ids, event_title):
        self.guild_id = guild_id
        self.tourn_id = tourn_id
        self.user_ids = user_ids
        self.event_title = event_title

        data = data_manager.get_travel_planning_data(guild_id, tourn_id)
        existing_cars = sorted(list({r[13] for r in data if r[13]} | {r[15] for r in data if r[15]}))

        options = [discord.SelectOption(label=c, value=c, emoji="🚗") for c in existing_cars[:24]]
        options.append(discord.SelectOption(label="Create new car...", value="NEW_CAR", emoji="➕"))
        super().__init__(placeholder="Step 2: Select car...", options=options, custom_id=f"car_sel_{uuid.uuid4().hex[:8]}")

    async def callback(self, i: discord.Interaction):
        if self.values[0] == "NEW_CAR":
            await i.response.send_modal(CarNameModal(self.guild_id, self.tourn_id, self.user_ids, self.event_title))
        else:
            v = ui.View()
            v.add_item(CarDirectionSelect(self.guild_id, self.tourn_id, self.user_ids, self.event_title, self.values[0]))
            await i.response.send_message("Step 3: Select route:", view=v, ephemeral=True)

class UserAssignCarSelect(ui.Select):
    def __init__(self, guild_id, tourn_id, event_title):
        self.guild_id = guild_id
        self.tourn_id = tourn_id
        self.event_title = event_title

        data = data_manager.get_travel_planning_data(guild_id, tourn_id)
        users = [r for r in data if not r[13] or not r[15]]

        options = []
        for r in users[:25]:
            car_info = "Offering car" if r[4] else ("Has license" if r[7] else "Passenger")
            options.append(discord.SelectOption(label=r[1][:100], description=car_info, value=str(r[0]), emoji="👤"))
        if not options:
            options = [discord.SelectOption(label="Everyone assigned to cars", value="0")]

        max_val = min(len(options), 25) if options[0].value != "0" else 1
        super().__init__(placeholder="Step 1: Select player(s)...", min_values=1, max_values=max_val, options=options, custom_id=f"car_add_{uuid.uuid4().hex[:8]}")

    async def callback(self, i: discord.Interaction):
        if self.values[0] == "0":
            await i.response.send_message("❌ Nobody available.", ephemeral=True)
            return
        v = ui.View()
        v.add_item(CarSelect(self.guild_id, self.tourn_id, self.values, self.event_title))
        await i.response.send_message(f"**{len(self.values)} player(s) selected.**", view=v, ephemeral=True)

class UserRemoveCarSelect(ui.Select):
    def __init__(self, guild_id, tourn_id, event_title):
        self.guild_id = guild_id
        self.tourn_id = tourn_id
        data = data_manager.get_travel_planning_data(guild_id, tourn_id)
        users = [r for r in data if r[13] is not None or r[15] is not None]

        options = []
        for r in users[:25]:
            desc = f"{'Out: ' + r[13] + ' ' if r[13] else ''}{'Ret: ' + r[15] if r[15] else ''}".strip()
            options.append(discord.SelectOption(label=r[1][:100], description=desc[:100], value=str(r[0]), emoji="🚪"))
        if not options:
            options = [discord.SelectOption(label="No car assignments", value="0")]

        max_val = min(len(options), 25) if options[0].value != "0" else 1
        super().__init__(placeholder="Remove player(s) from car...", min_values=1, max_values=max_val, options=options, custom_id=f"car_rem_{uuid.uuid4().hex[:8]}")

    async def callback(self, i: discord.Interaction):
        if self.values[0] == "0":
            await i.response.send_message("❌ No assignments.", ephemeral=True)
            return
        for uid in self.values:
            data_manager.remove_carpool(self.guild_id, self.tourn_id, uid, "both")
        await i.response.send_message("✅ Removed from carpool! *(Click Refresh)*", ephemeral=True)

class CarDeleteSelect(ui.Select):
    def __init__(self, guild_id, tourn_id, event_title):
        self.guild_id = guild_id
        self.tourn_id = tourn_id
        data = data_manager.get_travel_planning_data(guild_id, tourn_id)
        existing_cars = sorted(list({r[13] for r in data if r[13]} | {r[15] for r in data if r[15]}))

        options = [discord.SelectOption(label=c, value=c, emoji="💥") for c in existing_cars[:25]]
        if not options:
            options = [discord.SelectOption(label="No cars exist", value="0")]
        super().__init__(placeholder="Dissolve entire car...", options=options, custom_id=f"car_del_{uuid.uuid4().hex[:8]}")

    async def callback(self, i: discord.Interaction):
        if self.values[0] == "0":
            await i.response.send_message("❌ No cars exist.", ephemeral=True)
            return
        data_manager.delete_carpool(self.guild_id, self.tourn_id, self.values[0], "both")
        await i.response.send_message(f"✅ Car **{self.values[0]}** dissolved! *(Click Refresh)*", ephemeral=True)

# --- DASHBOARD ---
def generate_dashboard_embed(guild_id, tourn_id, event_title, event_ort=""):
    lang = i18n.get_guild_lang(guild_id)
    data = data_manager.get_travel_planning_data(guild_id, tourn_id)
    hotels = {h[0]: (h[2], h[3]) for h in data_manager.get_hotels(guild_id)}

    embed = discord.Embed(
        title=i18n.t(lang, "orga_title", title=event_title),
        description=i18n.t(lang, "orga_desc"),
        color=discord.Color.teal()
    )
    embed.set_footer(text=f"ID: {tourn_id}")

    needs_room, alt_acc, potential_drivers = [], [], []
    rooms, cars_out, cars_ret = {}, {}, {}
    zusagen_ids = [r[0] for r in data]

    for row in data:
        uid, name, n_hotel, alt, h_car, arr, dep, lic, pref, partner_id, def_pass, h_id, r_name, c_out, drv_out, c_ret, drv_ret = row
        safe_arr = arr[:3] if arr else "?"
        safe_dep = dep[:3] if dep else "?"

        pref_text = "Shared"
        if pref == 'single':
            pref_text = "Single"
        elif pref == 'double':
            if partner_id and partner_id in zusagen_ids:
                partner_name = next((r[1] for r in data if r[0] == partner_id), "Partner")
                pref_text = f"Double w/ {partner_name}"
            else:
                pref_text = "Single (Partner absent)"

        info = f"({safe_arr}–{safe_dep}, {pref_text})"

        if h_id and r_name:
            rooms.setdefault(h_id, {}).setdefault(r_name, []).append(f"• {name} {info}")
        elif alt:
            alt_acc.append(f"• {name} ({alt})")
        else:
            needs_room.append(f"• {name} {info}")

        if c_out:
            cars_out.setdefault(c_out, []).append({"name": name, "is_owner": bool(h_car), "can_drive": bool(lic)})
        if c_ret:
            cars_ret.setdefault(c_ret, []).append({"name": name, "is_owner": bool(h_car), "can_drive": bool(lic)})
        if h_car:
            potential_drivers.append(name)

    embed.add_field(
        name=i18n.t(lang, "orga_need_room"),
        value="\n".join(needs_room) if needs_room else i18n.t(lang, "orga_all_housed"),
        inline=False
    )

    for h_id, r_dict in rooms.items():
        h_name, h_link = hotels.get(h_id, ("Unknown Hotel", ""))
        val = f"🔗 [Booking Link]({h_link})\n\n" if h_link else ""
        for r_name, users in r_dict.items():
            val += f"**{r_name}**\n" + "\n".join(users) + "\n\n"
        embed.add_field(name=f"🏨 {h_name}", value=val.strip()[:1024], inline=False)

    if alt_acc:
        embed.add_field(name=i18n.t(lang, "tourn_fld_alt"), value="\n".join(alt_acc)[:1024], inline=False)
    if potential_drivers:
        embed.add_field(name=i18n.t(lang, "orga_offer_car"), value=", ".join(potential_drivers)[:1024], inline=False)

    def build_car_text(car_dict):
        text = ""
        for c_id, u_list in car_dict.items():
            u_list.sort(key=lambda x: (not x["is_owner"], not x["can_drive"]))
            prefix = "" if c_id.lower().startswith(("auto", "car", "bus", "kfz", "van")) else "Car "
            text += f"**{prefix}{c_id}:**\n"
            for u in u_list:
                marker = " 🚗" if u["is_owner"] else (" 🛞" if u["can_drive"] else "")
                text += f"  └ {u['name']}{marker}\n"
            text += "\n"
        return text.strip()

    out_text = build_car_text(cars_out)
    ret_text = build_car_text(cars_ret)
    if out_text:
        embed.add_field(name=i18n.t(lang, "tourn_fld_car_out"), value=out_text[:1024], inline=True)
    if ret_text:
        embed.add_field(name=i18n.t(lang, "tourn_fld_car_ret"), value=ret_text[:1024], inline=True)

    return embed

class DashboardView(ui.View):
    def __init__(self, guild_id, tourn_id, event_title, event_ort):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.tourn_id = tourn_id
        self.event_title = event_title
        self.event_ort = event_ort

    @ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
    async def btn_refresh(self, i: discord.Interaction, b: ui.Button):
        emb = generate_dashboard_embed(self.guild_id, self.tourn_id, self.event_title, self.event_ort)
        await i.response.edit_message(embed=emb)

    @ui.button(label="Auto-Generate Cars", style=discord.ButtonStyle.primary, emoji="🤖", row=0)
    async def btn_auto_car(self, i: discord.Interaction, b: ui.Button):
        data_manager.auto_assign_cars(self.guild_id, self.tourn_id)
        emb = generate_dashboard_embed(self.guild_id, self.tourn_id, self.event_title, self.event_ort)
        await i.response.edit_message(embed=emb)
        await i.followup.send(i18n.t(self.guild_id, "orga_cars_generated"), ephemeral=True)

    @ui.button(label="Assign Room", style=discord.ButtonStyle.success, emoji="🛏️", row=1)
    async def btn_assign_room(self, i: discord.Interaction, b: ui.Button):
        v = ui.View()
        v.add_item(UserAssignSelect(self.guild_id, self.tourn_id, self.event_title, self.event_ort))
        await i.response.send_message("Step 1: Select player(s):", view=v, ephemeral=True)

    @ui.button(label="Remove Room", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def btn_remove_room(self, i: discord.Interaction, b: ui.Button):
        v = ui.View()
        v.add_item(UserRemoveSelect(self.guild_id, self.tourn_id, self.event_title))
        await i.response.send_message("Select player(s):", view=v, ephemeral=True)

    @ui.button(label="Assign Car", style=discord.ButtonStyle.success, emoji="🚗", row=2)
    async def btn_assign_car(self, i: discord.Interaction, b: ui.Button):
        v = ui.View()
        v.add_item(UserAssignCarSelect(self.guild_id, self.tourn_id, self.event_title))
        await i.response.send_message("Step 1: Select player(s):", view=v, ephemeral=True)

    @ui.button(label="Remove from Car", style=discord.ButtonStyle.danger, emoji="🚪", row=2)
    async def btn_remove_car(self, i: discord.Interaction, b: ui.Button):
        v = ui.View()
        v.add_item(UserRemoveCarSelect(self.guild_id, self.tourn_id, self.event_title))
        await i.response.send_message("Select player(s):", view=v, ephemeral=True)

    @ui.button(label="Delete Car", style=discord.ButtonStyle.danger, emoji="💥", row=2)
    async def btn_delete_car(self, i: discord.Interaction, b: ui.Button):
        v = ui.View()
        v.add_item(CarDeleteSelect(self.guild_id, self.tourn_id, self.event_title))
        await i.response.send_message("Select car to dissolve:", view=v, ephemeral=True)

class Orgateam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def tournament_autocomplete(self, interaction: discord.Interaction, current: str):
        if not interaction.guild_id:
            return []
        conn = data_manager.get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT custom_id, event_title FROM tournament_events WHERE guild_id=%s", (str(interaction.guild_id),))
        rows = c.fetchall()
        c.close(); conn.close()

        def extract_id(item):
            return [int(p) if p.isdigit() else 0 for p in str(item[0]).split('-')]

        sorted_rows = sorted(rows, key=extract_id, reverse=True)
        choices = []
        for cid, title in sorted_rows:
            clean_t = (title or "").replace('\u200b', '')
            label = f"{clean_t[:80]} ({cid})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=cid))
            if len(choices) >= 25:
                break
        return choices

    @app_commands.command(name="orga_dashboard", description="Opens the hotel & carpool planning dashboard for a tournament")
    @app_commands.describe(tournament_id="Select tournament")
    @app_commands.autocomplete(tournament_id=tournament_autocomplete)
    @app_commands.check(is_authorized_orgateam)
    async def orga_dashboard(self, interaction: discord.Interaction, tournament_id: str):
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        evt = data_manager.get_tournament_event_by_custom_id(interaction.guild_id, tournament_id)
        if not evt:
            await interaction.followup.send("❌ Tournament not found on this server.", ephemeral=True)
            return

        event_title = evt[4]
        emb = generate_dashboard_embed(interaction.guild_id, tournament_id, event_title, "")
        await interaction.followup.send(embed=emb, view=DashboardView(interaction.guild_id, tournament_id, event_title, ""), ephemeral=True)

    @app_commands.command(name="hotel_add", description="Adds a hotel to this server's hotel catalog")
    @app_commands.describe(city="City (e.g. Prague, Munich)", name="Hotel name", link="Booking URL")
    @app_commands.check(is_authorized_orgateam)
    async def hotel_add(self, interaction: discord.Interaction, city: str, name: str, link: str):
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("en", "server_only"), ephemeral=True)
            return
        if data_manager.add_hotel(interaction.guild_id, city, name, link):
            await interaction.response.send_message(f"✅ Hotel **{name}** ({city.capitalize()}) added to server catalog.", ephemeral=True)
        else:
            await interaction.response.send_message(i18n.t(interaction, "db_error"), ephemeral=True)

    @app_commands.command(name="hotel_list", description="Lists all saved hotels for this server")
    @app_commands.check(is_authorized_orgateam)
    async def hotel_list(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            return
        hotels = data_manager.get_hotels(interaction.guild_id)
        if not hotels:
            await interaction.response.send_message("No hotels saved on this server yet (`/hotel_add`).", ephemeral=True)
            return
        desc = "\n".join([f"**ID {h_id}** | {loc.capitalize()}: [{name}]({link})" for h_id, loc, name, link in hotels])
        embed = discord.Embed(title=f"🏨 Hotel Catalog — {interaction.guild.name}", description=desc[:4000], color=discord.Color.teal())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="hotel_remove", description="Deletes a hotel from this server's catalog")
    @app_commands.describe(hotel_id="Hotel ID from /hotel_list")
    @app_commands.check(is_authorized_orgateam)
    async def hotel_remove(self, interaction: discord.Interaction, hotel_id: int):
        if not interaction.guild_id:
            return
        if data_manager.delete_hotel(interaction.guild_id, hotel_id):
            await interaction.response.send_message(f"✅ Hotel ID `{hotel_id}` removed.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Hotel ID not found on this server.", ephemeral=True)

    @orga_dashboard.error
    @hotel_add.error
    @hotel_list.error
    @hotel_remove.error
    async def error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(i18n.t(interaction, "no_permission"), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Orgateam(bot))
