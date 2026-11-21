import discord
from discord import app_commands
from discord.app_commands import TranslationContextLocation, TranslationContextTypes
import re

LOCALE_MAP = {
    discord.Locale.german: "de",
    discord.Locale.czech: "cs",
    discord.Locale.italian: "it",
}

# 1. SLASH COMMAND NAMEN (müssen kleingeschrieben & ohne Leerzeichen sein, max. 32 Zeichen)
CMD_NAMES = {
    "setup_config":      {"de": "setup_konfig",          "cs": "nastaveni_serveru",     "it": "config_server"},
    "setup":             {"de": "setup",                 "cs": "opravneni",             "it": "permessi"},
    "setup_list":        {"de": "setup_liste",           "cs": "opravneni_seznam",      "it": "lista_permessi"},
    "dev_ban":           {"de": "dev_bann",              "cs": "dev_blokace",           "it": "dev_blocco"},
    "dev_gdpr":          {"de": "dev_dsgvo",             "cs": "dev_gdpr",              "it": "dev_gdpr"},
    "captain_election":  {"de": "captainwahl",           "cs": "volba_kapitana",        "it": "elezione_capitano"},
    "admission":         {"de": "aufnahme",              "cs": "prijeti",               "it": "ammissione"},
    "votekick":          {"de": "votekick",              "cs": "vylouceni",             "it": "espulsione"},
    "vote":              {"de": "umfrage",               "cs": "anketa",                "it": "sondaggio"},
    "profile":           {"de": "profil",                "cs": "profil",                "it": "profilo"},
    "privacy":           {"de": "datenschutz",           "cs": "soukromi",              "it": "privacy"},
    "legal":             {"de": "rechtliches",           "cs": "pravni_info",           "it": "note_legali"},
    "punish":            {"de": "sperren",               "cs": "zablokovat",            "it": "blocca"},
    "pardon":            {"de": "entsperren",            "cs": "odblokovat",            "it": "sblocca"},
    "send_training_guest_panel": {"de": "gast_panel_senden", "cs": "panel_pro_hosty",   "it": "pannello_ospiti"},
    "training":          {"de": "training",              "cs": "trenink",               "it": "allenamento"},
    "tournament":        {"de": "turnier",               "cs": "turnaj",                "it": "torneo"},
    "tournament_manual": {"de": "turnier_manuell",       "cs": "turnaj_rucne",          "it": "torneo_manuale"},
    "tournament_update_old": {"de": "turniere_aktualisieren", "cs": "aktualizovat_turnaje", "it": "aggiorna_tornei"},
    "orga_dashboard":    {"de": "orga_dashboard",        "cs": "orga_dashboard",        "it": "orga_dashboard"},
    "hotel_add":         {"de": "hotel_hinzufuegen",     "cs": "hotel_pridat",          "it": "aggiungi_hotel"},
    "hotel_list":        {"de": "hotel_liste",           "cs": "hotel_seznam",          "it": "lista_hotel"},
    "hotel_remove":      {"de": "hotel_entfernen",       "cs": "hotel_odebrat",         "it": "rimuovi_hotel"},
    "statistics":        {"de": "statistik",             "cs": "statistiky",            "it": "statistiche"},
    "lf_set":            {"de": "lf_setzen",             "cs": "lf_nastavit",           "it": "imposta_lf"},
    "log":               {"de": "log",                   "cs": "log",                   "it": "log"},
    "log_level":         {"de": "log_level",             "cs": "log_uroven",            "it": "livello_log"},
    "reminder_create":   {"de": "erinnerung_erstellen",  "cs": "pripominka_vytvorit",   "it": "crea_promemoria"},
    "reminder_delete":   {"de": "erinnerung_loeschen",   "cs": "pripominka_smazat",     "it": "elimina_promemoria"},
    "reminder_edit":     {"de": "erinnerung_bearbeiten", "cs": "pripominka_upravit",    "it": "modifica_promemoria"},
    "reminder_list":     {"de": "erinnerungen",          "cs": "pripominky",            "it": "lista_promemoria"},
    "help":              {"de": "hilfe",                 "cs": "napoveda",              "it": "aiuto"},
}

# 2. RECHTSKLICK KONTEXTMENÜ-NAMEN (Dürfen Großbuchstaben & Leerzeichen haben, max. 32 Zeichen)
CTX_MENU_NAMES = {
    "Import as Tournament": {"de": "Als Turnier importieren", "cs": "Importovat jako turnaj", "it": "Importa come torneo"},
    "Votekick":             {"de": "Votekick starten",        "cs": "Hlasovat o vyloučení",   "it": "Avvia espulsione"},
    "View Profile":         {"de": "Profil ansehen",          "cs": "Zobrazit profil",        "it": "Vedi profilo"},
    "Manage Member":        {"de": "Mitglied verwalten",      "cs": "Spravovat člena",        "it": "Gestisci membro"},
    "Report Message":       {"de": "Nachricht melden",        "cs": "Nahlásit zprávu",        "it": "Segnala messaggio"},
}

# 3. SLASH COMMAND BESCHREIBUNGEN (max. 100 Zeichen)
CMD_DESCRIPTIONS = {
    "setup_config": {
        "de": "Interaktives Dashboard für Sprache, Rollen, Kanäle, Wahlregeln & Fristen",
        "cs": "Interaktivní panel pro jazyk, role, kanály, pravidla hlasování a uzávěrky",
        "it": "Pannello interattivo per lingua, ruoli, canali, regole di voto e scadenze",
    },
    "setup": {
        "de": "Weist Server-Rollen Berechtigungen für bestimmte Befehle zu oder entzieht sie",
        "cs": "Přiřadí nebo odebere oprávnění rolím pro jednotlivé funkce bota",
        "it": "Assegna o revoca i permessi dei comandi per i ruoli del server",
    },
    "setup_list": {
        "de": "Zeigt die freigegebenen Rollen für eine Befehlskategorie an",
        "cs": "Zobrazí povolené role pro vybranou kategorii příkazů",
        "it": "Mostra i ruoli autorizzati per una specifica categoria di comandi",
    },
    "dev_ban": {
        "de": "[Developer] Globale Bot-Sperre per User-ID verwalten",
        "cs": "[Vývojář] Globální blokace/odblokování uživatele podle ID",
        "it": "[Sviluppatore] Gestisci blocco globale del bot tramite ID utente",
    },
    "dev_gdpr": {
        "de": "[Developer] Serverübergreifender DSGVO-Export oder Löschung per User-ID",
        "cs": "[Vývojář] GDPR export nebo výmaz dat pro libovolné User ID",
        "it": "[Sviluppatore] Esportazione o cancellazione GDPR tramite ID utente",
    },
    "captain_election": {
        "de": "Startet eine anonyme Captain-Wahl nach den Regeln dieses Servers",
        "cs": "Spustí anonymní volbu kapitána podle pravidel serveru",
        "it": "Avvia un'elezione anonima del capitano secondo le regole del server",
    },
    "admission": {
        "de": "Startet eine anonyme Abstimmung über eine Team-Aufnahme",
        "cs": "Spustí anonymní hlasování o přijetí do týmu",
        "it": "Avvia una votazione anonima per l'ammissione nel team",
    },
    "votekick": {
        "de": "Startet eine anonyme Abstimmung über einen Team-Ausschluss",
        "cs": "Spustí anonymní hlasování o vyloučení z týmu",
        "it": "Avvia una votazione anonima per l'espulsione dal team",
    },
    "vote": {
        "de": "Erstellt eine allgemeine Umfrage (öffentlich oder anonym)",
        "cs": "Vytvoří obecnou anketu (veřejnou nebo anonymní)",
        "it": "Crea un sondaggio generale (pubblico o anonimo)",
    },
    "profile": {
        "de": "Öffnet dein persönliches Profil, Urlaube, Reise-Wünsche & DSGVO-Optionen",
        "cs": "Otevře tvůj osobní profil, nepřítomnosti, cestovní preference a GDPR",
        "it": "Apre il tuo profilo personale, assenze, preferenze di viaggio e opzioni GDPR",
    },
    "privacy": {
        "de": "Self-Service für DSGVO-Datenauskunft (Art. 15) und Datenlöschung (Art. 17)",
        "cs": "Samoobslužný GDPR export dat (Čl. 15) a výmaz osobních údajů (Čl. 17)",
        "it": "Self-service per esportazione dati GDPR (Art. 15) e cancellazione (Art. 17)",
    },
    "legal": {
        "de": "Zeigt Nutzungsbedingungen, Datenschutzerklärung & DSGVO-Optionen",
        "cs": "Zobrazí podmínky použití, zásady ochrany soukromí a GDPR nástroje",
        "it": "Mostra Termini di Servizio, Privacy Policy e strumenti GDPR",
    },
    "punish": {
        "de": "Sperrt ein Mitglied auf diesem Server für die Nutzung des Bots",
        "cs": "Omezí členovi přístup k botovi na tomto serveru",
        "it": "Limita l'utilizzo del bot per un membro su questo server",
    },
    "pardon": {
        "de": "Hebt die Bot-Sperre eines Mitglieds auf diesem Server wieder auf",
        "cs": "Zruší omezení přístupu k botovi pro člena na tomto serveru",
        "it": "Rimuove il blocco del bot per un membro su questo server",
    },
    "send_training_guest_panel": {
        "de": "Erstellt das Bewerbungs-Panel für externe Trainingsgäste",
        "cs": "Vytvoří přihlašovací panel pro hostující hráče na trénink",
        "it": "Pubblica il pannello di richiesta per ospiti agli allenamenti",
    },
    "training": {
        "de": "Öffnet die Trainings-Zentrale (Erstellen, Bearbeiten, Gäste & Teilnehmer)",
        "cs": "Otevře správu tréninků (vytváření, úpravy, účastníci a hosté)",
        "it": "Apre il pannello di gestione allenamenti, partecipanti e ospiti",
    },
    "tournament": {
        "de": "Zentrale Steuerung für Turniere, Liga-Serien und Teilnehmer",
        "cs": "Centrální správa turnajů, ligových sérií a účastníků",
        "it": "Pannello centrale per tornei, campionati a giornate e partecipanti",
    },
    "tournament_manual": {
        "de": "Erstellt ein Turnier direkt per Befehl im aktuellen oder gewählten Kanal",
        "cs": "Vytvoří turnaj přímo příkazem v aktuálním nebo zvoleném kanálu",
        "it": "Crea un torneo direttamente nel canale attuale o specificato",
    },
    "tournament_update_old": {
        "de": "Aktualisiert bestehende Turnier-Nachrichten (Dev: global | Admin: eigener Server)",
        "cs": "Aktualizuje zprávy turnajů (Vývojář: globálně | Admin: vlastní server)",
        "it": "Aggiorna i messaggi dei tornei (Dev: globale | Admin: proprio server)",
    },
    "orga_dashboard": {
        "de": "Öffnet das Hotel- und Fahrgemeinschafts-Dashboard für ein Turnier",
        "cs": "Otevře plánovací Orga panel (hotely a auta) pro vybraný turnaj",
        "it": "Apre la dashboard Orga (hotel e auto) per un torneo",
    },
    "hotel_add": {
        "de": "Fügt ein Hotel zum Server-Katalog hinzu",
        "cs": "Přidá hotel do katalogu tohoto serveru",
        "it": "Aggiunge un hotel al catalogo di questo server",
    },
    "hotel_list": {
        "de": "Listet alle gespeicherten Hotels dieses Servers auf",
        "cs": "Zobrazí všechny uložené hotely tohoto serveru",
        "it": "Elenca tutti gli hotel salvati per questo server",
    },
    "hotel_remove": {
        "de": "Löscht ein Hotel anhand der ID aus dem Server-Katalog",
        "cs": "Odstraní hotel z katalogu serveru podle ID",
        "it": "Rimuove un hotel dal catalogo del server tramite ID",
    },
    "statistics": {
        "de": "Öffnet die Server-Statistiken (Trainings, Turniere, Laserforce-Verzeichnis)",
        "cs": "Otevře statistiky serveru (tréninky, turnaje, adresář Laserforce)",
        "it": "Apre le statistiche del server (allenamenti, tornei, elenco Laserforce)",
    },
    "lf_set": {
        "de": "Verknüpft ein Mitglied mit seinem iPlayLaserforce-Tag",
        "cs": "Propojí člena serveru s jeho iPlayLaserforce tagem",
        "it": "Collega un membro al suo tag profilo iPlayLaserforce",
    },
    "log": {
        "de": "Legt den Textkanal für Bot- und Befehls-Logs fest",
        "cs": "Nastaví kanál pro logování příkazů a událostí bota",
        "it": "Imposta il canale per i log del bot e dei comandi",
    },
    "log_level": {
        "de": "Stellt die Detailstufe für den Log-Kanal ein",
        "cs": "Nastaví úroveň podrobností pro logovací kanál",
        "it": "Configura il livello di dettaglio per il canale di log",
    },
    "reminder_create": {
        "de": "Erstellt eine persönliche Erinnerung per Direktnachricht",
        "cs": "Vytvoří osobní připomínku do soukromých zpráv",
        "it": "Crea un promemoria personale via messaggio diretto",
    },
    "reminder_delete": {
        "de": "Löscht eine geplante persönliche Erinnerung",
        "cs": "Smaže naplánovanou osobní připomínku",
        "it": "Elimina un promemoria personale programmato",
    },
    "reminder_edit": {
        "de": "Bearbeitet eine bestehende persönliche Erinnerung",
        "cs": "Upraví existující osobní připomínku",
        "it": "Modifica un promemoria personale esistente",
    },
    "reminder_list": {
        "de": "Zeigt alle deine aktiven Erinnerungen an",
        "cs": "Zobrazí všechny tvé aktivní připomínky",
        "it": "Mostra tutti i tuoi promemoria attivi",
    },
    "help": {
        "de": "Zeigt eine Übersicht aller Befehle, Funktionen und Berechtigungen",
        "cs": "Zobrazí přehled všech příkazů, funkcí a oprávnění",
        "it": "Mostra una panoramica di tutti i comandi e permessi",
    },
}

# 4. PARAMETER-NAMEN (müssen kleingeschrieben & ohne Leerzeichen sein, max. 32 Zeichen)
PARAM_NAMES = {
    "feature":          {"de": "funktion",         "cs": "funkce",            "it": "funzione"},
    "action":           {"de": "aktion",           "cs": "akce",              "it": "azione"},
    "roles":            {"de": "rollen",           "cs": "role",              "it": "ruoli"},
    "user_id":          {"de": "nutzer_id",        "cs": "id_uzivatele",      "it": "id_utente"},
    "hours":            {"de": "stunden",          "cs": "hodiny",            "it": "ore"},
    "reason":           {"de": "grund",            "cs": "duvod",             "it": "motivo"},
    "title":            {"de": "titel",            "cs": "nazev",             "it": "titolo"},
    "deadline_hours":   {"de": "frist_stunden",    "cs": "uzaverka_hodiny",   "it": "scadenza_ore"},
    "name":             {"de": "name",             "cs": "jmeno",             "it": "nome"},
    "options":          {"de": "optionen",         "cs": "moznosti",          "it": "opzioni"},
    "anonymous":        {"de": "anonym",           "cs": "anonymni",          "it": "anonimo"},
    "max_choices":      {"de": "max_stimmen",      "cs": "max_hlasu",         "it": "max_scelte"},
    "member":           {"de": "mitglied",         "cs": "clen",              "it": "membro"},
    "duration_hours":   {"de": "dauer_stunden",    "cs": "trvani_hodiny",     "it": "durata_ore"},
    "trainer_channel":  {"de": "trainer_kanal",    "cs": "kanal_treneru",     "it": "canale_allenatori"},
    "panel_language":   {"de": "panel_sprache",    "cs": "jazyk_panelu",      "it": "lingua_pannello"},
    "image":            {"de": "bild",             "cs": "obrazek",           "it": "immagine"},
    "description":      {"de": "beschreibung",     "cs": "popis",             "it": "descrizione"},
    "location":         {"de": "ort",              "cs": "misto",             "it": "luogo"},
    "channel_name":     {"de": "kanalname",        "cs": "nazev_kanalu",      "it": "nome_canale"},
    "tournament_id":    {"de": "turnier_id",       "cs": "id_turnaje",        "it": "id_torneo"},
    "city":             {"de": "stadt",            "cs": "mesto",             "it": "citta"},
    "link":             {"de": "link",             "cs": "odkaz",             "it": "link"},
    "hotel_id":         {"de": "hotel_id",         "cs": "id_hotelu",         "it": "id_hotel"},
    "tag":              {"de": "tag",              "cs": "tag",               "it": "tag"},
    "channel":          {"de": "kanal",            "cs": "kanal",             "it": "canale"},
    "level":            {"de": "stufe",            "cs": "uroven",            "it": "livello"},
    "text":             {"de": "text",             "cs": "text",              "it": "testo"},
    "date":             {"de": "datum",            "cs": "datum",             "it": "data"},
    "time":             {"de": "uhrzeit",          "cs": "cas",               "it": "ora"},
    "reminder_id":      {"de": "erinnerung_id",    "cs": "id_pripominky",     "it": "id_promemoria"},
    "new_text":         {"de": "neuer_text",       "cs": "novy_text",         "it": "nuovo_testo"},
    "new_date":         {"de": "neues_datum",      "cs": "nove_datum",        "it": "nuova_data"},
    "new_time":         {"de": "neue_uhrzeit",     "cs": "novy_cas",          "it": "nuova_ora"},
}

def _sanitize_slug(val: str) -> str:
    """Garantiert, dass Slash-Command- & Parameternamen den strengen Discord-Regex-Regeln entsprechen."""
    clean = val.lower().strip().replace(" ", "_")
    clean = re.sub(r"[^a-z0-9_-]", "", clean)
    return clean[:32] or "cmd"

class LaserbotCommandTranslator(app_commands.Translator):
    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: TranslationContextTypes,
    ) -> str | None:
        lang = LOCALE_MAP.get(locale)
        if not lang:
            return None  # Alle anderen Sprachen fallen automatisch auf den englischen Originaltext zurück

        loc = context.location
        orig = string.message

        # 1. Befehlsnamen (Slash Commands vs. Rechtsklick-Kontextmenüs)
        if loc in (TranslationContextLocation.command_name, TranslationContextLocation.group_name):
            if isinstance(context.data, app_commands.ContextMenu):
                res = CTX_MENU_NAMES.get(orig, {}).get(lang)
                return res[:32] if res else None
            res = CMD_NAMES.get(orig, {}).get(lang)
            return _sanitize_slug(res) if res else None

        # 2. Befehlsbeschreibungen
        if loc in (TranslationContextLocation.command_description, TranslationContextLocation.group_description):
            cmd_name = getattr(context.data, "name", "")
            res = CMD_DESCRIPTIONS.get(cmd_name, {}).get(lang)
            return res[:100] if res else None

        # 3. Parameter-Namen
        if loc == TranslationContextLocation.parameter_name:
            res = PARAM_NAMES.get(orig, {}).get(lang)
            return _sanitize_slug(res) if res else None

        return None
