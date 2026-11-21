# Laserbot — Multi-Server Lasertag & Tournament Management Bot

A multi-tenant, multilingual (`EN`, `DE`, `CS`, `IT`) Discord bot built with Python (`discord.py`) and MySQL/MariaDB for Lasertag teams.

## Key Features
- **Multi-Server Customization (`/setup_config`):** Every server configures its own language, team/guest/observer roles, channels, election point limits, admission/votekick majority percentages, turnout quorums, deadlines, car seats, and optional Google Sheet link.
- **Tournaments & Smart Travel Logistics (`/tournament`, `/orga_dashboard`):** Single-day, multi-day, and league series management, message-to-tournament importer, server-isolated hotel catalogs, room assignments, and smart outbound/return carpool generation.
- **Training & Guest System (`/training`, `/send_training_guest_panel`):** Automated deadlines and reminders, upcoming 14-day tournament preview, and time-limited guest role workflows.
- **Cryptographically Anonymous Voting (`/captain_election`, `/admission`, `/votekick`, `/vote`):** SHA-256 salted secret ballots with customizable rules per server.
- **Built-in GDPR Self-Service (`/privacy`, `/profile`):** Instant cross-server data export (Art. 15 GDPR) and one-click erasure (Art. 17 GDPR), usable both in servers and via DMs.

## Quick Start
**First command on your server:** An Admin should start with `/setup_config` to select the desired language, the standard team member role, standard channel for upcoming trainings – all dynamic rules will follow.
