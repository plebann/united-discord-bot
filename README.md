# united-discord-bot

Minimalny bot Discord do typowania wyników meczów Manchesteru United.

## MVP

Bot obsługuje ręczne dodawanie meczów, typowanie wyniku od 3 dni przed kickoffem,
edycję typu do rozpoczęcia meczu oraz ręczne rozliczenie punktów `5/3/1/0`.

Komendy:

- `/typ wynik:<gospodarze>:<goście>`
- `/moj-typ`
- `/admin-mecz-dodaj gospodarze:<nazwa> goscie:<nazwa> rozgrywki:<nazwa> kickoff:<data>`
- `/admin-mecz-edytuj kickoff:<data>`
- `/admin-mecz-wynik wynik:<gospodarze>:<goście>`

Komendy administracyjne wymagają uprawnienia `Manage Guild` albo `Administrator`.
Kickoff należy podawać jako ISO 8601 ze strefą czasową, np.
`2026-09-12T18:30:00+00:00`.

## Uruchomienie

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
# uzupełnij DISCORD_TOKEN
New-Item -ItemType Directory -Force data
py -m alembic upgrade head
python -m united_bot.main
```

Bot używa SQLite w trybie WAL. Automatyczna synchronizacja meczów, oceny
zawodników i rankingi nie są częścią obecnego MVP.

Logi aplikacji i biblioteki Discord są kierowane na standardowe wyjście
terminala. Token Discorda nie jest zapisywany w logach.
