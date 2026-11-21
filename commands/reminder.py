import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime
import data_manager
import i18n

class Reminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.check_reminders.start()

    async def cog_unload(self):
        self.check_reminders.cancel()

    @tasks.loop(seconds=60)
    async def check_reminders(self):
        due_list = data_manager.get_due_reminders()
        for r_id, user_id, text in due_list:
            try:
                user = await self.bot.fetch_user(int(user_id))
                embed = discord.Embed(
                    title=i18n.t("en", "rem_dm_title"),
                    description=text,
                    color=discord.Color.gold()
                )
                embed.set_footer(text=i18n.t("en", "rem_dm_footer", bot_name=data_manager.BOT_NAME))
                await user.send(embed=embed)
            except discord.Forbidden:
                pass
            except Exception as e:
                print(f"Reminder error {r_id}: {e}")
            finally:
                data_manager.delete_reminder(r_id)

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()

    async def reminder_autocomplete(self, interaction: discord.Interaction, current: str):
        my_reminders = data_manager.get_reminders_by_user(interaction.user.id)
        choices = []
        for r_id, text, time in my_reminders:
            short_text = (text[:30] + '..') if len(text) > 30 else text
            label = f"{short_text} ({time.strftime('%d.%m. %H:%M')})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=str(r_id)))
        return choices[:25]

    @app_commands.command(name="reminder_create", description="Creates a personal DM reminder")
    @app_commands.describe(text="What should I remind you about?", datum="Date (DD.MM.YYYY)", uhrzeit="Time (HH:MM)")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def reminder_create(self, interaction: discord.Interaction, text: str, datum: str, uhrzeit: str):
        lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        try:
            reminder_time = datetime.strptime(f"{datum.strip()} {uhrzeit.strip()}", "%d.%m.%Y %H:%M")
        except ValueError:
            await interaction.response.send_message(i18n.t(lang, "rem_err_fmt"), ephemeral=True)
            return

        if reminder_time < datetime.now():
            await interaction.response.send_message(i18n.t(lang, "rem_err_past"), ephemeral=True)
            return

        if data_manager.add_reminder(interaction.user.id, text, reminder_time):
            await interaction.response.send_message(i18n.t(lang, "rem_saved", time=reminder_time.strftime('%d.%m.%Y %H:%M')), ephemeral=True)
        else:
            await interaction.response.send_message(i18n.t(lang, "db_error"), ephemeral=True)

    @app_commands.command(name="reminder_delete", description="Deletes a scheduled personal reminder")
    @app_commands.autocomplete(reminder_id=reminder_autocomplete)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def reminder_delete(self, interaction: discord.Interaction, reminder_id: str):
        lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        my_reminders = data_manager.get_reminders_by_user(interaction.user.id)
        try:
            r_id = int(reminder_id)
        except ValueError:
            await interaction.response.send_message("❌ Invalid ID.", ephemeral=True)
            return

        if not any(r[0] == r_id for r in my_reminders):
            await interaction.response.send_message("❌ Reminder not found.", ephemeral=True)
            return

        data_manager.delete_reminder(r_id)
        await interaction.response.send_message(i18n.t(lang, "rem_deleted"), ephemeral=True)

    @app_commands.command(name="reminder_edit", description="Edits an existing personal reminder")
    @app_commands.autocomplete(reminder_id=reminder_autocomplete)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def reminder_edit(self, interaction: discord.Interaction, reminder_id: str, neuer_text: str = None, neues_datum: str = None, neue_uhrzeit: str = None):
        lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        try:
            r_id = int(reminder_id)
        except ValueError:
            await interaction.response.send_message("❌ Invalid ID.", ephemeral=True)
            return

        my_reminders = data_manager.get_reminders_by_user(interaction.user.id)
        target = next((r for r in my_reminders if r[0] == r_id), None)
        if not target:
            await interaction.response.send_message("❌ Reminder not found.", ephemeral=True)
            return

        final_text = neuer_text if neuer_text else target[1]
        current_dt = target[2]
        final_dt = current_dt

        if neues_datum or neue_uhrzeit:
            d_str = neues_datum.strip() if neues_datum else current_dt.strftime("%d.%m.%Y")
            t_str = neue_uhrzeit.strip() if neue_uhrzeit else current_dt.strftime("%H:%M")
            try:
                final_dt = datetime.strptime(f"{d_str} {t_str}", "%d.%m.%Y %H:%M")
            except ValueError:
                await interaction.response.send_message(i18n.t(lang, "rem_err_fmt"), ephemeral=True)
                return

        if data_manager.update_reminder(r_id, final_text, final_dt):
            await interaction.response.send_message(i18n.t(lang, "rem_saved", time=final_dt.strftime('%d.%m.%Y %H:%M')), ephemeral=True)
        else:
            await interaction.response.send_message(i18n.t(lang, "db_error"), ephemeral=True)

    @app_commands.command(name="reminder_list", description="Lists all your active personal reminders")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def reminder_list(self, interaction: discord.Interaction):
        lang = i18n.get_interaction_lang(interaction, prefer_guild=False)
        my_reminders = data_manager.get_reminders_by_user(interaction.user.id)
        if not my_reminders:
            await interaction.response.send_message(i18n.t(lang, "rem_empty"), ephemeral=True)
            return

        embed = discord.Embed(title=i18n.t(lang, "rem_list_title"), color=discord.Color.gold())
        desc = ""
        for r_id, text, time_obj in my_reminders:
            short_text = (text[:60] + '..') if len(text) > 60 else text
            desc += f"`ID {r_id}` | **{time_obj.strftime('%d.%m.%Y %H:%M')}**\n📝 {short_text}\n\n"
        embed.description = desc[:4000]
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Reminder(bot))
