# united-discord-bot

Minimalny bot Discord do typowania wyników meczów Manchesteru United.

## MVP

Bot obsługuje ręczne dodawanie meczów, typowanie wyniku od 3 dni przed kickoffem,
edycję typu do rozpoczęcia meczu oraz ręczne rozliczenie punktów `5/3/1/0`.

Komendy:

- `/typ wynik:<gospodarze>:<goście>`
- `/moj-typ`
- `/wszystkie-typy` — prywatna lista wszystkich typów na bieżący mecz (trwający
  lub z otwartym oknem typowania; trwający ma pierwszeństwo), posortowana
  wg wyniku i bramek (wygrana gospodarzy, remis, wygrana gości)
- `/admin-mecz-dodaj gospodarze:<nazwa> goscie:<nazwa> rozgrywki:<nazwa> kickoff:<data>`
- `/admin-mecz-edytuj kickoff:<data>`
- `/admin-mecz-wynik wynik:<gospodarze>:<goście>`

Komendy administracyjne wymagają uprawnienia `Manage Guild` albo `Administrator`.
Kickoff należy podawać jako czas Polski w formacie `RRRR-MM-DD GG:MM`, np.
`2026-09-12 18:30`. Bot konwertuje tę wartość do UTC w bazie.
Wszystkie slash commands działają wyłącznie na kanale wskazanym przez
`CHANNEL_ID` w pliku `.env`.
Bot publikuje tam również ogłoszenia o konfiguracji meczu, rozpoczęciu
typowania, zmianie kickoffu i zakończeniu rozliczenia. Ogłoszenia o otwarciu
typowania są sprawdzane co 5 minut.

## Uruchomienie

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
# uzupełnij DISCORD_TOKEN
New-Item -ItemType Directory -Force data
py -m alembic upgrade head
py -m united_bot.main
```

Bot używa SQLite w trybie WAL. Automatyczna synchronizacja meczów, oceny
zawodników i rankingi nie są częścią obecnego MVP.

Logi aplikacji i biblioteki Discord są kierowane na standardowe wyjście
terminala. Token Discorda nie jest zapisywany w logach.
