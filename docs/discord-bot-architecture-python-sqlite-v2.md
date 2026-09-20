# Architektura bota Discord — Python + SQLite v2

## Status dokumentu

- Status: zaakceptowana architektura MVP / pierwszej wersji produkcyjnej
- Podejście: modularny monolit
- Styl: hexagonal architecture / ports and adapters
- Runtime: jeden proces aplikacji
- Główne decyzje: Python, discord.py, SQLite, APScheduler
- Cel: typer Manchesteru United, oceny piłkarzy, sezonowe zgadywanki i podsumowania LLM

## 1. Decyzje technologiczne

```text
Python 3.12+
discord.py 2.x
SQLite w trybie WAL
SQLAlchemy 2.x async + aiosqlite
Alembic
Pydantic v2
httpx
APScheduler w tym samym procesie
Ollama adapter jako opcjonalna integracja
pytest + pytest-asyncio
Docker Compose
```

Świadomie nie używamy na obecnym etapie:

```text
PostgreSQL
Redis
BullMQ
mikroserwisów
osobnego workera
```

SQLite jest odpowiednim wyborem, jeśli bot działa jako jeden proces zapisujący dane, obsługuje jeden lub kilka serwerów Discord i nie ma dużej liczby równoległych zapisów. Migracja do PostgreSQL będzie uzasadniona dopiero przy wielu instancjach, osobnych workerach, dużym ruchu lub problemach z równoległością.

## 2. Zakres funkcjonalny

Bot powinien obsługiwać:

- synchronizację terminarza i wyników meczów Manchesteru United;
- typowanie wyniku przez `/typ wynik:3:1`;
- otwarcie typowania określoną liczbę godzin przed kickoffem;
- automatyczne zamknięcie typowania przed rozpoczęciem meczu;
- rozliczanie punktów po meczu;
- tabelę sezonową;
- ocenianie zawodników, którzy rozegrali więcej niż 5 minut;
- ocenianie przez selecty Discorda, z podziałem na pozycje i strony;
- przedsezonowe zgadywanki;
- przewidywane i potwierdzone składy, jeśli dostawca danych je udostępnia;
- generowanie podsumowań przez LLM;
- komendy administracyjne do obsługi sezonu, kanałów i synchronizacji.

## 3. Architektura logiczna

```text
Discord Gateway / Interactions
              │
              ▼
      Discord adapter (discord.py)
              │
              ▼
       Application services / use cases
      ┌───────┼─────────┬──────────┐
      ▼       ▼         ▼          ▼
    Typer    Oceny     Mecze      Sezony
      │       │         │          │
      └───────┴─────────┴──────────┘
              │
              ▼
       Domain models + ports
      ┌───────┼─────────┬──────────┐
      ▼       ▼         ▼          ▼
 SQLite   Football API   LLM    Scheduler
 adapter    adapter    adapter   adapter
```

### Zasada zależności

Zależności kierują się do środka:

```text
adapters → application → domain
```

Warstwa `domain` nie może importować `discord.py`, SQLAlchemy, `httpx`, APScheduler ani konkretnego klienta LLM. `application` korzysta z portów, a konkretne implementacje portów są dostarczane podczas składania aplikacji.

## 4. Porty i adaptery

### Port danych piłkarskich

```python
class FootballDataPort(Protocol):
    async def list_team_matches(
        self,
        team_id: str,
        from_at: datetime,
        to_at: datetime,
    ) -> list[ExternalMatch]: ...

    async def get_match_details(
        self,
        external_match_id: str,
    ) -> ExternalMatchDetails: ...
```

Możliwe adaptery:

```text
SportmonksAdapter
ApiFootballAdapter
FootballDataAdapter
FakeFootballDataAdapter
```

Adapter mapuje odpowiedź providera na wewnętrzne modele. Surowy payload należy zachować w bazie, ale logika domenowa nie może zależeć od jego struktury.

### Port LLM

```python
class LlmPort(Protocol):
    async def summarize_match(self, context: MatchSummaryContext) -> LlmResult: ...
```

Możliwe adaptery:

```text
OllamaAdapter
OpenAiAdapter
FakeLlmAdapter
```

LLM jest funkcją niekrytyczną. Awaria Ollama nie może zatrzymać synchronizacji, rozliczania typów ani ocen.

### Port harmonogramu

```python
class SchedulerPort(Protocol):
    def add_interval_job(self, name: str, seconds: int, callback) -> None: ...
    def add_date_job(self, name: str, run_at: datetime, callback) -> None: ...
    def start(self) -> None: ...
    def shutdown(self) -> None: ...
```

Implementacja produkcyjna:

```text
APSchedulerAdapter
```

Implementacja testowa:

```text
FakeSchedulerAdapter / NoopSchedulerAdapter
```

Cron systemowy pozostaje opcją dla backupu albo ręcznych synchronizacji, ale nie powinien równolegle zapisywać do SQLite, gdy działa bot. Jedna ścieżka zapisu ogranicza ryzyko `database is locked`.

## 5. Model domenowy

Minimalne modele domenowe:

```text
Season
- id
- guild_id
- name
- status: DRAFT | ACTIVE | FINISHED
- starts_at
- ends_at
- prediction_open_offset_hours

Match
- id
- guild_id
- season_id
- provider
- external_id
- competition
- home_team
- away_team
- kickoff_at_utc
- status: SCHEDULED | IN_PLAY | FINISHED | POSTPONED | CANCELLED
- home_score
- away_score
- data_quality

Prediction
- match_id
- discord_user_id
- home_score
- away_score
- submitted_at
- updated_at
- awarded_points

PlayerAppearance
- match_id
- player_id
- name
- position
- started
- substituted_in_minute
- substituted_out_minute
- minutes_played

PlayerRating
- match_id
- player_id
- discord_user_id
- rating: 1..10
- submitted_at
- updated_at
```

Dla MVP mecz może należeć bezpośrednio do guilda. Jeżeli później ten sam mecz ma być współdzielony przez wiele serwerów, można wydzielić `external_matches` oraz `season_matches`.

## 6. SQLite i trwałość danych

SQLite jest źródłem prawdy dla:

- konfiguracji serwera;
- sezonów;
- meczów i wyników;
- typów i punktów;
- zawodników i występów;
- ocen;
- statusu synchronizacji;
- historii zadań;
- podsumowań LLM.

### Konfiguracja SQLite

Wymagane ustawienia:

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
```

Zasady:

- krótkie transakcje;
- jedna ścieżka zapisu;
- brak długich operacji HTTP w transakcji;
- indeksy dla często używanych filtrów;
- migracje wersjonowane przez Alembic;
- identyfikatory Discorda i providerów przechowywane jako `TEXT`;
- backup przez SQLite Backup API, a nie zwykłe kopiowanie aktywnego pliku.

## 7. Model relacyjny

```text
guilds
- id
- discord_guild_id TEXT UNIQUE
- name
- timezone
- created_at
- updated_at

guild_settings
- guild_id
- key
- value_json
- updated_by_discord_user_id TEXT
- updated_at

seasons
- id
- guild_id
- name
- status
- starts_at
- ends_at
- prediction_open_offset_hours
- created_by_discord_user_id TEXT
- created_at

matches
- id
- guild_id
- season_id
- provider
- external_match_id TEXT
- competition
- home_team
- away_team
- kickoff_at_utc
- status
- home_score
- away_score
- data_quality
- provider_updated_at
- source_payload_json
- synced_at
- last_sync_error

players
- id
- provider
- external_player_id TEXT
- name
- position
- team_name

match_appearances
- id
- match_id
- player_id
- started
- substituted_in_minute
- substituted_out_minute
- minutes_played
- lineup_position
- source_payload_json

predictions
- id
- match_id
- discord_user_id TEXT
- home_score
- away_score
- submitted_at
- updated_at
- awarded_points
- UNIQUE(match_id, discord_user_id)

player_ratings
- id
- match_id
- player_id
- discord_user_id TEXT
- rating
- submitted_at
- updated_at
- UNIQUE(match_id, player_id, discord_user_id)

season_predictions
- id
- season_id
- discord_user_id TEXT
- category
- value_json
- submitted_at
- awarded_points
- UNIQUE(season_id, discord_user_id, category)

job_runs
- id
- run_key TEXT UNIQUE
- job_name
- planned_run_at
- status: PENDING | RUNNING | SUCCESS | FAILED
- attempts
- locked_at
- started_at
- finished_at
- last_error

llm_summaries
- id
- match_id
- model
- prompt_version
- status: PENDING | RUNNING | SUCCESS | FAILED
- text
- generated_at
- last_error
```

## 8. Reguły typowania

Typowanie jest otwarte, gdy wszystkie warunki są spełnione:

```text
season.status == ACTIVE
AND match.status == SCHEDULED
AND now_utc >= kickoff_at_utc - prediction_open_offset_hours
AND now_utc < kickoff_at_utc
```

To sprawdzenie wykonuje use case zapisu typu przy każdym `/typ`. Scheduler może publikować informacje o otwarciu i zamknięciu, ale nie jest źródłem prawdy.

### Zasady zapisu

- jeden typ na użytkownika i mecz;
- edycja typu do deadline’u;
- po deadline’ie brak insertu i update’u;
- zapis i aktualizacja typu w transakcji;
- unikalność wymuszana w bazie;
- wszystkie czasy w bazie jako UTC;
- prezentacja w strefie skonfigurowanej dla guilda.

## 9. Formalny system punktacji

Przed implementacją trzeba zatwierdzić reguły. Proponowany system bazowy:

```text
3 punkty — dokładny wynik
1 punkt  — poprawny rezultat: wygrana/remis/przegrana
0 punktów — pozostałe przypadki
```

Opcjonalne elementy należy ustalić osobno:

- bonus za różnicę bramek;
- bonus za wytypowanie czystego konta;
- liczenie tylko wyniku po 90 minutach;
- dogrywka i rzuty karne;
- walkower;
- mecz przełożony lub anulowany;
- korekta wyniku przez providera;
- ponowne rozliczenie po korekcie.

Reguły punktacji powinny być czystą funkcją domenową i mieć testy tabelaryczne przed podłączeniem Discorda i bazy.

## 10. Oceny zawodników

Po zakończeniu meczu adapter pobiera:

- wyjściowy skład;
- ławkę;
- wejścia i zejścia z boiska;
- minuty zdarzeń;
- formację i pozycję, jeśli są dostępne.

Serwis domenowy wylicza `minutes_played` i kwalifikuje zawodników według jawnej reguły:

```text
minutes_played > 5
```

Do ustalenia przed implementacją:

- czy wejście dokładnie w 5. minucie kwalifikuje zawodnika;
- jak liczyć doliczony czas;
- jak traktować niekompletne zdarzenia;
- czy oceny są dostępne do następnego meczu, czy przez określoną liczbę godzin;
- czy użytkownik może zmienić ocenę przed zamknięciem.

`/ocen` wysyła prywatny widok z:

- zawodnikami pogrupowanymi według pozycji;
- selectami ocen 1–10;
- kilkoma wiadomościami lub stronami z powodu limitów komponentów Discorda;
- zapisem po każdym wyborze;
- możliwością aktualizacji własnej oceny.

Callback komponentu ponownie sprawdza użytkownika, mecz, okno ocen i kwalifikację zawodnika. Nie należy ufać samemu `custom_id`.

## 11. Synchronizacja danych piłkarskich

Przepływ:

```text
scheduler
   │
   ▼
FootballDataPort
   │
   ▼
provider adapter
   │
   ▼
mapper / normalizer
   │
   ▼
transactional upsert do SQLite
   │
   ▼
application events / dalsze use case'y
```

Częstotliwość zależy od rodzaju danych:

- terminarz: co kilka godzin;
- status i wynik w dniu meczu: co 1–5 minut;
- składy przed meczem: częściej w ostatnich 90 minutach;
- szczegóły i zmiany po meczu: do czasu kompletności danych.

Nie wolno rozliczać meczu wyłącznie dlatego, że provider zwrócił status `FINISHED`. Trzeba potwierdzić wynik i minimalną kompletność danych. Zapisywać należy `data_quality`, `last_sync_error` i `provider_updated_at`.

## 12. Harmonogram i idempotencja

APScheduler działa w tym samym procesie co bot. Przykładowe zadania:

```text
sync_fixtures              co 6–12 godzin
sync_live_match_details    co 1–5 minut w dniu meczu
finalize_finished_matches  co 1–5 minut
publish_notifications      według potrzeb
backup_sqlite              raz dziennie
```

Każde zadanie musi być idempotentne. `job_runs` przechowuje deterministyczny `run_key`, np.:

```text
sync_match:sportmonks:12345:2026-09-05T14:00Z
finalize_match:local-match-id:attempt-slot
```

Status `RUNNING` powinien mieć `locked_at`, aby po awarii można było uznać stary lock za wygasły. Retry powinien dotyczyć wyłącznie błędów przejściowych.

Scheduler nie decyduje o tym, czy użytkownik może oddać typ. On tylko synchronizuje dane i uruchamia działania poboczne.

## 13. LLM i podsumowania

LLM jest funkcją niekrytyczną i musi być odseparowany od rozliczania meczu.

```text
mecz FINISHED i dane kompletne
   ├── zapisz wynik
   ├── rozlicz typy
   ├── otwórz/aktywuj oceny
   └── utwórz zadanie podsumowania LLM
```

Do promptu trafia znormalizowany kontekst:

- wynik;
- gole i minuty;
- kartki;
- zmiany;
- składy;
- statystyki;
- oceny użytkowników, jeśli są już dostępne.

Podsumowanie zapisuje się w `llm_summaries`, aby ponowne uruchomienie nie generowało duplikatów. Warto przechowywać model, wersję promptu, status i błąd.

## 14. Uprawnienia i komendy

Komendy publiczne:

```text
/typ
/ocen
/mecze
/tabela
/podsumowanie-meczu
```

Komendy administracyjne:

```text
/admin start-sezon
/admin stop-sezon
/admin synchronizuj-mecze
/admin ustaw-kanał
/admin rozlicz-mecz
/admin zamknij-oceny
/admin ustaw-konfiguracje
```

Admin-only powinno być egzekwowane zarówno przez deklarację uprawnień Discorda, jak i runtime check oparty o konfigurację guilda. Nie używać globalnego `Administrator` bez potrzeby.

## 15. Struktura repozytorium

```text
src/
├── main.py
├── config/
│   ├── settings.py
│   └── logging.py
├── domain/
│   ├── models/
│   │   ├── match.py
│   │   ├── season.py
│   │   ├── prediction.py
│   │   └── rating.py
│   ├── services/
│   │   ├── scoring.py
│   │   ├── playing_time.py
│   │   └── prediction_window.py
│   └── ports/
│       ├── repositories.py
│       ├── football_data.py
│       ├── llm.py
│       └── scheduler.py
├── application/
│   ├── typer/
│   │   ├── submit_prediction.py
│   │   ├── calculate_points.py
│   │   └── standings.py
│   ├── ratings/
│   │   ├── list_eligible_players.py
│   │   └── submit_rating.py
│   ├── matches/
│   │   ├── sync_fixtures.py
│   │   ├── sync_match_details.py
│   │   └── finalize_match.py
│   ├── seasons/
│   │   ├── start_season.py
│   │   └── stop_season.py
│   └── summaries/
│       └── generate_match_summary.py
├── adapters/
│   ├── discord/
│   │   ├── bot.py
│   │   ├── commands/
│   │   │   ├── typer.py
│   │   │   ├── ratings.py
│   │   │   ├── matches.py
│   │   │   └── admin.py
│   │   ├── components/
│   │   │   └── ratings_view.py
│   │   └── permissions.py
│   │   ├── persistence/
│   │   │   ├── sqlite.py
│   │   │   ├── models.py
│   │   │   └── repositories/
│   │   ├── football/
│   │   │   ├── provider.py
│   │   │   ├── mapper.py
│   │   │   └── fake_provider.py
│   │   ├── llm/
│   │   │   ├── ollama.py
│   │   │   ├── prompt_builder.py
│   │   │   └── fake_llm.py
│   │   └── scheduler/
│   │       ├── apscheduler_adapter.py
│   │       └── cron_jobs.py
├── jobs/
│   ├── sync_matches.py
│   ├── finalize_matches.py
│   └── backup_database.py
└── shared/
    ├── errors.py
    ├── time.py
    └── ids.py

tests/
├── domain/
│   ├── test_scoring.py
│   ├── test_prediction_window.py
│   └── test_playing_time.py
├── application/
└── adapters/
```

W pokazanym drzewie `adapters/discord` i `adapters/persistence` są rodzeństwem; fizycznie `persistence` nie powinno znajdować się wewnątrz katalogu `discord`.

Poprawiona wersja:

```text
adapters/
├── discord/
├── persistence/
├── football/
├── llm/
└── scheduler/
```

## 16. Minimalny przykład cienkiego handlera

```python
@app_commands.command(name="typ", description="Zapisz typ wyniku")
async def typ(interaction: discord.Interaction, wynik: str) -> None:
    await interaction.response.defer(ephemeral=True)

    try:
        home_score, away_score = parse_score(wynik)
        result = await submit_prediction.execute(
            guild_id=str(interaction.guild_id),
            user_id=str(interaction.user.id),
            home_score=home_score,
            away_score=away_score,
        )
    except DomainError as exc:
        await interaction.edit_original_response(content=str(exc))
        return

    await interaction.edit_original_response(content=result.message)
```

Use case `submit_prediction` odpowiada za znalezienie aktywnego meczu, weryfikację okna czasowego oraz zapis transakcyjny. Handler nie zna SQL, modelu ORM ani reguł punktacji.

## 17. Niezawodność i bezpieczeństwo

Minimum produkcyjne:

- token Discorda, klucze API i konfiguracja tylko w `.env`/secretach;
- `.env` poza repozytorium;
- timeouty HTTP;
- retry tylko dla błędów przejściowych;
- exponential backoff;
- walidacja każdej wartości z komendy i komponentu;
- brak logowania sekretów;
- transakcje dla operacji wieloetapowych;
- graceful shutdown i obsługa `SIGTERM`;
- healthcheck procesu;
- `restart: unless-stopped`;
- regularny backup SQLite przez Backup API;
- test przywracania backupu;
- audit log operacji administracyjnych;
- brak Message Content Intent, jeśli bot używa tylko slash commands i komponentów;
- ograniczone uprawnienia Discorda.

## 18. Obserwowalność

Logować ustrukturyzowane pola:

```text
request_id
guild_id
user_id
command_name
match_id
duration_ms
status
error_code
```

W MVP wystarczą logi JSON i `/system health`. Monitorować należy:

- stan połączenia Gateway;
- czas i błędy komend;
- czas i błędy API piłkarskiego;
- czas i błędy LLM;
- czas ostatniej udanej synchronizacji;
- liczbę nierozliczonych meczów;
- status i rozmiar backupu SQLite.

Prometheus i Grafana pozostają opcjonalnym późniejszym rozszerzeniem.

## 19. Kolejność implementacji

1. Zdefiniować modele domenowe i reguły punktacji.
2. Napisać testy punktacji, deadline’u i liczenia minut — bez Discorda i bazy.
3. Utworzyć SQLite, Alembic i repositories.
4. Zaimplementować adapter jednego dostawcy danych piłkarskich.
5. Dodać `/mecze` i `/typ`.
6. Dodać rozliczanie wyników.
7. Dodać `/ocen` i komponenty select.
8. Dodać sezony i zgadywanki.
9. Dodać APScheduler oraz automatyczne synchronizacje.
10. Dodać Ollama jako opcjonalny adapter podsumowań.
11. Dodać backup, healthcheck i testy awarii.

## 20. Wniosek

Rekomendowana wersja projektu:

```text
Python + discord.py
SQLite WAL
SQLAlchemy async + aiosqlite
Alembic
APScheduler w jednym procesie
adapter Football API
adapter Ollama/LLM
Docker Compose
```

Najważniejsze zasady:

1. Scheduler automatyzuje działania, ale nie decyduje o ważności typu.
2. Reguły domenowe są testowane bez Discorda, bazy i zewnętrznych API.
3. SQLite jest jedynym źródłem trwałego stanu w MVP.
4. LLM nie blokuje krytycznych operacji.
5. Adaptery izolują zmienne integracje od stabilnej logiki aplikacji.
6. Jedna ścieżka zapisu do SQLite ogranicza problemy z blokadami.

To jest wersja gotowa do przejścia z analizy do implementacji fundamentu.
