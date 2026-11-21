import discord
import data_manager

SUPPORTED_LANGUAGES = {
    "en": "🇬🇧 English",
    "de": "🇩🇪 Deutsch",
    "cs": "🇨🇿 Čeština",
    "it": "🇮🇹 Italiano"
}

TRANSLATIONS = {
    "en": {
        "no_permission": "⛔ **Access denied!** You do not have permission to use this action.",
        "server_only": "⛔ This command can only be used inside a server.",
        "db_error": "❌ Database error occurred.",
        "ban_global_title": "⛔ **Global Bot Ban!**\nYou have been banned from using {bot_name}.",
        "ban_guild_title": "⛔ **Server Bot Restriction!**\nYou have been restricted from using {bot_name} on this server.",
        "ban_until": "\nExpires on: {time}",
        "ban_perm": "\nDuration: Permanent",
        "ban_reason": "\n**Reason:** {reason}",
        "setup_title": "⚙️ {bot_name} — Server Configuration",
        "setup_desc": "Configure all server-specific roles, channels, voting quorums, and deadlines below.",
        "setup_saved": "✅ Configuration saved successfully!",
        "setup_select_cat": "Choose a configuration section...",
        "setup_opt_lang": "Language / Sprache",
        "setup_opt_roles": "Core Roles (Team, Guest, Observer)",
        "setup_opt_channels": "Channels & Categories",
        "setup_opt_voting": "Voting & Captain Election Rules",
        "setup_opt_deadlines": "Deadlines, Cars & Google Sheet",
        "not_configured": "Not configured",
        "gdpr_export_header": "GDPR DATA EXPORT (Art. 15 GDPR)",
        "gdpr_cooldown": "⏳ You can only request a data export once every 24 hours. Next available: **{time}**.",
        "gdpr_export_done": "✅ Your cross-server personal data export has been generated."
    },
    "de": {
        "no_permission": "⛔ **Keine Berechtigung!** Dir fehlen die nötigen Rechte für diese Aktion.",
        "server_only": "⛔ Dieser Befehl kann nur auf einem Server genutzt werden.",
        "db_error": "❌ Ein Datenbank-Fehler ist aufgetreten.",
        "ban_global_title": "⛔ **Globale Bot-Sperre!**\nDu wurdest global von der Nutzung von {bot_name} ausgeschlossen.",
        "ban_guild_title": "⛔ **Server Bot-Sperre!**\nDu wurdest auf diesem Server von der Nutzung von {bot_name} ausgeschlossen.",
        "ban_until": "\nSperre endet am: {time} Uhr",
        "ban_perm": "\nDauer: Dauerhaft",
        "ban_reason": "\n**Grund:** {reason}",
        "setup_title": "⚙️ {bot_name} — Server-Konfiguration",
        "setup_desc": "Passe hier alle serverspezifischen Rollen, Kanäle, Wahlregeln und Fristen an.",
        "setup_saved": "✅ Einstellungen erfolgreich gespeichert!",
        "setup_select_cat": "Konfigurations-Bereich auswählen...",
        "setup_opt_lang": "Sprache / Language",
        "setup_opt_roles": "Kern-Rollen (Team, Gast, Observer)",
        "setup_opt_channels": "Kanäle & Kategorien",
        "setup_opt_voting": "Wahlregeln (Captainwahl, Aufnahme & Kick)",
        "setup_opt_deadlines": "Fristen, Autos & Google Sheet",
        "not_configured": "Nicht konfiguriert",
        "gdpr_export_header": "DSGVO DATENAUSKUNFT (Art. 15 DSGVO)",
        "gdpr_cooldown": "⏳ Du kannst nur alle 24 Stunden einen Datenexport anfordern. Nächster Abruf möglich ab: **{time}**.",
        "gdpr_export_done": "✅ Deine vollständige, serverübergreifende Datenauskunft wurde erstellt."
    },
    "cs": {
        "no_permission": "⛔ **Přístup odepřen!** Na tuto akci nemáš oprávnění.",
        "server_only": "⛔ Tento příkaz lze použít pouze na serveru.",
        "db_error": "❌ Došlo k chybě databáze.",
        "ban_global_title": "⛔ **Globální blokace bota!**\nByl ti zablokován přístup k botovi {bot_name}.",
        "ban_guild_title": "⛔ **Serverová blokace bota!**\nNa tomto serveru ti byl omezen přístup k botovi {bot_name}.",
        "ban_until": "\nKončí dne: {time}",
        "ban_perm": "\nTrvání: Trvale",
        "ban_reason": "\n**Důvod:** {reason}",
        "setup_title": "⚙️ {bot_name} — Nastavení serveru",
        "setup_desc": "Zde nastavíš serverové role, kanály, pravidla hlasování a uzávěrky.",
        "setup_saved": "✅ Nastavení bylo úspěšně uloženo!",
        "setup_select_cat": "Vyber kategorii nastavení...",
        "setup_opt_lang": "Jazyk / Language",
        "setup_opt_roles": "Hlavní role (Tým, Host, Pozorovatel)",
        "setup_opt_channels": "Kanály a kategorie",
        "setup_opt_voting": "Pravidla hlasování a volby kapitána",
        "setup_opt_deadlines": "Uzávěrky, auta a Google Sheet",
        "not_configured": "Nenastaveno",
        "gdpr_export_header": "EXPORT OSOBNÍCH ÚDAJŮ (Čl. 15 GDPR)",
        "gdpr_cooldown": "⏳ Export dat lze vyžádat pouze jednou za 24 hodin. Další možný termín: **{time}**.",
        "gdpr_export_done": "✅ Tvůj export osobních údajů ze všech serverů byl vygenerován."
    },
    "it": {
        "no_permission": "⛔ **Accesso negato!** Non hai i permessi per eseguire questa azione.",
        "server_only": "⛔ Questo comando può essere usato solo in un server.",
        "db_error": "❌ Si è verificato un errore del database.",
        "ban_global_title": "⛔ **Blocco Globale Bot!**\nSei stato escluso dall'utilizzo di {bot_name}.",
        "ban_guild_title": "⛔ **Blocco Server Bot!**\nSei stato escluso dall'utilizzo di {bot_name} su questo server.",
        "ban_until": "\nScadenza: {time}",
        "ban_perm": "\nDurata: Permanente",
        "ban_reason": "\n**Motivo:** {reason}",
        "setup_title": "⚙️ {bot_name} — Configurazione Server",
        "setup_desc": "Configura ruoli del server, canali, quorum di voto e scadenze qui sotto.",
        "setup_saved": "✅ Configurazione salvata con successo!",
        "setup_select_cat": "Scegli una sezione da configurare...",
        "setup_opt_lang": "Lingua / Language",
        "setup_opt_roles": "Ruoli Principali (Team, Ospite, Osservatore)",
        "setup_opt_channels": "Canali e Categorie",
        "setup_opt_voting": "Regole di Voto ed Elezione Capitano",
        "setup_opt_deadlines": "Scadenze, Auto e Google Sheet",
        "not_configured": "Non configurato",
        "gdpr_export_header": "ESPORTAZIONE DATI GDPR (Art. 15 GDPR)",
        "gdpr_cooldown": "⏳ Puoi richiedere l'esportazione dei dati solo una volta ogni 24 ore. Prossima disponibilità: **{time}**.",
        "gdpr_export_done": "✅ L'esportazione completa dei tuoi dati personali è stata generata."
    }
}

def get_guild_lang(guild_id) -> str:
    """Gibt die eingestellte Sprache eines Servers zurück (Standard: 'en')."""
    if not guild_id:
        return "en"
    lang = data_manager.get_server_settings(guild_id).get("language", "en")
    return lang if lang in SUPPORTED_LANGUAGES else "en"

def get_interaction_lang(interaction: discord.Interaction, prefer_guild: bool = True) -> str:
    """Ermittelt die Sprache für eine Interaktion.
    Bei öffentlichen Nachrichten (prefer_guild=True) zählt die Server-Sprache;
    in DMs oder wenn prefer_guild=False ist, wird vorrangig das Discord-Locale des Users geprüft."""
    if interaction.guild_id and prefer_guild:
        return get_guild_lang(interaction.guild_id)

    loc = str(getattr(interaction, "locale", "en")).lower()
    if loc.startswith("de"): return "de"
    if loc.startswith("cs"): return "cs"
    if loc.startswith("it"): return "it"
    if interaction.guild_id:
        return get_guild_lang(interaction.guild_id)
    return "en"

def t(lang_or_guild, key: str, **kwargs) -> str:
    """Übersetzt einen Key in die gewünschte Sprache (mit Fallback auf Englisch)."""
    if isinstance(lang_or_guild, int) or (isinstance(lang_or_guild, str) and lang_or_guild.isdigit()):
        lang = get_guild_lang(lang_or_guild)
    elif isinstance(lang_or_guild, discord.Interaction):
        lang = get_interaction_lang(lang_or_guild)
    else:
        lang = str(lang_or_guild) if lang_or_guild in SUPPORTED_LANGUAGES else "en"

    template = TRANSLATIONS.get(lang, {}).get(key) or TRANSLATIONS["en"].get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template
