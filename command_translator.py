import discord
from discord import app_commands
from discord.app_commands import TranslationContextLocation, TranslationContextTypes
import re

LOCALE_MAP = {
    discord.Locale.german: "de",
    discord.Locale.czech: "cs",
    discord.Locale.italian: "it",
    discord.Locale.japanese: "ja",
}

# 1. SLASH COMMAND NAMEN (kleingeschrieben, ohne Leerzeichen, max. 32 Zeichen; Unicode inkl. Kanji/Kana erlaubt)
CMD_NAMES = {
    "setup_config":              {"de": "setup_konfig",          "cs": "nastaveni_serveru",     "it": "config_server",       "ja": "サーバー設定"},
    "setup":                     {"de": "setup",                 "cs": "opravneni",             "it": "permessi",            "ja": "権限設定"},
    "setup_list":                {"de": "setup_liste",           "cs": "opravneni_seznam",      "it": "lista_permessi",      "ja": "権限一覧"},
    "dev_ban":                   {"de": "dev_bann",              "cs": "dev_blokace",           "it": "dev_blocco",          "ja": "dev_ban"},
    "dev_gdpr":                  {"de": "dev_dsgvo",             "cs": "dev_gdpr",              "it": "dev_gdpr",            "ja": "dev_gdpr"},
    "captain_election":          {"de": "captainwahl",           "cs": "volba_kapitana",        "it": "elezione_capitano",   "ja": "キャプテン選挙"},
    "admission":                 {"de": "aufnahme",              "cs": "prijeti",               "it": "ammissione",          "ja": "加入投票"},
    "votekick":                  {"de": "votekick",              "cs": "vylouceni",             "it": "espulsione",          "ja": "除名投票"},
    "vote":                      {"de": "umfrage",               "cs": "anketa",                "it": "sondaggio",           "ja": "アンケート"},
    "profile":                   {"de": "profil",                "cs": "profil",                "it": "profilo",             "ja": "プロフィール"},
    "privacy":                   {"de": "datenschutz",           "cs": "soukromi",              "it": "privacy",             "ja": "プライバシー"},
    "legal":                     {"de": "rechtliches",           "cs": "pravni_info",           "it": "note_legali",         "ja": "利用規約"},
    "punish":                    {"de": "sperren",               "cs": "zablokovat",            "it": "blocca",              "ja": "利用制限"},
    "pardon":                    {"de": "entsperren",            "cs": "odblokovat",            "it": "sblocca",             "ja": "制限解除"},
    "send_training_guest_panel": {"de": "gast_panel_senden",     "cs": "panel_pro_hosty",       "it": "pannello_ospiti",     "ja": "ゲスト申請パネル設置"},
    "training":                  {"de": "training",              "cs": "trenink",               "it": "allenamento",         "ja": "トレーニング"},
    "tournament":                {"de": "turnier",               "cs": "turnaj",                "it": "torneo",              "ja": "大会"},
    "tournament_manual":         {"de": "turnier_manuell",       "cs": "turnaj_rucne",          "it": "torneo_manuale",      "ja": "大会手動作成"},
    "tournament_update_old":     {"de": "turniere_aktualisieren","cs": "aktualizovat_turnaje",  "it": "aggiorna_tornei",     "ja": "大会一括更新"},
    "orga_dashboard":            {"de": "orga_dashboard",        "cs": "orga_dashboard",        "it": "orga_dashboard",      "ja": "運営パネル"},
    "hotel_add":                 {"de": "hotel_hinzufuegen",     "cs": "hotel_pridat",          "it": "aggiungi_hotel",      "ja": "ホテル追加"},
    "hotel_list":                {"de": "hotel_liste",           "cs": "hotel_seznam",          "it": "lista_hotel",         "ja": "ホテル一覧"},
    "hotel_remove":              {"de": "hotel_entfernen",       "cs": "hotel_odebrat",         "it": "rimuovi_hotel",       "ja": "ホテル削除"},
    "statistics":                {"de": "statistik",             "cs": "statistiky",            "it": "statistiche",         "ja": "統計"},
    "lf_set":                    {"de": "lf_setzen",             "cs": "lf_nastavit",           "it": "imposta_lf",          "ja": "lfタグ設定"},
    "log":                       {"de": "log",                   "cs": "log",                   "it": "log",                 "ja": "ログ設定"},
    "log_level":                 {"de": "log_level",             "cs": "log_uroven",            "it": "livello_log",         "ja": "ログレベル"},
    "reminder_create":           {"de": "erinnerung_erstellen",  "cs": "pripominka_vytvorit",   "it": "crea_promemoria",     "ja": "リマインダー作成"},
    "reminder_delete":           {"de": "erinnerung_loeschen",   "cs": "pripominka_smazat",     "it": "elimina_promemoria",  "ja": "リマインダー削除"},
    "reminder_edit":             {"de": "erinnerung_bearbeiten", "cs": "pripominka_upravit",    "it": "modifica_promemoria", "ja": "リマインダー編集"},
    "reminder_list":             {"de": "erinnerungen",          "cs": "pripominky",            "it": "lista_promemoria",    "ja": "リマインダー一覧"},
    "help":                      {"de": "hilfe",                 "cs": "napoveda",              "it": "aiuto",               "ja": "ヘルプ"},
}

# 2. RECHTSKLICK KONTEXTMENÜ-NAMEN (max. 32 Zeichen)
CTX_MENU_NAMES = {
    "Import as Tournament": {"de": "Als Turnier importieren", "cs": "Importovat jako turnaj", "it": "Importa come torneo", "ja": "大会としてインポート"},
    "Votekick":             {"de": "Votekick starten",        "cs": "Hlasovat o vyloučení",   "it": "Avvia espulsione",    "ja": "除名投票を開始"},
    "View Profile":         {"de": "Profil ansehen",          "cs": "Zobrazit profil",        "it": "Vedi profilo",        "ja": "プロフィールを表示"},
    "Manage Member":        {"de": "Mitglied verwalten",      "cs": "Spravovat člena",        "it": "Gestisci membro",     "ja": "メンバー管理"},
    "Report Message":       {"de": "Nachricht melden",        "cs": "Nahlásit zprávu",        "it": "Segnala messaggio",   "ja": "メッセージを通報"},
}

# 3. SLASH COMMAND BESCHREIBUNGEN (max. 100 Zeichen)
CMD_DESCRIPTIONS = {
    "setup_config": {
        "de": "Interaktives Dashboard für Sprache, Rollen, Kanäle, Wahlregeln & Fristen",
        "cs": "Interaktivní panel pro jazyk, role, kanály, pravidla hlasování a uzávěrky",
        "it": "Pannello interattivo per lingua, ruoli, canali, regole di voto e scadenze",
        "ja": "言語・ロール・チャンネル・投票ルール・締切を設定する管理パネルを開きます",
    },
    "setup": {
        "de": "Weist Server-Rollen Berechtigungen für bestimmte Befehle zu oder entzieht sie",
        "cs": "Přiřadí nebo odebere oprávnění rolím pro jednotlivé funkce bota",
        "it": "Assegna o revoca i permessi dei comandi per i ruoli del server",
        "ja": "各機能・コマンドの実行権限をサーバーロールに付与または剥奪します",
    },
    "setup_list": {
        "de": "Zeigt die freigegebenen Rollen für eine Befehlskategorie an",
        "cs": "Zobrazí povolené role pro vybranou kategorii příkazů",
        "it": "Mostra i ruoli autorizzati per una specifica categoria di comandi",
        "ja": "指定した機能に対して許可されているロール一覧を表示します",
    },
    "dev_ban": {
        "de": "[Developer] Globale Bot-Sperre per User-ID verwalten",
        "cs": "[Vývojář] Globální blokace/odblokování uživatele podle ID",
        "it": "[Sviluppatore] Gestisci blocco globale del bot tramite ID utente",
        "ja": "[開発者専用] ユーザーIDによるグローバルBot利用制限を管理します",
    },
    "dev_gdpr": {
        "de": "[Developer] Serverübergreifender DSGVO-Export oder Löschung per User-ID",
        "cs": "[Vývojář] GDPR export nebo výmaz dat pro libovolné User ID",
        "it": "[Sviluppatore] Esportazione o cancellazione GDPR tramite ID utente",
        "ja": "[開発者専用] 任意のユーザーIDのGDPRデータ出力・完全削除を実行します",
    },
    "captain_election": {
        "de": "Startet eine anonyme Captain-Wahl nach den Regeln dieses Servers",
        "cs": "Spustí anonymní volbu kapitána podle pravidel serveru",
        "it": "Avvia un'elezione anonima del capitano secondo le regole del server",
        "ja": "サーバースールに基づき匿名のキャプテン選挙を開始します",
    },
    "admission": {
        "de": "Startet eine anonyme Abstimmung über eine Team-Aufnahme",
        "cs": "Spustí anonymní hlasování o přijetí do týmu",
        "it": "Avvia una votazione anonima per l'ammissione nel team",
        "ja": "チームへの新規加入に関する匿名投票を開始します",
    },
    "votekick": {
        "de": "Startet eine anonyme Abstimmung über einen Team-Ausschluss",
        "cs": "Spustí anonymní hlasování o vyloučení z týmu",
        "it": "Avvia una votazione anonima per l'espulsione dal team",
        "ja": "チームからの除名に関する匿名投票を開始します",
    },
    "vote": {
        "de": "Erstellt eine allgemeine Umfrage (öffentlich oder anonym)",
        "cs": "Vytvoří obecnou anketu (veřejnou nebo anonymní)",
        "it": "Crea un sondaggio generale (pubblico o anonimo)",
        "ja": "公開または匿名のアンケートを作成します",
    },
    "profile": {
        "de": "Öffnet dein persönliches Profil, Urlaube, Reise-Wünsche & DSGVO-Optionen",
        "cs": "Otevře tvůj osobní profil, nepřítomnosti, cestovní preference a GDPR",
        "it": "Apre il tuo profilo personale, assenze, preferenze di viaggio e opzioni GDPR",
        "ja": "個人プロフィール、不在予定、遠征希望、GDPRデータ管理を開きます",
    },
    "privacy": {
        "de": "Self-Service für DSGVO-Datenauskunft (Art. 15) und Datenlöschung (Art. 17)",
        "cs": "Samoobslužný GDPR export dat (Čl. 15) a výmaz osobních údajů (Čl. 17)",
        "it": "Self-service per esportazione dati GDPR (Art. 15) e cancellazione (Art. 17)",
        "ja": "個人データの出力（GDPR第15条）および完全削除（第17条）を行います",
    },
    "legal": {
        "de": "Zeigt Nutzungsbedingungen, Datenschutzerklärung & DSGVO-Optionen",
        "cs": "Zobrazí podmínky použití, zásady ochrany soukromí a GDPR nástroje",
        "it": "Mostra Termini di Servizio, Privacy Policy e strumenti GDPR",
        "ja": "利用規約、プライバシーポリシー、およびデータ管理ツールを表示します",
    },
    "punish": {
        "de": "Sperrt ein Mitglied auf diesem Server für die Nutzung des Bots",
        "cs": "Omezí členovi přístup k botovi na tomto serveru",
        "it": "Limita l'utilizzo del bot per un membro su questo server",
        "ja": "このサーバーでの特定メンバーのBot利用を制限します",
    },
    "pardon": {
        "de": "Hebt die Bot-Sperre eines Mitglieds auf diesem Server wieder auf",
        "cs": "Zruší omezení přístupu k botovi pro člena na tomto serveru",
        "it": "Rimuove il blocco del bot per un membro su questo server",
        "ja": "このサーバーでの特定メンバーのBot利用制限を解除します",
    },
    "send_training_guest_panel": {
        "de": "Erstellt das Bewerbungs-Panel für externe Trainingsgäste",
        "cs": "Vytvoří přihlašovací panel pro hostující hráče na trénink",
        "it": "Pubblica il pannello di richiesta per ospiti agli allenamenti",
        "ja": "練習に参加したい外部ゲスト向けの申請ボタンパネルを設置します",
    },
    "training": {
        "de": "Öffnet die Trainings-Zentrale (Erstellen, Bearbeiten, Gäste & Teilnehmer)",
        "cs": "Otevře správu tréninků (vytváření, úpravy, účastníci a hosté)",
        "it": "Apre il pannello di gestione allenamenti, partecipanti e ospiti",
        "ja": "練習の作成・編集・中止および参加者・ゲストの管理パネルを開きます",
    },
    "tournament": {
        "de": "Zentrale Steuerung für Turniere, Liga-Serien und Teilnehmer",
        "cs": "Centrální správa turnajů, ligových sérií a účastníků",
        "it": "Pannello centrale per tornei, campionati a giornate e partecipanti",
        "ja": "大会・リーグ戦の作成・編集および参加者の管理センターを開きます",
    },
    "tournament_manual": {
        "de": "Erstellt ein Turnier direkt per Befehl im aktuellen oder gewählten Kanal",
        "cs": "Vytvoří turnaj přímo příkazem v aktuálním nebo zvoleném kanálu",
        "it": "Crea un torneo direttamente nel canale attuale o specificato",
        "ja": "現在のチャンネルまたは指定チャンネルに直接大会を作成します",
    },
    "tournament_update_old": {
        "de": "Aktualisiert bestehende Turnier-Nachrichten (Dev: global | Admin: eigener Server)",
        "cs": "Aktualizuje zprávy turnajů (Vývojář: globálně | Admin: vlastní server)",
        "it": "Aggiorna i messaggi dei tornei (Dev: globale | Admin: proprio server)",
        "ja": "既存の大会メッセージとボタンを最新状態に一括更新します",
    },
    "orga_dashboard": {
        "de": "Öffnet das Hotel- und Fahrgemeinschafts-Dashboard für ein Turnier",
        "cs": "Otevře plánovací Orga panel (hotely a auta) pro vybraný turnaj",
        "it": "Apre la dashboard Orga (hotel e auto) per un torneo",
        "ja": "大会のホテル部屋割り＆配車計画ダッシュボードを開きます",
    },
    "hotel_add": {
        "de": "Fügt ein Hotel zum Server-Katalog hinzu",
        "cs": "Přidá hotel do katalogu tohoto serveru",
        "it": "Aggiunge un hotel al catalogo di questo server",
        "ja": "サーバーのホテルカタログに新しいホテルを追加します",
    },
    "hotel_list": {
        "de": "Listet alle gespeicherten Hotels dieses Servers auf",
        "cs": "Zobrazí všechny uložené hotely tohoto serveru",
        "it": "Elenca tutti gli hotel salvati per questo server",
        "ja": "このサーバーに登録されているホテル一覧を表示します",
    },
    "hotel_remove": {
        "de": "Löscht ein Hotel anhand der ID aus dem Server-Katalog",
        "cs": "Odstraní hotel z katalogu serveru podle ID",
        "it": "Rimuove un hotel dal catalogo del server tramite ID",
        "ja": "指定したIDのホテルをカタログから削除します",
    },
    "statistics": {
        "de": "Öffnet die Server-Statistiken (Trainings, Turniere, Laserforce-Verzeichnis)",
        "cs": "Otevře statistiky serveru (tréninky, turnaje, adresář Laserforce)",
        "it": "Apre le statistiche del server (allenamenti, tornei, elenco Laserforce)",
        "ja": "練習・大会の参加率統計およびLaserforce名鑑を表示します",
    },
    "lf_set": {
        "de": "Verknüpft ein Mitglied mit seinem iPlayLaserforce-Tag",
        "cs": "Propojí člena serveru s jeho iPlayLaserforce tagem",
        "it": "Collega un membro al suo tag profilo iPlayLaserforce",
        "ja": "メンバーに iPlayLaserforce のプロフィールタグを紐づけます",
    },
    "log": {
        "de": "Legt den Textkanal für Bot- und Befehls-Logs fest",
        "cs": "Nastaví kanál pro logování příkazů a událostí bota",
        "it": "Imposta il canale per i log del bot e dei comandi",
        "ja": "Botの操作ログを出力するテキストチャンネルを設定します",
    },
    "log_level": {
        "de": "Stellt die Detailstufe für den Log-Kanal ein",
        "cs": "Nastaví úroveň podrobností pro logovací kanál",
        "it": "Configura il livello di dettaglio per il canale di log",
        "ja": "ログチャンネルに出力する詳細レベルを設定します",
    },
    "reminder_create": {
        "de": "Erstellt eine persönliche Erinnerung per Direktnachricht",
        "cs": "Vytvoří osobní připomínku do soukromých zpráv",
        "it": "Crea un promemoria personale via messaggio diretto",
        "ja": "指定した日時にDMで通知する個人リマインダーを作成します",
    },
    "reminder_delete": {
        "de": "Löscht eine geplante persönliche Erinnerung",
        "cs": "Smaže naplánovanou osobní připomínku",
        "it": "Elimina un promemoria personale programmato",
        "ja": "登録済みの個人リマインダーを削除します",
    },
    "reminder_edit": {
        "de": "Bearbeitet eine bestehende persönliche Erinnerung",
        "cs": "Upraví existující osobní připomínku",
        "it": "Modifica un promemoria personale esistente",
        "ja": "登録済みの個人リマインダーの内容や日時を編集します",
    },
    "reminder_list": {
        "de": "Zeigt alle deine aktiven Erinnerungen an",
        "cs": "Zobrazí všechny tvé aktivní připomínky",
        "it": "Mostra tutti i tuoi promemoria attivi",
        "ja": "現在有効な個人リマインダーの一覧を表示します",
    },
    "help": {
        "de": "Zeigt eine Übersicht aller Befehle, Funktionen und Berechtigungen",
        "cs": "Zobrazí přehled všech příkazů, funkcí a oprávnění",
        "it": "Mostra una panoramica di tutti i comandi e permessi",
        "ja": "全コマンド・機能・必要な権限のヘルプ一覧を表示します",
    },
}

# 4. PARAMETER-NAMEN (max. 32 Zeichen)
PARAM_NAMES = {
    "feature":          {"de": "funktion",         "cs": "funkce",            "it": "funzione",          "ja": "機能"},
    "action":           {"de": "aktion",           "cs": "akce",              "it": "azione",            "ja": "操作"},
    "roles":            {"de": "rollen",           "cs": "role",              "it": "ruoli",             "ja": "ロール"},
    "user_id":          {"de": "nutzer_id",        "cs": "id_uzivatele",      "it": "id_utente",         "ja": "ユーザーid"},
    "hours":            {"de": "stunden",          "cs": "hodiny",            "it": "ore",               "ja": "時間"},
    "reason":           {"de": "grund",            "cs": "duvod",             "it": "motivo",            "ja": "理由"},
    "title":            {"de": "titel",            "cs": "nazev",             "it": "titolo",            "ja": "タイトル"},
    "deadline_hours":   {"de": "frist_stunden",    "cs": "uzaverka_hodiny",   "it": "scadenza_ore",      "ja": "締切時間"},
    "name":             {"de": "name",             "cs": "jmeno",             "it": "nome",              "ja": "名前"},
    "options":          {"de": "optionen",         "cs": "moznosti",          "it": "opzioni",           "ja": "選択肢"},
    "anonymous":        {"de": "anonym",           "cs": "anonymni",          "it": "anonimo",           "ja": "匿名"},
    "max_choices":      {"de": "max_stimmen",      "cs": "max_hlasu",         "it": "max_scelte",        "ja": "最大選択数"},
    "member":           {"de": "mitglied",         "cs": "clen",              "it": "membro",            "ja": "メンバー"},
    "duration_hours":   {"de": "dauer_stunden",    "cs": "trvani_hodiny",     "it": "durata_ore",        "ja": "制限時間"},
    "trainer_channel":  {"de": "trainer_kanal",    "cs": "kanal_treneru",     "it": "canale_allenatori", "ja": "通知先チャンネル"},
    "panel_language":   {"de": "panel_sprache",    "cs": "jazyk_panelu",      "it": "lingua_pannello",   "ja": "パネル言語"},
    "image":            {"de": "bild",             "cs": "obrazek",           "it": "immagine",          "ja": "画像"},
    "description":      {"de": "beschreibung",     "cs": "popis",             "it": "descrizione",       "ja": "説明"},
    "location":         {"de": "ort",              "cs": "misto",             "it": "luogo",             "ja": "開催地"},
    "channel_name":     {"de": "kanalname",        "cs": "nazev_kanalu",      "it": "nome_canale",       "ja": "チャンネル名"},
    "tournament_id":    {"de": "turnier_id",       "cs": "id_turnaje",        "it": "id_torneo",         "ja": "大会id"},
    "city":             {"de": "stadt",            "cs": "mesto",             "it": "citta",             "ja": "都市"},
    "link":             {"de": "link",             "cs": "odkaz",             "it": "link",              "ja": "リンク"},
    "hotel_id":         {"de": "hotel_id",         "cs": "id_hotelu",         "it": "id_hotel",          "ja": "ホテルid"},
    "tag":              {"de": "tag",              "cs": "tag",               "it": "tag",               "ja": "タグ"},
    "channel":          {"de": "kanal",            "cs": "kanal",             "it": "canale",            "ja": "チャンネル"},
    "level":            {"de": "stufe",            "cs": "uroven",            "it": "livello",           "ja": "レベル"},
    "text":             {"de": "text",             "cs": "text",              "it": "testo",             "ja": "内容"},
    "date":             {"de": "datum",            "cs": "datum",             "it": "data",              "ja": "日付"},
    "time":             {"de": "uhrzeit",          "cs": "cas",               "it": "ora",               "ja": "時刻"},
    "reminder_id":      {"de": "erinnerung_id",    "cs": "id_pripominky",     "it": "id_promemoria",     "ja": "リマインダーid"},
    "new_text":         {"de": "neuer_text",       "cs": "novy_text",         "it": "nuovo_testo",       "ja": "新しい内容"},
    "new_date":         {"de": "neues_datum",      "cs": "nove_datum",        "it": "nuova_data",        "ja": "新しい日付"},
    "new_time":         {"de": "neue_uhrzeit",     "cs": "novy_cas",          "it": "nuova_ora",         "ja": "新しい時刻"},
}

def _sanitize_slug(val: str) -> str:
    """Erlaubt Kleinbuchstaben, Zahlen, '-', '_' sowie Unicode-Schriftzeichen (z. B. Kanji/Kana) gemäß Discord-API."""
    clean = val.lower().strip().replace(" ", "_")
    clean = re.sub(r"[^\w-]", "", clean, flags=re.UNICODE)
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
            return None

        loc = context.location
        orig = string.message

        if loc in (TranslationContextLocation.command_name, TranslationContextLocation.group_name):
            if isinstance(context.data, app_commands.ContextMenu):
                res = CTX_MENU_NAMES.get(orig, {}).get(lang)
                return res[:32] if res else None
            res = CMD_NAMES.get(orig, {}).get(lang)
            return _sanitize_slug(res) if res else None

        if loc in (TranslationContextLocation.command_description, TranslationContextLocation.group_description):
            cmd_name = getattr(context.data, "name", "")
            res = CMD_DESCRIPTIONS.get(cmd_name, {}).get(lang)
            return res[:100] if res else None

        if loc == TranslationContextLocation.parameter_name:
            res = PARAM_NAMES.get(orig, {}).get(lang)
            return _sanitize_slug(res) if res else None

        return None
