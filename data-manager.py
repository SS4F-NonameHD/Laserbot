import mysql.connector
import os
import hashlib
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

BOT_NAME = os.getenv('BOT_NAME', 'Laserbot')

# Developer IDs (ehemals SUPER_USER_IDS)
_env_devs = os.getenv('DEVELOPER_IDS', '')
if _env_devs.strip():
    DEVELOPER_IDS = [int(x.strip()) for x in _env_devs.split(',') if x.strip().isdigit()]
else:
    DEVELOPER_IDS = [322457841149411328, 734721876726775830, 491648861501259777]

DEFAULT_SERVER_SETTINGS = {
    "language": "en",
    "team_role_id": None,
    "observer_role_id": None,
    "guest_role_id": None,
    "guest_default_days": 14,
    "training_channel_id": None,
    "tournament_category_id": None,
    "report_channel_id": None,
    "captain_max_for": 3,
    "captain_max_against": 1,
    "captain_default_hours": 48,
    "aufnahme_majority": 66.67,
    "votekick_majority": 66.67,
    "decision_quorum": 0.0,
    "decision_default_hours": 48,
    "training_deadline_hours": 30.5,
    "training_reminder_hours": 2.0,
    "tournament_deadline_hours": 48,
    "default_car_seats": 4,
    "google_sheet_url": None
}

def get_main_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        port=int(os.getenv('DB_PORT', 3306)),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        connection_timeout=5
    )

def get_vote_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_VOTE_HOST', os.getenv('DB_HOST', '127.0.0.1')),
        port=int(os.getenv('DB_VOTE_PORT', 3306)),
        database=os.getenv('DB_VOTE_NAME', os.getenv('DB_NAME')),
        user=os.getenv('DB_VOTE_USER', os.getenv('DB_USER')),
        password=os.getenv('DB_VOTE_PASSWORD', os.getenv('DB_PASSWORD')),
        connection_timeout=5
    )

def init_db():
    try:
        conn = get_main_db_connection()
        c = conn.cursor()

        # 1. Zentrale Server-Konfiguration (Multi-Tenancy)
        c.execute("""
            CREATE TABLE IF NOT EXISTS server_settings (
                guild_id VARCHAR(50) PRIMARY KEY,
                language VARCHAR(10) DEFAULT 'en',
                team_role_id VARCHAR(50) DEFAULT NULL,
                observer_role_id VARCHAR(50) DEFAULT NULL,
                guest_role_id VARCHAR(50) DEFAULT NULL,
                guest_default_days INT DEFAULT 14,
                training_channel_id VARCHAR(50) DEFAULT NULL,
                tournament_category_id VARCHAR(50) DEFAULT NULL,
                report_channel_id VARCHAR(50) DEFAULT NULL,
                captain_max_for INT DEFAULT 3,
                captain_max_against INT DEFAULT 1,
                captain_default_hours INT DEFAULT 48,
                aufnahme_majority DOUBLE DEFAULT 66.67,
                votekick_majority DOUBLE DEFAULT 66.67,
                decision_quorum DOUBLE DEFAULT 0.0,
                decision_default_hours INT DEFAULT 48,
                training_deadline_hours DOUBLE DEFAULT 30.5,
                training_reminder_hours DOUBLE DEFAULT 2.0,
                tournament_deadline_hours INT DEFAULT 48,
                default_car_seats INT DEFAULT 4,
                google_sheet_url VARCHAR(500) DEFAULT NULL
            )
        """)

        # 2. Events & Teilnahmen (strikt nach guild_id + custom_id getrennt)
        c.execute("""
            CREATE TABLE IF NOT EXISTS tournament_events (
                guild_id VARCHAR(50),
                custom_id VARCHAR(50),
                event_title VARCHAR(255),
                channel_id VARCHAR(50),
                message_id VARCHAR(50),
                reminder_sent BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (guild_id, custom_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                guild_id VARCHAR(50),
                custom_id VARCHAR(50),
                user_id VARCHAR(255),
                user_name VARCHAR(255),
                display_name VARCHAR(255),
                event_title VARCHAR(255),
                status VARCHAR(50),
                team_name VARCHAR(255) DEFAULT NULL,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_manual BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (guild_id, custom_id, user_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS training_events (
                guild_id VARCHAR(50),
                custom_id VARCHAR(50),
                training_id VARCHAR(255),
                channel_id VARCHAR(50),
                message_id VARCHAR(50),
                reminder_sent BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (guild_id, custom_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS trainings (
                guild_id VARCHAR(50),
                custom_id VARCHAR(50),
                user_id VARCHAR(255),
                user_name VARCHAR(255),
                display_name VARCHAR(255),
                training_id VARCHAR(255),
                status VARCHAR(50),
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_manual BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (guild_id, custom_id, user_id)
            )
        """)

        # 3. Notizen
        c.execute("""
            CREATE TABLE IF NOT EXISTS tournament_notes (
                guild_id VARCHAR(50),
                custom_id VARCHAR(50),
                user_id VARCHAR(255),
                note VARCHAR(100),
                PRIMARY KEY (guild_id, custom_id, user_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS training_notes (
                guild_id VARCHAR(50),
                custom_id VARCHAR(50),
                user_id VARCHAR(255),
                note VARCHAR(100),
                PRIMARY KEY (guild_id, custom_id, user_id)
            )
        """)

        # 4. Profile & Abwesenheiten (Captain-Status pro Server, Reisedaten/Urlaub global pro User)
        c.execute("""
            CREATE TABLE IF NOT EXISTS member_guild_profiles (
                guild_id VARCHAR(50),
                user_id VARCHAR(255),
                captain_eligible BOOLEAN DEFAULT TRUE,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_travel_profiles (
                user_id VARCHAR(255) PRIMARY KEY,
                has_license BOOLEAN DEFAULT FALSE,
                room_pref VARCHAR(20) DEFAULT 'shared',
                partner_id VARCHAR(255) DEFAULT NULL,
                default_passengers VARCHAR(255) DEFAULT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_absences (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(255),
                start_date DATETIME,
                end_date DATETIME,
                reason VARCHAR(100)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS laserforce_tags (
                user_id VARCHAR(255) PRIMARY KEY,
                lf_tag VARCHAR(50)
            )
        """)

        # 5. Reiselogistik & Hotels (strikt nach guild_id getrennt)
        c.execute("""
            CREATE TABLE IF NOT EXISTS hotels (
                id INT AUTO_INCREMENT PRIMARY KEY,
                guild_id VARCHAR(50),
                location VARCHAR(255),
                name VARCHAR(255),
                link VARCHAR(500)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS tournament_travel_responses (
                guild_id VARCHAR(50),
                custom_id VARCHAR(50),
                user_id VARCHAR(255),
                needs_hotel BOOLEAN,
                alt_accommodation VARCHAR(50),
                has_car BOOLEAN,
                arrival_day VARCHAR(50),
                departure_day VARCHAR(50),
                PRIMARY KEY (guild_id, custom_id, user_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS travel_assignments (
                guild_id VARCHAR(50),
                custom_id VARCHAR(50),
                user_id VARCHAR(255),
                hotel_id INT DEFAULT NULL,
                room_name VARCHAR(50) DEFAULT NULL,
                carpool_id VARCHAR(50) DEFAULT NULL,
                is_driver BOOLEAN DEFAULT FALSE,
                carpool_ret_id VARCHAR(50) DEFAULT NULL,
                is_driver_ret BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (guild_id, custom_id, user_id)
            )
        """)

        # 6. Rechte, Logs, Gäste, Polls, Reminders & Sperren
        c.execute("""
            CREATE TABLE IF NOT EXISTS command_permissions (
                guild_id VARCHAR(50),
                command_name VARCHAR(50),
                role_id VARCHAR(50),
                PRIMARY KEY (guild_id, command_name, role_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS server_log_settings (
                guild_id VARCHAR(50) PRIMARY KEY,
                channel_id VARCHAR(50),
                log_level VARCHAR(20) NOT NULL DEFAULT 'none'
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS active_guests (
                guild_id VARCHAR(50),
                user_id VARCHAR(50),
                expires_at DATETIME,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS guest_panels (
                guild_id VARCHAR(50) PRIMARY KEY,
                channel_id VARCHAR(50)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS guild_blacklist (
                guild_id VARCHAR(50),
                user_id VARCHAR(255),
                unban_time DATETIME NULL,
                reason VARCHAR(255),
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS global_blacklist (
                user_id VARCHAR(255) PRIMARY KEY,
                unban_time DATETIME NULL,
                reason VARCHAR(255)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(255),
                reminder_text TEXT,
                reminder_time DATETIME
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS general_polls (
                poll_id VARCHAR(20) PRIMARY KEY,
                guild_id VARCHAR(50),
                title VARCHAR(255),
                is_anonymous BOOLEAN,
                max_votes INT,
                author_id VARCHAR(255),
                channel_id VARCHAR(255),
                message_id VARCHAR(255),
                is_closed BOOLEAN DEFAULT FALSE
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS general_votes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                poll_id VARCHAR(20),
                voter_id VARCHAR(255),
                user_name VARCHAR(255),
                choice VARCHAR(255),
                UNIQUE KEY unique_user_choice (poll_id, voter_id, choice)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS dsgvo_export_log (
                user_id VARCHAR(255) PRIMARY KEY,
                last_export DATETIME
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS guild_maintenance_log (
                guild_id VARCHAR(50),
                action_name VARCHAR(50),
                last_run DATETIME,
                PRIMARY KEY (guild_id, action_name)
            )
        """)

        conn.commit()
        c.close()
        conn.close()
        print("Main DB initialized (Multi-Tenant ready).")

        # Vote DB (Anonyme Wahlen)
        try:
            conn_v = get_vote_db_connection()
            c_v = conn_v.cursor()
            c_v.execute("""
                CREATE TABLE IF NOT EXISTS captain_votes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(50),
                    election_id VARCHAR(20),
                    voter_id VARCHAR(255),
                    candidate VARCHAR(255),
                    vote_type VARCHAR(10)
                )
            """)
            c_v.execute("""
                CREATE TABLE IF NOT EXISTS majority_votes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(50),
                    poll_id VARCHAR(20),
                    voter_hash VARCHAR(255),
                    vote VARCHAR(10),
                    UNIQUE KEY unique_poll_vote (poll_id, voter_hash)
                )
            """)
            conn_v.commit()
            c_v.close()
            conn_v.close()
            print("Vote DB initialized.")
        except Exception as e:
            print(f"Vote DB Error: {e}")

    except Exception as e:
        print(f"Main DB Init Error: {e}")

init_db()

# =====================================================================
# SERVER SETTINGS & MULTI-TENANCY HELPERS
# =====================================================================

def get_server_settings(guild_id) -> dict:
    res = DEFAULT_SERVER_SETTINGS.copy()
    if not guild_id:
        return res
    try:
        conn = get_main_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute("SELECT * FROM server_settings WHERE guild_id=%s", (str(guild_id),))
        row = c.fetchone()
        c.close()
        conn.close()
        if row:
            for k in res.keys():
                if k in row and row[k] is not None:
                    res[k] = row[k]
    except Exception as e:
        print(f"Error loading server_settings: {e}")
    return res

def update_server_settings(guild_id, **kwargs) -> bool:
    if not guild_id or not kwargs:
        return False
    valid_keys = set(DEFAULT_SERVER_SETTINGS.keys())
    updates = {k: v for k, v in kwargs.items() if k in valid_keys}
    if not updates:
        return False
    try:
        conn = get_main_db_connection()
        c = conn.cursor()
        c.execute("INSERT IGNORE INTO server_settings (guild_id) VALUES (%s)", (str(guild_id),))
        set_clause = ", ".join([f"{k}=%s" for k in updates.keys()])
        vals = list(updates.values()) + [str(guild_id)]
        c.execute(f"UPDATE server_settings SET {set_clause} WHERE guild_id=%s", tuple(vals))
        conn.commit()
        c.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating server_settings: {e}")
        return False

def is_member_observer(member) -> bool:
    """Prüft anhand der Server-Konfiguration, ob ein Mitglied die Observer-Rolle trägt."""
    if not member or not hasattr(member, "guild") or not hasattr(member, "roles"):
        return False
    settings = get_server_settings(member.guild.id)
    obs_role_id = settings.get("observer_role_id")
    if not obs_role_id:
        return False
    return any(str(r.id) == str(obs_role_id) for r in member.roles)

def is_member_team(member) -> bool:
    """Prüft, ob ein Mitglied die konfigurierte Haupt-Teamrolle des Servers besitzt."""
    if not member or not hasattr(member, "guild") or not hasattr(member, "roles"):
        return False
    settings = get_server_settings(member.guild.id)
    team_role_id = settings.get("team_role_id")
    if not team_role_id:
        return False
    return any(str(r.id) == str(team_role_id) for r in member.roles)

# Kompatibilitäts-Wrapper für Gäste-Rolle (nutzt nun direkt server_settings)
def set_guest_settings(guild_id, role_id=None, default_days=None):
    updates = {}
    if role_id == "CLEAR":
        updates["guest_role_id"] = None
    elif role_id is not None:
        updates["guest_role_id"] = str(role_id)
    if default_days is not None:
        updates["guest_default_days"] = int(default_days)
    return update_server_settings(guild_id, **updates)

def get_guest_settings(guild_id):
    s = get_server_settings(guild_id)
    return s.get("guest_role_id"), s.get("guest_default_days", 14)

# =====================================================================
# BERECHTIGUNGEN & LOGGING
# =====================================================================

def add_command_permission(guild_id, command_name, role_id):
    try:
        conn = get_main_db_connection(); cu = conn.cursor()
        cu.execute("INSERT IGNORE INTO command_permissions (guild_id, command_name, role_id) VALUES (%s,%s,%s)",
                   (str(guild_id), command_name, str(role_id)))
        conn.commit(); cu.close(); conn.close(); return True
    except: return False

def remove_command_permission(guild_id, command_name, role_id):
    try:
        conn = get_main_db_connection(); cu = conn.cursor()
        cu.execute("DELETE FROM command_permissions WHERE guild_id=%s AND command_name=%s AND role_id=%s",
                   (str(guild_id), command_name, str(role_id)))
        conn.commit(); cu.close(); conn.close(); return True
    except: return False

def get_allowed_roles(guild_id, command_name):
    try:
        conn = get_main_db_connection(); cu = conn.cursor()
        cu.execute("SELECT role_id FROM command_permissions WHERE guild_id=%s AND command_name=%s",
                   (str(guild_id), command_name))
        r = cu.fetchall(); cu.close(); conn.close()
        return [x[0] for x in r]
    except: return []

def set_log_settings(guild_id, channel_id, level):
    try:
        conn = get_main_db_connection(); cu = conn.cursor()
        cu.execute("""
            INSERT INTO server_log_settings (guild_id, channel_id, log_level) VALUES (%s,%s,%s)
            ON DUPLICATE KEY UPDATE channel_id=%s, log_level=%s
        """, (str(guild_id), str(channel_id), level, str(channel_id), level))
        conn.commit(); cu.close(); conn.close(); return True
    except: return False

def get_log_settings(guild_id):
    try:
        conn = get_main_db_connection(); cu = conn.cursor()
        cu.execute("SELECT channel_id, log_level FROM server_log_settings WHERE guild_id=%s", (str(guild_id),))
        r = cu.fetchone(); cu.close(); conn.close(); return r
    except: return None

# =====================================================================
# EVENT-IDs, TURNIERE & TRAININGS (STRIKT MIT GUILD_ID)
# =====================================================================

def get_next_event_id(guild_id, year, event_type):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        target_table = "tournament_events" if event_type == "tournaments" else "training_events"
        c.execute(f"SELECT DISTINCT custom_id FROM {target_table} WHERE guild_id = %s AND custom_id LIKE %s",
                  (str(guild_id), f"{year}-%"))
        rows = c.fetchall(); c.close(); conn.close()
        nums = []
        for r in rows:
            parts = str(r[0]).split('-')
            if len(parts) == 2:
                try: nums.append(int(parts[1]))
                except: pass
        next_num = max(nums) + 1 if nums else 1
        return f"{year}-{next_num:03d}"
    except Exception as e:
        print(f"ID Error: {e}")
        return f"{year}-001"

def get_next_sub_id(guild_id, base_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT custom_id FROM tournament_events WHERE guild_id = %s AND custom_id LIKE %s",
                  (str(guild_id), f"{base_id}-%"))
        rows = c.fetchall(); c.close(); conn.close()
        nums = []
        for r in rows:
            parts = str(r[0]).split('-')
            if len(parts) > 2:
                try: nums.append(int(parts[-1]))
                except: pass
        next_num = max(nums) + 1 if nums else 1
        return f"{base_id}-{next_num}"
    except:
        return f"{base_id}-1"

def get_event_id_by_message(message_id, guild_id=None):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        if guild_id:
            c.execute("SELECT custom_id FROM tournament_events WHERE guild_id=%s AND message_id=%s",
                      (str(guild_id), str(message_id)))
        else:
            c.execute("SELECT custom_id FROM tournament_events WHERE message_id=%s", (str(message_id),))
        r = c.fetchone(); c.close(); conn.close()
        return r[0] if r else None
    except: return None

def _set_status_main(table, id_field, guild_id, custom_id, user_id, user_name, display_name, title, status, is_manual):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        query = f"""
            INSERT INTO {table} (guild_id, custom_id, user_id, user_name, display_name, {id_field}, status, last_updated, is_manual)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
            ON DUPLICATE KEY UPDATE status=%s, display_name=%s, user_name=%s, {id_field}=%s, last_updated=NOW(), is_manual=%s
        """
        c.execute(query, (
            str(guild_id), str(custom_id), str(user_id), user_name, display_name, title, status, is_manual,
            status, display_name, user_name, title, is_manual
        ))
        conn.commit(); c.close(); conn.close()
    except Exception as e:
        print(f"Set Status Error: {e}")

def set_tournament_status(guild_id, custom_id, user_id, user_name, display_name, title, status, manual=False):
    _set_status_main("tournaments", "event_title", guild_id, custom_id, user_id, user_name, display_name, title, status, manual)

def set_training_status(guild_id, custom_id, user_id, user_name, display_name, title, status, manual=False):
    _set_status_main("trainings", "training_id", guild_id, custom_id, user_id, user_name, display_name, title, status, manual)

def get_tournament_participants(guild_id, custom_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("""
            SELECT display_name, status, last_updated, is_manual, team_name, user_id
            FROM tournaments
            WHERE guild_id = %s AND custom_id = %s
            ORDER BY last_updated ASC
        """, (str(guild_id), str(custom_id)))
        rows = c.fetchall(); c.close(); conn.close()
        res = {}
        for r in rows:
            res[r[0]] = {'status': r[1], 'time': r[2], 'manual': bool(r[3]), 'team': r[4] if r[4] else None, 'user_id': r[5]}
        return res
    except: return {}

def get_training_participants(guild_id, custom_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("""
            SELECT display_name, status, last_updated, is_manual, user_id
            FROM trainings
            WHERE guild_id = %s AND custom_id = %s
            ORDER BY last_updated ASC
        """, (str(guild_id), str(custom_id)))
        rows = c.fetchall(); c.close(); conn.close()
        res = {}
        for r in rows:
            res[r[0]] = {'status': r[1], 'time': r[2], 'manual': bool(r[3]), 'team': None, 'user_id': r[4]}
        return res
    except: return {}

def set_team_members(guild_id, custom_id, team_name, members_list, event_title):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        query = """
            INSERT INTO tournaments (guild_id, custom_id, user_id, user_name, display_name, event_title, status, team_name, last_updated, is_manual)
            VALUES (%s, %s, %s, %s, %s, %s, 'Zusagen', %s, NOW(), TRUE)
            ON DUPLICATE KEY UPDATE status='Zusagen', team_name=%s, display_name=%s, last_updated=NOW(), is_manual=TRUE
        """
        for uid, uname, dname in members_list:
            c.execute(query, (str(guild_id), str(custom_id), str(uid), uname, dname, event_title, team_name, team_name, dname))
        conn.commit(); c.close(); conn.close()
        return True
    except: return False

def delete_team(guild_id, custom_id, team_name):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("UPDATE tournaments SET team_name = NULL WHERE guild_id = %s AND custom_id = %s AND team_name = %s",
                  (str(guild_id), str(custom_id), team_name))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def remove_team_member(guild_id, custom_id, user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("UPDATE tournaments SET team_name = NULL WHERE guild_id = %s AND custom_id = %s AND user_id = %s",
                  (str(guild_id), str(custom_id), str(user_id)))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def delete_tournament_entry(guild_id, custom_id, user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM tournaments WHERE guild_id = %s AND custom_id = %s AND user_id = %s",
                  (str(guild_id), str(custom_id), str(user_id)))
        c.execute("DELETE FROM tournament_travel_responses WHERE guild_id = %s AND custom_id = %s AND user_id = %s",
                  (str(guild_id), str(custom_id), str(user_id)))
        c.execute("DELETE FROM travel_assignments WHERE guild_id = %s AND custom_id = %s AND user_id = %s",
                  (str(guild_id), str(custom_id), str(user_id)))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def get_existing_teams(guild_id, custom_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT DISTINCT team_name FROM tournaments WHERE guild_id = %s AND custom_id = %s AND team_name IS NOT NULL",
                  (str(guild_id), str(custom_id)))
        r = c.fetchall(); c.close(); conn.close(); return [x[0] for x in r]
    except: return []

def get_team_members_data(guild_id, custom_id, team_name):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT user_id, display_name FROM tournaments WHERE guild_id = %s AND custom_id = %s AND team_name = %s",
                  (str(guild_id), str(custom_id), team_name))
        r = c.fetchall(); c.close(); conn.close(); return r
    except: return []

def save_training_event(tid, cid, gid, chid, mid):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("""
            INSERT INTO training_events (guild_id, custom_id, training_id, channel_id, message_id, reminder_sent)
            VALUES (%s,%s,%s,%s,%s,0)
            ON DUPLICATE KEY UPDATE training_id=%s, channel_id=%s, message_id=%s
        """, (str(gid), str(cid), tid, str(chid), str(mid), tid, str(chid), str(mid)))
        conn.commit(); c.close(); conn.close()
    except Exception as e: print(f"Save Training Event Error: {e}")

def save_tournament_event(ttl, cid, gid, chid, mid):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("""
            INSERT INTO tournament_events (guild_id, custom_id, event_title, channel_id, message_id)
            VALUES (%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE event_title=%s, channel_id=%s, message_id=%s
        """, (str(gid), str(cid), ttl, str(chid), str(mid), ttl, str(chid), str(mid)))
        conn.commit(); c.close(); conn.close()
    except Exception as e: print(f"Save Tourn Event Error: {e}")

def get_training_event_by_custom_id(gid, cid):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT channel_id, message_id, custom_id, guild_id, training_id FROM training_events WHERE guild_id=%s AND custom_id=%s",
                  (str(gid), str(cid)))
        r = c.fetchone(); c.close(); conn.close(); return r
    except: return None

def get_tournament_event_by_custom_id(gid, cid):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT channel_id, message_id, custom_id, guild_id, event_title FROM tournament_events WHERE guild_id=%s AND custom_id=%s",
                  (str(gid), str(cid)))
        r = c.fetchone(); c.close(); conn.close(); return r
    except: return None

def get_all_training_events():
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT guild_id, custom_id, training_id, channel_id, message_id, reminder_sent FROM training_events WHERE reminder_sent = 0")
        r = c.fetchall(); c.close(); conn.close(); return r
    except: return []

def mark_training_reminder_sent(guild_id, custom_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("UPDATE training_events SET reminder_sent=1 WHERE guild_id=%s AND custom_id=%s",
                  (str(guild_id), str(custom_id)))
        conn.commit(); c.close(); conn.close()
    except: pass

def get_active_trainings(guild_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT training_id, custom_id FROM training_events WHERE guild_id=%s", (str(guild_id),))
        r = c.fetchall(); c.close(); conn.close(); return r
    except: return []

def delete_training_entry(guild_id, custom_id, user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM trainings WHERE guild_id = %s AND custom_id = %s AND user_id = %s",
                  (str(guild_id), str(custom_id), str(user_id)))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

# =====================================================================
# FREITEXT NOTIZEN
# =====================================================================

def set_tournament_note(guild_id, custom_id, user_id, note):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("REPLACE INTO tournament_notes (guild_id, custom_id, user_id, note) VALUES (%s, %s, %s, %s)",
                  (str(guild_id), str(custom_id), str(user_id), str(note)))
        conn.commit(); c.close(); conn.close()
    except Exception as e: print(e)

def get_tournament_notes(guild_id, custom_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT user_id, note FROM tournament_notes WHERE guild_id=%s AND custom_id=%s",
                  (str(guild_id), str(custom_id)))
        rows = c.fetchall(); c.close(); conn.close()
        return {str(row[0]): str(row[1]) for row in rows}
    except: return {}

def delete_tournament_note(guild_id, custom_id, user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM tournament_notes WHERE guild_id=%s AND custom_id=%s AND user_id=%s",
                  (str(guild_id), str(custom_id), str(user_id)))
        conn.commit(); c.close(); conn.close()
    except: pass

def set_training_note(guild_id, custom_id, user_id, note):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("REPLACE INTO training_notes (guild_id, custom_id, user_id, note) VALUES (%s, %s, %s, %s)",
                  (str(guild_id), str(custom_id), str(user_id), str(note)))
        conn.commit(); c.close(); conn.close()
    except Exception as e: print(e)

def get_training_notes(guild_id, custom_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT user_id, note FROM training_notes WHERE guild_id=%s AND custom_id=%s",
                  (str(guild_id), str(custom_id)))
        rows = c.fetchall(); c.close(); conn.close()
        return {str(row[0]): str(row[1]) for row in rows}
    except: return {}

def delete_training_note(guild_id, custom_id, user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM training_notes WHERE guild_id=%s AND custom_id=%s AND user_id=%s",
                  (str(guild_id), str(custom_id), str(user_id)))
        conn.commit(); c.close(); conn.close()
    except: pass

# =====================================================================
# ANONYME WAHLEN & ABSTIMMUNGEN (100 % HASHED - KEIN KLARTEXT)
# =====================================================================

def _anonymize_voter(voter_id, context_id):
    salt = os.getenv('SECURITY_SALT', 'default_change_me_salt')
    return hashlib.sha256(f"{voter_id}-{context_id}-{salt}".encode()).hexdigest()

def get_user_captain_votes(guild_id, election_id, voter_id):
    v_hash = _anonymize_voter(voter_id, f"{guild_id}-{election_id}")
    try:
        conn = get_vote_db_connection(); c = conn.cursor()
        c.execute("SELECT candidate, vote_type FROM captain_votes WHERE guild_id=%s AND election_id=%s AND voter_id=%s",
                  (str(guild_id), str(election_id), v_hash))
        r = c.fetchall(); c.close(); conn.close()
        res = {'for': [], 'against': []}
        for ca, vt in r:
            if vt == 'FOR': res['for'].append(ca)
            elif vt == 'AGAINST': res['against'].append(ca)
        return res
    except: return None

def save_votes(guild_id, election_id, voter_id, for_candidates, against_candidates):
    v_hash = _anonymize_voter(voter_id, f"{guild_id}-{election_id}")
    if isinstance(against_candidates, str):
        against_list = [against_candidates]
    elif against_candidates:
        against_list = list(against_candidates)
    else:
        against_list = []
    try:
        conn = get_vote_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM captain_votes WHERE guild_id=%s AND election_id=%s AND voter_id=%s",
                  (str(guild_id), str(election_id), v_hash))
        for x in for_candidates:
            c.execute("INSERT INTO captain_votes (guild_id, election_id, voter_id, candidate, vote_type) VALUES (%s,%s,%s,%s,'FOR')",
                      (str(guild_id), str(election_id), v_hash, x))
        for x in against_list:
            c.execute("INSERT INTO captain_votes (guild_id, election_id, voter_id, candidate, vote_type) VALUES (%s,%s,%s,%s,'AGAINST')",
                      (str(guild_id), str(election_id), v_hash, x))
        conn.commit(); c.close(); conn.close(); return True
    except Exception as e:
        print(f"Vote Save Error: {e}")
        return False

def get_election_results(guild_id, election_id):
    try:
        conn = get_vote_db_connection(); c = conn.cursor()
        c.execute("SELECT candidate, vote_type, voter_id FROM captain_votes WHERE guild_id=%s AND election_id=%s",
                  (str(guild_id), str(election_id)))
        r = c.fetchall(); c.close(); conn.close()
        return r
    except: return []

def save_majority_vote(guild_id, poll_id, voter_id, vote_val):
    v_hash = _anonymize_voter(voter_id, f"{guild_id}-{poll_id}")
    try:
        conn = get_vote_db_connection(); c = conn.cursor()
        c.execute("""
            INSERT INTO majority_votes (guild_id, poll_id, voter_hash, vote)
            VALUES (%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE vote=%s
        """, (str(guild_id), str(poll_id), v_hash, vote_val, vote_val))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def get_my_vote(guild_id, poll_id, voter_id):
    v_hash = _anonymize_voter(voter_id, f"{guild_id}-{poll_id}")
    try:
        conn = get_vote_db_connection(); c = conn.cursor()
        c.execute("SELECT vote FROM majority_votes WHERE guild_id=%s AND poll_id=%s AND voter_hash=%s",
                  (str(guild_id), str(poll_id), v_hash))
        r = c.fetchone(); c.close(); conn.close(); return r[0] if r else None
    except: return None

def get_full_majority_poll_data(guild_id, poll_id):
    try:
        conn = get_vote_db_connection(); c = conn.cursor()
        c.execute("SELECT vote, voter_hash FROM majority_votes WHERE guild_id=%s AND poll_id=%s",
                  (str(guild_id), str(poll_id)))
        r = c.fetchall(); c.close(); conn.close(); return r
    except: return []

# Allgemeine Umfragen (/vote)
def create_general_poll(guild_id, pid, tit, anon, mv, aid, cid, mid):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("""
            INSERT INTO general_polls (poll_id, guild_id, title, is_anonymous, max_votes, author_id, channel_id, message_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (pid, str(guild_id), tit, anon, mv, str(aid), str(cid), str(mid)))
        conn.commit(); c.close(); conn.close()
    except: pass

def get_general_poll_meta(pid):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT title, is_anonymous, max_votes, is_closed FROM general_polls WHERE poll_id=%s", (pid,))
        r = c.fetchone(); c.close(); conn.close(); return r
    except: return None

def save_general_vote(pid, ruid, uname, clist, anon):
    if anon:
        vid = _anonymize_voter(ruid, pid)
        nm = "Anonymous"
    else:
        vid = str(ruid)
        nm = uname
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM general_votes WHERE poll_id=%s AND voter_id=%s", (pid, vid))
        if clist:
            d = [(pid, vid, nm, x) for x in clist]
            c.executemany("INSERT INTO general_votes (poll_id, voter_id, user_name, choice) VALUES (%s,%s,%s,%s)", d)
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def get_general_poll_votes(pid):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT choice, user_name FROM general_votes WHERE poll_id=%s", (pid,))
        r = c.fetchall(); c.close(); conn.close(); return r
    except: return []

# =====================================================================
# SPIELER-PROFIL, URLAUBE, REMINDERS & STATISTIKEN
# =====================================================================

def get_captain_status(guild_id, user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT captain_eligible FROM member_guild_profiles WHERE guild_id=%s AND user_id=%s",
                  (str(guild_id), str(user_id)))
        r = c.fetchone(); c.close(); conn.close()
        return bool(r[0]) if r else True
    except: return True

def toggle_captain_status(guild_id, user_id):
    current = get_captain_status(guild_id, user_id)
    new_status = not current
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("""
            INSERT INTO member_guild_profiles (guild_id, user_id, captain_eligible) VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE captain_eligible=%s
        """, (str(guild_id), str(user_id), new_status, new_status))
        conn.commit(); c.close(); conn.close()
        return new_status
    except: return current

def add_absence(user_id, start_date, end_date, reason):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("INSERT INTO user_absences (user_id, start_date, end_date, reason) VALUES (%s, %s, %s, %s)",
                  (str(user_id), start_date, end_date, reason))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def get_user_absences(user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT id, start_date, end_date, reason FROM user_absences WHERE user_id=%s ORDER BY start_date ASC",
                  (str(user_id),))
        r = c.fetchall(); c.close(); conn.close(); return r
    except: return []

def delete_absence(absence_id, user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM user_absences WHERE id=%s AND user_id=%s", (absence_id, str(user_id)))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def get_absences_for_date(event_date):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT user_id, reason FROM user_absences WHERE start_date <= %s AND end_date >= %s",
                  (event_date, event_date))
        r = c.fetchall(); c.close(); conn.close(); return r
    except: return []

def add_reminder(uid, txt, tm):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("INSERT INTO reminders (user_id, reminder_text, reminder_time) VALUES (%s,%s,%s)", (str(uid), txt, tm))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def get_due_reminders():
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT id, user_id, reminder_text FROM reminders WHERE reminder_time <= NOW()")
        r = c.fetchall(); c.close(); conn.close(); return r
    except: return []

def delete_reminder(rid):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM reminders WHERE id=%s", (rid,))
        conn.commit(); c.close(); conn.close()
    except: pass

def update_reminder(rid, txt, tm):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("UPDATE reminders SET reminder_text=%s, reminder_time=%s WHERE id=%s", (txt, tm, rid))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def get_reminders_by_user(uid):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT id, reminder_text, reminder_time FROM reminders WHERE user_id=%s ORDER BY reminder_time ASC", (str(uid),))
        r = c.fetchall(); c.close(); conn.close(); return r
    except: return []

def set_lf_tag(user_id, tag):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("INSERT INTO laserforce_tags (user_id, lf_tag) VALUES (%s, %s) ON DUPLICATE KEY UPDATE lf_tag=%s",
                  (str(user_id), tag, tag))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def get_all_lf_tags():
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT user_id, lf_tag FROM laserforce_tags")
        r = c.fetchall(); c.close(); conn.close()
        return {row[0]: row[1] for row in r}
    except: return {}

def get_training_stats_full(guild_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT training_id, custom_id FROM training_events WHERE guild_id=%s", (str(guild_id),))
        events = c.fetchall()
        c.execute("SELECT custom_id, user_id, status, is_manual, display_name FROM trainings WHERE guild_id=%s", (str(guild_id),))
        entries = c.fetchall()
        c.close(); conn.close()
        return events, entries
    except: return [], []

def get_tournament_stats(guild_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT custom_id FROM tournament_events WHERE guild_id=%s", (str(guild_id),))
        events = c.fetchall()
        c.execute("SELECT custom_id, user_id FROM tournaments WHERE guild_id=%s AND status='Zusagen'", (str(guild_id),))
        zusagen = c.fetchall()
        c.close(); conn.close()
        return events, zusagen
    except: return [], []

# =====================================================================
# REISEPLANUNG, HOTELS & FAHRGEMEINSCHAFTEN (MIT GUILD_ID)
# =====================================================================

def get_travel_profile(user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT has_license, room_pref, partner_id, default_passengers FROM user_travel_profiles WHERE user_id=%s",
                  (str(user_id),))
        r = c.fetchone(); c.close(); conn.close()
        if r:
            return {"has_license": bool(r[0]), "room_pref": r[1], "partner_id": r[2], "default_passengers": r[3]}
    except: pass
    return {"has_license": False, "room_pref": "shared", "partner_id": None, "default_passengers": None}

def update_travel_profile(user_id, has_license=None, room_pref=None, partner_id=None, default_passengers=None):
    current = get_travel_profile(user_id)
    new_lic = has_license if has_license is not None else current["has_license"]
    new_pref = room_pref if room_pref is not None else current["room_pref"]
    new_part = None if partner_id == "CLEAR" else (partner_id if partner_id is not None else current.get("partner_id"))
    new_pass = None if default_passengers == "CLEAR" else (default_passengers if default_passengers is not None else current.get("default_passengers"))

    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("""
            INSERT INTO user_travel_profiles (user_id, has_license, room_pref, partner_id, default_passengers)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE has_license=%s, room_pref=%s, partner_id=%s, default_passengers=%s
        """, (str(user_id), new_lic, new_pref, new_part, new_pass, new_lic, new_pref, new_part, new_pass))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def save_travel_response(guild_id, custom_id, user_id, needs_hotel, alt_accommodation, has_car, arrival, departure):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("""
            INSERT INTO tournament_travel_responses
            (guild_id, custom_id, user_id, needs_hotel, alt_accommodation, has_car, arrival_day, departure_day)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE needs_hotel=%s, alt_accommodation=%s, has_car=%s, arrival_day=%s, departure_day=%s
        """, (str(guild_id), str(custom_id), str(user_id), needs_hotel, alt_accommodation, has_car, arrival, departure,
              needs_hotel, alt_accommodation, has_car, arrival, departure))
        conn.commit(); c.close(); conn.close(); return True
    except Exception as e:
        print(f"Error saving travel response: {e}")
        return False

def get_travel_response(guild_id, custom_id, user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("""
            SELECT needs_hotel, alt_accommodation, has_car, arrival_day, departure_day
            FROM tournament_travel_responses
            WHERE guild_id=%s AND custom_id=%s AND user_id=%s
        """, (str(guild_id), str(custom_id), str(user_id)))
        r = c.fetchone(); c.close(); conn.close()
        if r:
            return {"needs_hotel": bool(r[0]), "alt_accommodation": r[1], "has_car": bool(r[2]), "arrival": r[3], "departure": r[4]}
    except: pass
    return None

def add_hotel(guild_id, location, name, link):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("INSERT INTO hotels (guild_id, location, name, link) VALUES (%s, %s, %s, %s)",
                  (str(guild_id), location.lower().strip(), name.strip(), link.strip()))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def get_hotels(guild_id, location=None):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        if location:
            c.execute("SELECT id, location, name, link FROM hotels WHERE guild_id=%s AND location=%s",
                      (str(guild_id), location.lower().strip()))
        else:
            c.execute("SELECT id, location, name, link FROM hotels WHERE guild_id=%s ORDER BY location",
                      (str(guild_id),))
        r = c.fetchall(); c.close(); conn.close(); return r
    except: return []

def delete_hotel(guild_id, hotel_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM hotels WHERE guild_id=%s AND id=%s", (str(guild_id), int(hotel_id)))
        deleted = c.rowcount > 0
        conn.commit(); c.close(); conn.close()
        return deleted
    except: return False

def get_travel_planning_data(guild_id, custom_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        query = """
            SELECT t.user_id, t.display_name, tr.needs_hotel, tr.alt_accommodation, tr.has_car,
                   tr.arrival_day, tr.departure_day, p.has_license, p.room_pref, p.partner_id,
                   p.default_passengers, a.hotel_id, a.room_name, a.carpool_id, a.is_driver,
                   a.carpool_ret_id, a.is_driver_ret
            FROM tournaments t
            LEFT JOIN tournament_travel_responses tr
                ON t.guild_id = tr.guild_id AND t.custom_id = tr.custom_id AND t.user_id = tr.user_id
            LEFT JOIN user_travel_profiles p
                ON t.user_id = p.user_id
            LEFT JOIN travel_assignments a
                ON t.guild_id = a.guild_id AND t.custom_id = a.custom_id AND t.user_id = a.user_id
            WHERE t.guild_id = %s AND t.custom_id = %s AND t.status = 'Zusagen'
        """
        c.execute(query, (str(guild_id), str(custom_id)))
        r = c.fetchall(); c.close(); conn.close(); return r
    except Exception as e:
        print(f"Error getting planning data: {e}")
        return []

def assign_hotel_room(guild_id, custom_id, user_id, hotel_id, room_name):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("""
            INSERT INTO travel_assignments (guild_id, custom_id, user_id, hotel_id, room_name)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE hotel_id=%s, room_name=%s
        """, (str(guild_id), str(custom_id), str(user_id), hotel_id, room_name, hotel_id, room_name))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def remove_hotel_room(guild_id, custom_id, user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("UPDATE travel_assignments SET hotel_id=NULL, room_name=NULL WHERE guild_id=%s AND custom_id=%s AND user_id=%s",
                  (str(guild_id), str(custom_id), str(user_id)))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def assign_carpool(guild_id, custom_id, user_id, car_name, is_driver, direction="both"):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        if direction in ["both", "out"]:
            c.execute("""
                INSERT INTO travel_assignments (guild_id, custom_id, user_id, carpool_id, is_driver)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE carpool_id=%s, is_driver=%s
            """, (str(guild_id), str(custom_id), str(user_id), car_name, is_driver, car_name, is_driver))
        if direction in ["both", "ret"]:
            c.execute("""
                INSERT INTO travel_assignments (guild_id, custom_id, user_id, carpool_ret_id, is_driver_ret)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE carpool_ret_id=%s, is_driver_ret=%s
            """, (str(guild_id), str(custom_id), str(user_id), car_name, is_driver, car_name, is_driver))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def remove_carpool(guild_id, custom_id, user_id, direction="both"):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        if direction == "both":
            c.execute("""
                UPDATE travel_assignments
                SET carpool_id=NULL, is_driver=FALSE, carpool_ret_id=NULL, is_driver_ret=FALSE
                WHERE guild_id=%s AND custom_id=%s AND user_id=%s
            """, (str(guild_id), str(custom_id), str(user_id)))
        elif direction == "out":
            c.execute("UPDATE travel_assignments SET carpool_id=NULL, is_driver=FALSE WHERE guild_id=%s AND custom_id=%s AND user_id=%s",
                      (str(guild_id), str(custom_id), str(user_id)))
        elif direction == "ret":
            c.execute("UPDATE travel_assignments SET carpool_ret_id=NULL, is_driver_ret=FALSE WHERE guild_id=%s AND custom_id=%s AND user_id=%s",
                      (str(guild_id), str(custom_id), str(user_id)))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def delete_carpool(guild_id, custom_id, car_name, direction="both"):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        if direction in ["both", "out"]:
            c.execute("UPDATE travel_assignments SET carpool_id=NULL, is_driver=FALSE WHERE guild_id=%s AND custom_id=%s AND carpool_id=%s",
                      (str(guild_id), str(custom_id), car_name))
        if direction in ["both", "ret"]:
            c.execute("UPDATE travel_assignments SET carpool_ret_id=NULL, is_driver_ret=FALSE WHERE guild_id=%s AND custom_id=%s AND carpool_ret_id=%s",
                      (str(guild_id), str(custom_id), car_name))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def auto_assign_cars(guild_id, custom_id):
    try:
        settings = get_server_settings(guild_id)
        max_seats = max(2, int(settings.get("default_car_seats", 4)))
        data = get_travel_planning_data(guild_id, custom_id)

        driver_cars = {}
        car_counter = 1

        for r in data:
            if r[4]:
                if r[13]: driver_cars[r[0]] = r[13]
                elif r[15]: driver_cars[r[0]] = r[15]

        def distribute(direction_key, col_idx, day_idx):
            nonlocal car_counter
            groups = {}
            for r in data:
                if r[col_idx]: continue
                day_val = r[day_idx].strip().lower() if r[day_idx] else "unknown"
                acc_base = f"hotel_{r[11]}" if r[11] else f"alt_{str(r[3]).strip().lower()}"
                key = f"{acc_base}_{direction_key}_{day_val}"
                if key not in groups: groups[key] = {'drivers': [], 'passengers': []}
                if r[4]: groups[key]['drivers'].append(r)
                else: groups[key]['passengers'].append(r)

            for _, group in groups.items():
                drivers = group['drivers']
                passengers = group['passengers']
                if not drivers: continue

                available_cars = []
                car_capacities = {}

                for d in drivers:
                    uid = d[0]
                    if uid not in driver_cars:
                        driver_cars[uid] = f"Auto {car_counter}"
                        car_counter += 1
                    cname = driver_cars[uid]
                    assign_carpool(guild_id, custom_id, uid, cname, True, direction_key)
                    available_cars.append(cname)
                    car_capacities[cname] = 1

                    def_pass_str = d[10]
                    if def_pass_str:
                        def_pass_list = [x.strip() for x in def_pass_str.split(',')]
                        rem_passengers = []
                        for p in passengers:
                            if p[0] in def_pass_list and car_capacities[cname] < max_seats:
                                assign_carpool(guild_id, custom_id, p[0], cname, bool(p[7]), direction_key)
                                car_capacities[cname] += 1
                            else:
                                rem_passengers.append(p)
                        passengers = rem_passengers

                for p in list(passengers):
                    available_cars = [c for c in available_cars if car_capacities[c] < max_seats]
                    if not available_cars: break
                    cname = available_cars[0]
                    assign_carpool(guild_id, custom_id, p[0], cname, bool(p[7]), direction_key)
                    car_capacities[cname] += 1
                    if car_capacities[cname] >= max_seats:
                        available_cars.pop(0)
                    else:
                        available_cars.append(available_cars.pop(0))

        distribute("out", 13, 5)
        distribute("ret", 15, 6)
        return True
    except Exception as e:
        print(f"Auto-assign error: {e}")
        return False

# =====================================================================
# GÄSTE-ABLAUFSYSTEM
# =====================================================================

def add_active_guest(guild_id, user_id, expires_at):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("REPLACE INTO active_guests (guild_id, user_id, expires_at) VALUES (%s, %s, %s)",
                  (str(guild_id), str(user_id), expires_at))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def remove_active_guest(guild_id, user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM active_guests WHERE guild_id=%s AND user_id=%s", (str(guild_id), str(user_id)))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def get_expired_guests():
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT guild_id, user_id, expires_at FROM active_guests WHERE expires_at <= NOW()")
        r = c.fetchall(); c.close(); conn.close(); return r
    except: return []

def get_guest_expiry(guild_id, user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT expires_at FROM active_guests WHERE guild_id=%s AND user_id=%s", (str(guild_id), str(user_id)))
        r = c.fetchone(); c.close(); conn.close()
        return r[0] if r else None
    except: return None

# =====================================================================
# BLACKLIST SYSTEM (LOKAL PRO SERVER + GLOBAL FÜR DEVELOPER)
# =====================================================================

def blacklist_guild_user(guild_id, user_id, unban_time=None, reason="No reason provided"):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("REPLACE INTO guild_blacklist (guild_id, user_id, unban_time, reason) VALUES (%s, %s, %s, %s)",
                  (str(guild_id), str(user_id), unban_time, reason))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def unblacklist_guild_user(guild_id, user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM guild_blacklist WHERE guild_id=%s AND user_id=%s", (str(guild_id), str(user_id)))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def get_guild_blacklist_status(guild_id, user_id):
    if not guild_id:
        return {"is_blacklisted": False}
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT unban_time, reason FROM guild_blacklist WHERE guild_id=%s AND user_id=%s",
                  (str(guild_id), str(user_id)))
        r = c.fetchone(); c.close(); conn.close()
        if r:
            return {"is_blacklisted": True, "unban_time": r[0], "reason": r[1]}
    except: pass
    return {"is_blacklisted": False}

def blacklist_global_user(user_id, unban_time=None, reason="No reason provided"):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("REPLACE INTO global_blacklist (user_id, unban_time, reason) VALUES (%s, %s, %s)",
                  (str(user_id), unban_time, reason))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def unblacklist_global_user(user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM global_blacklist WHERE user_id=%s", (str(user_id),))
        conn.commit(); c.close(); conn.close(); return True
    except: return False

def get_global_blacklist_status(user_id):
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT unban_time, reason FROM global_blacklist WHERE user_id=%s", (str(user_id),))
        r = c.fetchone(); c.close(); conn.close()
        if r:
            return {"is_blacklisted": True, "unban_time": r[0], "reason": r[1]}
    except: pass
    return {"is_blacklisted": False}

# =====================================================================
# DSGVO / GDPR SELF-SERVICE (SERVERÜBERGREIFEND ART. 15 & ART. 17)
# =====================================================================

def check_and_record_dsgvo_export(user_id, cooldown_hours=72) -> tuple[bool, datetime | None]:
    """Prüft das Rate-Limit für Self-Service-Exporte (Standard: 1x pro 72h)."""
    uid = str(user_id)
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT last_export FROM dsgvo_export_log WHERE user_id=%s", (uid,))
        r = c.fetchone()
        now = datetime.now()
        if r and r[0]:
            next_allowed = r[0] + timedelta(hours=cooldown_hours)
            if now < next_allowed:
                c.close(); conn.close()
                return False, next_allowed
        c.execute("REPLACE INTO dsgvo_export_log (user_id, last_export) VALUES (%s, %s)", (uid, now))
        conn.commit(); c.close(); conn.close()
        return True, None
    except:
        return True, None

def check_and_record_guild_cooldown(guild_id, action_name: str, cooldown_hours=72) -> tuple[bool, datetime | None]:
    """Prüft das 72h-Rate-Limit für rechenintensive Admin-Aktionen pro Server."""
    gid = str(guild_id)
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        c.execute("SELECT last_run FROM guild_maintenance_log WHERE guild_id=%s AND action_name=%s", (gid, action_name))
        r = c.fetchone()
        now = datetime.now()
        if r and r[0]:
            next_allowed = r[0] + timedelta(hours=cooldown_hours)
            if now < next_allowed:
                c.close(); conn.close()
                return False, next_allowed
        c.execute("REPLACE INTO guild_maintenance_log (guild_id, action_name, last_run) VALUES (%s, %s, %s)", (gid, action_name, now))
        conn.commit(); c.close(); conn.close()
        return True, None
    except:
        return True, None

def get_dsgvo_data(user_id) -> dict:
    data = {}
    uid = str(user_id)

    def fetch_table(c, table, id_column="user_id"):
        try:
            c.execute(f"SELECT * FROM {table} WHERE {id_column}=%s", (uid,))
            rows = c.fetchall()
            if not rows: return []
            cols = [desc[0] for desc in c.description]
            return [dict(zip(cols, row)) for row in rows]
        except:
            return []

    try:
        conn = get_main_db_connection(); c = conn.cursor()
        data['member_guild_profiles'] = fetch_table(c, 'member_guild_profiles')
        data['laserforce_tags'] = fetch_table(c, 'laserforce_tags')
        data['user_travel_profiles'] = fetch_table(c, 'user_travel_profiles')
        data['user_absences'] = fetch_table(c, 'user_absences')
        data['guild_blacklist'] = fetch_table(c, 'guild_blacklist')
        data['global_blacklist'] = fetch_table(c, 'global_blacklist')
        data['active_guests'] = fetch_table(c, 'active_guests')
        data['reminders'] = fetch_table(c, 'reminders')
        data['tournaments'] = fetch_table(c, 'tournaments')
        data['tournament_travel_responses'] = fetch_table(c, 'tournament_travel_responses')
        data['travel_assignments'] = fetch_table(c, 'travel_assignments')
        data['tournament_notes'] = fetch_table(c, 'tournament_notes')
        data['trainings'] = fetch_table(c, 'trainings')
        data['training_notes'] = fetch_table(c, 'training_notes')
        data['general_votes_public'] = fetch_table(c, 'general_votes', 'voter_id')
        c.close(); conn.close()
    except Exception as e:
        print(f"GDPR Export Error: {e}")

    return data

def delete_all_user_data(user_id) -> bool:
    """Löscht auf Wunsch des Nutzers (Art. 17 DSGVO) alle personenbezogenen Daten serverübergreifend.
    Aktive Sperren (Blacklist) bleiben aus berechtigtem Interesse zum Missbrauchsschutz unberührt."""
    uid = str(user_id)
    tables = [
        ('member_guild_profiles', 'user_id'),
        ('laserforce_tags', 'user_id'),
        ('user_travel_profiles', 'user_id'),
        ('user_absences', 'user_id'),
        ('active_guests', 'user_id'),
        ('reminders', 'user_id'),
        ('tournaments', 'user_id'),
        ('tournament_travel_responses', 'user_id'),
        ('travel_assignments', 'user_id'),
        ('tournament_notes', 'user_id'),
        ('trainings', 'user_id'),
        ('training_notes', 'user_id'),
        ('general_votes', 'voter_id'),
        ('dsgvo_export_log', 'user_id')
    ]
    try:
        conn = get_main_db_connection(); c = conn.cursor()
        for tbl, col in tables:
            try:
                c.execute(f"DELETE FROM {tbl} WHERE {col}=%s", (uid,))
            except:
                pass
        # Partner-Referenzen bei anderen Spielern bereinigen
        try:
            c.execute("UPDATE user_travel_profiles SET partner_id=NULL WHERE partner_id=%s", (uid,))
        except:
            pass
        conn.commit(); c.close(); conn.close()
        return True
    except Exception as e:
        print(f"GDPR Delete Error: {e}")
        return False
