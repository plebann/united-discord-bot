# Specyfikacja implementacji — pogłębienie architektury (5 kandydatów)

Stan: **potwierdzona do implementacji** (konsolidacja 5 wątków grillingowych T1–T5 + korekty
centralne C1–C7; fronty wszystkie puste). Zakres obejmuje dokładnie pięć kandydatów
pogłębienia z raportu architektonicznego:

| Kandydat | Wątek | Jądro |
|---|---|---|
| 1 | T1 | Jeden „aktywny mecz do typowania" w warstwie aplikacji |
| 2 | T2 | Prezentacja jako czysty moduł poza adapterem |
| 3 | T3 | Jeden moduł odpowiedzi znający okno 3 sekund |
| 4 | T4 | Event-shaped interfejs modułu ogłoszeń |
| 5 | T5 | `BotConfig` / env / literały strefy i okna |

## Problem Statement

Użytkownik bota widzi spójny produkt, ale kod ma systematyczne zapachy:

- **Rozproszona polityka „który mecz"**: trzy use-casesy (`save_prediction`,
  `get_prediction`, `list_predictions`) składają kolejność priorytetów po swojemu
  (save pyta przyszły, get/list pytają trwający), a adapter `/moj-typ` wyprowadza fazę
  meczu surowym `datetime.now(...)` — klasa błędu, która już raz dała defekt.
- **Teksty użytkownika w adapterze**: wszystkie komunikaty (ogłoszenia, listingi,
  odpowiedzi komend) siedzą inline w module Discorda — nie da się ich testować bez
  Discorda, a żadne nowe użycie nie może ich bezpiecznie podzielić.
- **Naruszane okno 3 sekund**: część handlerów wykonuje I/O przed deferem; wiedza o
  protokole (defer / `is_done` / widoczność / chunking) rozrzucona jest po handlerach
  i publisherze; `/typ` i `/moj-typ` nie mają mapowania błędów do wiadomości.
- **Moduł ogłoszeń zorientowany na metody-publish**: cog musi wiedzieć, którą z pięciu
  metod wołać; `/admin-mecz-wynik` generuje dwa odrębne ogłoszenia dwoma wywołaniami.
- **Literały przeciekające przez szwy**: `CHANNEL_ID` czytany z env w trzech miejscach,
  strefa `Europe/Warsaw` jako stała adaptera, 3-dniowe okno typowania jako literał
  `timedelta(days=3)` w domenie i repozytorium, martwa linia `PREDICTION_OPEN_DAYS`
  w `.env.example`.

## Solution

Dla użytkownika bota: **nic się nie zmienia** — wszystkie stringi pozostają bajtowo
identyczne, UX komend zachowuje frazy, kolejności i widoczność (jedyny celowy wyjątek:
komendy admina dostają krótki efemeralny placeholder „myślę" przed publicznym ackiem,
bo defer idzie przed I/O). Zmiana jest w budowie kodu:

1. Aplikacja dostaje **jeden szew `active_match`** niosący fazę meczu jako wartość
   („Aktywny mecz do typowania": trwający nierozliczony > otwarte okno; inaczej brak) —
   trzy use-casesy i adapter przestają wyprowadzać fazę.
2. Wszystkie teksty użytkownika żyją w **nowym czystym module prezentacji**; adapter
   zawiera zero inline-stringów poza stałami błędów.
3. **Nowy moduł odpowiedzi** (`InteractionReply`) przejmuje całą wiedzę protokołu
   okna 3 sekund: każdy handler = `begin()` → serwis → string prezentacji → `send`;
   błędy przez `fail(exc)`. Latentne naruszenia okna (3 komendy admina + `/typ`)
   znika.
4. Moduł ogłoszeń staje się **event-shaped**: cog raportuje fakty
   (`match_added`, `kickoff_changed`, `match_settled`, `prediction_reply`), serwis
   decyduje kiedy/raz/co; rozliczenie = jedno wywołanie.
5. Runtime config ma **jedno typowane dom** (`BotConfig`: walidowany `channel_id` +
   konfigurowalna strefa wyświetlania), startup **fail-fast** przy braku/invalid
   `CHANNEL_ID`, a 3-dniowe okno typowania ma nazwaną stałą domeny.

## User Stories

1. Jako developer, chcę, by reguła priorytetu „mecz trwający > otwarte okno" żyła w
   jednej czystej funkcji w module reguł, aby wszystkie use-casesy dzieliły jeden
   testowany dom polityki.
2. Jako developer, chcę, by `TyperService.active_match` zwracało fazę jako wartość
   (frozen dataclass), aby żaden caller nie mógł ponownie wyprowadzić fazy inline.
3. Jako użytkownik `/typ`, chcę, by komunikat o minionym czasie typowania wskazywał
   nazwy drużyn meczu trwającego pobrane prosto z wyniku szewa, aby wiadomość była
   konkretna bez dodatkowych fetchy.
4. Jako użytkownik `/moj-typ`, chcę, by odpowiedź rozgałęziła się na obiekcie
   niesącym fazę, aby rozróżnienie „nie masz typu na aktualnie trwający mecz" vs.
   „nie masz jeszcze typu dla meczu #id" było poprawne bez zegara w adapterze.
5. Jako developer, chcę, by adapter `/moj-typ` przestał wołać `datetime.now(...)`
   bezpośrednio, aby konwencja pinned-now obowiązywała wszędzie.
6. Jako developer, chcę, by `get_prediction` zwracało `MyPrediction`
   (match/prediction/in_progress), aby handler gałęziował na jednym obiekcie.
7. Jako developer, chcę, by `list_predictions` zwracało `(ActiveMatch | None, lista)`,
   aby formatter `/wszystkie-typy` dostawał fazę jako wartość zamiast parametru czasu.
8. Jako utrzymujący, chcę, by `add_match`/`edit_kickoff`/`finish_match` i
   `get_next_scheduled` pozostały nietknięte, aby pojęcie „Nierozliczony mecz"
   pozostało rozdzielone od „Aktywny mecz do typowania".
9. Jako testujący, chcę dedykowanego pliku behawioralnego pinującego priorytet
   z piniętym `now`, aby reguła miała pokrycie unitowe obok istniejącego kontraktu
   end-to-end.
10. Jako developer, chcę wszystkich tekstów użytkownika w jednym czystym module
    prezentacji, aby adapter nie zawierał inline-stringów.
11. Jako developer, chcę, by funkcje prezentacji były czyste nad wartościami domeny
    i callable nazw, aby testować je bez Discorda i bazy.
12. Jako użytkownik bota, chcę, by każdy komunikat był bajtowo identyczny po zmianie,
    aby nie było żadnej widocznej regresji.
13. Jako developer, chcę, by `format_match_listing` przyjmował strefę jako parametr,
    aby jedyny serwerowy render kickoffu (`strftime`) używał konfigurowanej strefy
    wyświetlania.
14. Jako użytkownik bota na dowolnym urządzeniu, chcę, by ogłoszenia kickoffu nadal
    używały tokenów `<t:…>`, aby Discord lokalizował czas według moich ustawień.
15. Jako developer, chcę linii pustego listingu („Nikt jeszcze nie typował…") w jednym
    miejscu, aby komunikat nie rozjechał się między kontekstami.
16. Jako developer, chcę stałych `MAN_UTD` i `LISTING_GROUP_HEADINGS` w miejscach ich
    użycia (stała klubu w domenie, nagłówki grup w prezentacji), aby literały miały
    jedno dom.
17. Jako utrzymujący, chcę, by reguła `ensure_man_utd_involvement` używała tej samej
    stałej klubu co prezentacja, aby klub nie był zduplikowany jako string.
18. Jako użytkownik komend, chcę, by każda komenda deferowała przed jakimkolwiek I/O,
    aby nigdy nie zobaczyć „Interaction failed" przy wolnym zapisie.
19. Jako developer, chcę, by klasa `InteractionReply` władała stanem protokołu
    (deferowana? wysłano? widoczność?), aby handler nie znał `is_done`, deferu ani
    widoczności.
20. Jako developer, chcę, by `begin()` była bezwzględnie pierwszym dotknięciem
    interakcji i rzucała jawny błąd przy podwójnym `begin()`, aby nadużycie protokołu
    było głośne w testach.
21. Jako użytkownik `/typ` i `/moj-typ`, chcę, by błędy serwisu trafiały do efemeralnej
    wiadomości zamiast stack trace'u, aby komunikacja o błędzie była czytelna.
22. Jako developer, chcę jednego domy dla limitu długości wiadomości Discord
    (`chunk_messages`), aby publisher i moduł odpowiedzi nie miały odrębnych stałych.
23. Jako developer, chcę, by globalny handler błędów komend współdzielił ten sam
    prywatny helper dostarczania co `fail()`, aby wiedza protokołu żyła w jednym
    miejscu.
24. Jako administrator, chcę, by tekst acka „Ogłoszenie zostało opublikowane."
    pozostał identyczny i efemeralny, aby UX admina był stabilny.
25. Jako administrator, chcę, by `_require_admin` pozostawał na cogu i wysyłał
    natychmiastową efemeralną odpowiedź przed jakimkolwiek `InteractionReply`,
    aby polityka autoryzacji nie wchodziła do modułu odpowiedzi.
26. Jako developer, chcę, by pętla ogłoszeń pozostała try/except log-only,
    aby jeden zły cykl nie zabijał zaplanowanej pracy.
27. Jako developer, chcę, by `AnnouncementService` był event-shaped
    (`match_added`/`kickoff_changed`/`match_settled`/`prediction_reply` + `poll`),
    aby cog raportował fakty, a serwis decydował kiedy/raz/co.
28. Jako administrator, chcę, by po `/admin-mecz-wynik` jedno wywołanie serwisu
    opublikowało parę ogłoszeń (rozpoczęcie + wynik) z deduplikacją per typ,
    aby rozliczenie nie wymagało zapamiętywania dwóch metod.
29. Jako administrator, chcę, by ponowne rozliczenie po częściowej awarii ponowiło
    tylko niezapisany typ ogłoszenia, aby retry był idempotentny bez migracji.
30. Jako developer, chcę, by `prediction_reply` budowała i zwracała string,
    aby handler `/typ` dostarczał tekst przez moduł odpowiedzi, nie przez serwis.
31. Jako developer, chcę, by serwis importował funkcje prezentacji bezpośrednio
    (bez iniekcji w konstruktorze), aby renderowanie tekstu nie było kolejnym szwem do
    podpinania.
32. Jako operator, chcę, by przy braku lub invalid `CHANNEL_ID` bot kończył start z
    czytelnym błędem, aby nie działać w stanie, w którym każda komenda zawiesza.
33. Jako developer, chcę frozen dataclass `BotConfig` z dwoma polami
    (`channel_id: int`, `display_timezone: ZoneInfo`), aby runtime config miał jedno
    typowane dom.
34. Jako developer, chcę czystego walidatora `parse_channel_id`, aby testować
    walidację bez env i composition roota.
35. Jako developer, chcę fabryki `make_channel_check(channel_id)`, aby check
    interpolował zwalidowany int, a martwa gałąź „nie ma skonfigurowanego kanału"
    zniknęła wraz ze swoją stałą.
36. Jako operator, chcę, by `.env.example` listowało tylko zmienne czytane przez kod,
    aby martwa linia `PREDICTION_OPEN_DAYS` nie zapraszała do przedwczesnego
    podpinania.
37. Jako developer, chcę nazwanej stałej domeny `PREDICTION_WINDOW = timedelta(days=3)`
    używanej w `Match.prediction_opens_at` i w repozytorium, aby okno 3-dniowe miało
    jedno dom, a planowane przełączenie na env było osobną decyzją projektową.
38. Jako developer, chcę, by stała strefy adaptera zniknęła, a `ZoneInfo("Europe/Warsaw")`
    był składany w composition root jako konfigurowalne pole configu, aby strefa
    wyświetlania była decyzyjna, a nie zakodowana w module Discorda.
39. Jako przyszły agent LLM, chcę zaktualizowanego AGENTS.md (nowy moduł config,
    przepisane „Known deltas"), aby udokumentowana architektura zgadzała się z kodem.
40. Jako utrzymujący, chcę dokumentu reguł domenowych v1.5 z mapowaniem terminologicznym
    („docelowy mecz" = „Aktywny mecz do typowania") przy literalnym tekście reguły,
    aby ustalone zachowanie nie zostało przepisane.

## Implementation Decisions

Korekty cross-thread C1–C7 są wchłonięte poniżej; pełny ich rejestr — w sekcji
„Further Notes". Nazwy modułów odpowiadają modułom pakietu bota (patrz AGENTS.md);
sygnatury są artefaktami decyzji i podane celowo precyzyjnie.

### Moduł domeny (T1/T2/T5)

- Nowe stałe modułowe: `MAN_UTD` (nazwa klubu; użytkownicy: prezentacja — porównanie
  drużyny w renderze wyniku — oraz reguła zaangażowania klubu w formie lowercased) i
  `PREDICTION_WINDOW = timedelta(days=3)` (własność T5; przejmuje T1).
- `Match.prediction_opens_at` używa `PREDICTION_WINDOW`; repozytorium importuje tę
  stałą zamiast własnego literału (import warstwowy db→domain jest dozwolony).
- Domena pozostaje czysta: zero zależności od configu; env-switch okna to osobna,
  przyszła decyzja.

### Moduł reguł (T1)

- Nowa czysta funkcja (selector, nie walidator — stąd czasownik inny niż `ensure_*`):
  `select_active_match(in_progress: Match | None, open_window: Match | None) -> tuple[Match, bool] | None`.
  Zwraca `(match, True)` dla meczu trwającego, `(match, False)` dla otwartego okna,
  `None` gdy brak. Nie potrzebuje `now` — priorytet jest czysto strukturalny.
- Istniejące walidatory `ensure_*` nietknięte; `ensure_man_utd_involvement` przechodzi
  na stałą `MAN_UTD` (zakres W2 = b: prezentacja **+** reguły).

### Moduł aplikacji (T1)

- Dwa nowe frozen dataclass-y obok serwisu: `ActiveMatch(match: Match, in_progress: bool)`
  i `MyPrediction(match: Match | None, prediction: Prediction | None, in_progress: bool)`.
  Dom = aplikacja (nosiciel przypadku użycia, nie wartość domeny); promocja do domeny
  dopiero przy wielu użyciach.
- Nowa publiczna metoda: `TyperService.active_match(guild_id, now=None) -> ActiveMatch | None`
  — kompozycja dwóch istniejących fetchery repozytorium (najpierw `get_in_progress`,
  potem `get_current`) + reguła z modułu reguł + owinięcie w nosiciel.
- `save_prediction`, `get_prediction`, `list_predictions` trafiają przez szew
  `active_match`; zwroty: `save_prediction` zostaje trzy-elementówką (match,
  prediction, previous) ale mecz pochodzi z szewa; `get_prediction` → `MyPrediction`;
  `list_predictions` → `(ActiveMatch | None, list[Prediction])`, przypadek pusty
  `(None, [])`.
- Zmiana semantyczna (W1, przycięta): w stanie legacy dwóch nierozliczonych meczów
  `/typ` trafia w trwający zamiast przyszłego i zgłasza minione okno — akceptowane
  jako konsekwencja spójnej polityki szwu; stan jest nieosiągalny normalną drogą
  (`add_match` go blokuje), **bez dedykowanej analizy i testu**.
- `add_match`, `edit_kickoff`, `finish_match`, `delete_match`, `list_matches` i
  `get_next_scheduled` nietknięte. Fetchery `get_current`/`get_in_progress` pozostają
  publiczne i nienaruszone — bez odchudzania redundancyjnego ponownego sprawdzenia
  `can_predict` (defensywne, ustalone zachowanie).

### Moduł prezentacji — NOWY (T2)

- Czyste funkcje nad wartościami domeny; zero I/O, zero Discorda. Katalog:
  - `format_prediction_listing(match, predictions, name_of) -> str`
  - `format_all_predictions(match, predictions, name_of, in_progress: bool) -> str`
  - `format_match_listing(matches, tz: ZoneInfo) -> str` — jedyna publiczna z `tz`
  - `_describe_match(match, tz: ZoneInfo) -> str` (prywatny; jedyny serwerowy
    `strftime`)
  - `format_typing_announcement(user_id, match, prediction, previous_prediction) -> str`
  - `format_my_prediction(match | None, prediction | None, in_progress: bool) -> str`
  - `format_match_configured(match, opening: bool) -> str`
  - `format_prediction_opened(match) -> str`
  - `format_match_started(match, predictions, name_of) -> str`
  - `format_match_edited(previous, updated, opening: bool, started: bool) -> str`
  - `format_result(match, top_predictions, total: int) -> str`
- Stałe: `LISTING_GROUP_HEADINGS` przeniesione do tego modułu; `MAN_UTD` importowane
  z domeny; stała strefy (`WARSAW`/`LOCAL_TIMEZONE`) nie istnieje.
- **Kontrakt bajtowej identyczności**: wszystkie stringi 1:1 z dzisiejszym kodem.
- Parametr `name_of` abstrahuje nazwę od pingu: serwis podaje callable zbudowany z
  resolvera nazw; handler `/wszystkie-typy` podaje lambda generującą `<@id>`
  (zachowanie bez zmian, bez nowego podpinania resolvera pod coga użytkownika).
- Nagłówek fazy („⚽ … trwa") w `format_all_predictions` pochodzi z parametru
  `in_progress`, nie z porównania timestampów.
- `parse_kickoff(value, tz)` pozostaje w module adaptera i zyskuje parametr strefy
  (konwersja krawędziowa `Europe/Warsaw → UTC`); prezentacja go nie przenosi.

### Moduł odpowiedzi — NOWY (T3)

- Klasa `InteractionReply` instancjonowana per handler; duck-typing na interakcji
  (`.response.defer/send_message`, `.followup.send`) — bez produkcyjnego Protocolu/
  adaptera.
- `begin()`: zawsze `defer(ephemeral=True)`; bezwzględnie pierwsze dotknięcie
  interakcji; guard — drugie `begin()` lub `send`/`fail` przed `begin()` rzuca jawne
  `RuntimeError`.
- Kształt każdego handlera: `reply.begin()` → wywołanie serwisu → string prezentacji
  → `reply.send(text)`; w `except` tylko `reply.fail(exc)`. Żaden handler nie zna
  `is_done`, deferu ani widoczności.
- `fail(exc)`: przejmuje tuple `(DomainError, LookupError, RuntimeError,
  discord.DiscordException)`; `DomainError`/`LookupError` → `str(exc)`, reszta →
  generyczna polska fraza jako stała modułu; dostarczenie efemeralne. Moduł jest
  „głupi" — nie śledzi częściowego sukcesu (ograniczenie w docstringu).
- `chunk_messages(text, limit=1900)` eksportowana publicznie; `DiscordAnnouncementPublisher`
  importuje ją (jeden dom limitu wiadomości Discord).
- Prywatny helper `_deliver(interaction, text)` (is_done → response vs. followup)
  eksportowany wewnętrznie: używają go `fail()` i gałąź `ChannelCheckFailure` globalnego
  `on_app_command_error` (struktura handlera bez zmian).
- `_acknowledge_announcement` znika; trzy potoki admina używają `reply.send` z tym
  samym tekstem acka, pinned jako efemeralny.
- `/typ` (pojazd D): `reply.begin()` → `save_prediction` → `prediction_reply(...)` →
  `reply.send(text)` — publiczna pierwsza odpowiedź przez followup; likwiduje
  latentne naruszenie okna 3 s (zapis do bazy przed odpowiedzią). Gałąź zmiany typu
  (publikacja ogłoszenia) i efemeralna fraza „Typ nie został zmieniony." — zachowanie
  bez zmian.
- Pętla ogłoszeń: try/except log-only bez zmian (nie-interaction).

### Moduł ogłoszeń (T4)

- Interfejs event-shaped, cztery metody + poll:
  - `match_added(match, now=None) -> None` — natychmiastowe ogłoszenie dodania
    (warianty otwarte/zamknięte okno przez `format_match_configured`).
  - `kickoff_changed(previous, updated, now=None) -> None` — cog ma oba mecze z
    `edit_kickoff`, zero dodatkowego fetchu.
  - `match_settled(finished, predictions, now=None) -> None` — wewnętrzna sekwencja:
    started (dedup `MATCH_STARTED`) → result (nowy dedup `MATCH_RESULT`); cog po
    `/admin-mecz-wynik` wywołuje dokładnie to jedno.
  - `prediction_reply(match, user_id, prediction, previous_prediction) -> str` —
    build-and-return (tekst przez `format_typing_announcement`); metoda nie
    publikuje; publikacja należy do modułu odpowiedzi po stronie handlera.
  - `poll(now=None)` — bez zmian: guild-agnostic due-listy (start po kickoff,
    otwarcie okna), 5-minutowa granularność akceptowalna (best-effort, brak gwarancji
    czasowej w docu).
- Deduplikacja: istniejący mechanizm `was_sent`/`mark_sent`/`_publish_once` bez zmian;
  `MATCH_RESULT` to nowa wartość danych w istniejącej kolumnie `String(40)` bez
  constraintu — **żadna migracja Alembic**; trzy istniejące wartości typów ogłoszeń w
  bazie nietknięte.
- Partial-failure: brak logiki kompensacyjnej; wyjątek wypływa do adaptera (mapowanie
  błędów wg AGENTS.md); dedup per typ pozwala ponowić tylko niezapisany typ.
- Prezentacja: bezpośredni import funkcji z modułu prezentacji (bez iniekcji w
  konstruktorze); `DisplayNameResolver` pozostaje po stronie serwisu, a do funkcji
  prezentacji trafia callable `name_of`. Cięcie top-10 dla wyniku wykonuje serwis.
- **Konstruktor bez zmian**: `(matches, predictions, announcements, publisher,
  display_names=None)` — **brak parametru strefy** (C1: kickoff w ogłoszeniach renderuje
  tokeny `<t:…>`, lokalizacja po stronie klienta Discorda).
- Metody admin zwracają `None`; ack niezależny od dedup.

### Moduł adaptera Discorda (T2/T3/T5)

- Cienkie cogy wg kształtu z T3; znikają: `LOCAL_TIMEZONE`, stała błędu konfiguracji
  kanału z gałęzią checka, `_split_messages` (chunking w module odpowiedzi),
  inline-stringi komend i ogłoszeń, gałąź RuntimeError „nieprawidłowy CHANNEL_ID" w
  publisherze.
- `make_channel_check(channel_id: int)` — fabryka zwracająca closure pod
  `app_commands.check`; kogi powstają przez funkcję fabryczną wewnątrz `create_bot`
  (dekorator nie może domykać instancji). Komunikat o niewłaściwym kanale interpoluje
  int.
- `DiscordAnnouncementPublisher(channel_id: int)` — skalar w konstruktorze;
  leniwe get/fetch kanału per publish zostaje (istnienie kanału nie jest sprawdzane
  przy starcie — bot jeszcze nie zalogowany).
- `TyperCog(config, service, announcements)` — trzyma obiekt configu i podaje
  `config.display_timezone` do `parse_kickoff(value, tz)` oraz
  `format_match_listing(matches, tz)`.
- `UserTyperCog(service, announcements)` — zyskuje serwis ogłoszeń (dla
  `prediction_reply`); **nie** zyskuje strefy ani resolvera nazw (C6/C7).
- `/moj-typ` i `/wszystkie-typy` gałęziują na wartościach z szewa T1; formatter
  `/wszystkie-typy` dostaje `in_progress` zamiast `now` oraz lambda pingu jako
  `name_of`.
- `create_bot(service, announcements, publisher, name_resolver, config)` — cały
  obiekt configu.

### Composition root (T5)

- Fail-fast: przed `create_session_factory`/`bot.start` — odczyt `CHANNEL_ID`,
  walidacja czystym `parse_channel_id`, przy braku/invalid → log błędu +
  `SystemExit(1)`. Typ pola configu to gołe `int` (bez Optional).
- `ZoneInfo("Europe/Warsaw")` składane tu jako konfigurowalne pole
  `display_timezone` (wariant B strefy); konsumenci wyłącznie komponenty `TyperCog`.
- `DISCORD_TOKEN`/`DATABASE_URL` zostają wyłącznie w composition root (wejścia
  startowe, nie runtime config).

### Nowy moduł config — NOWY (T5)

- Frozen dataclass `BotConfig{channel_id: int, display_timezone: ZoneInfo}` + czysty
  walidator `parse_channel_id(raw) -> int` (raise na puste/invalid; main łapie i
  konwertuje). Dataclass nie może żyć w main (cykl importów) ani w module adaptera
  (runtime config w warstwie adaptera = zły layer). Odczyt env zostaje w main.
- Limit chunków 1900 i interwał pętli ogłoszeń pozostają stałymi adaptera — poza
  configiem.

### Dokumentacja (wykonania centralne)

- Glosariusz: termin „Aktywny mecz do typowania" dodany; linia `_Avoid_` hasła
  „Nierozliczony mecz" nietknięta (goły zwrot „aktywny mecz" zostaje w zakazie; pełna
  forma jest jednoznaczna).
- Dokument reguł domenowych → v1.5: treść reguły priorytetu dosłownie (zero zmian
  semantycznych), mapowanie „docelowy mecz" = „Aktywny mecz do typowania" w sekcji
  prezentacji listy typów, changelog terminologiczny przy wersji.
- AGENTS.md: nowa linia dla modułu config w „Where things live"; „Known deltas"
  przepisane (okno 3 dni = nazwana stała domeny `PREDICTION_WINDOW`; przełączenie na
  env to osobna decyzja projektowa); dopisek o walidacji fail-fast w composition root.
- `.env.example`: usunięcie linii `PREDICTION_OPEN_DAYS=3`.

## Testing Decisions

Dobry test testuje wyłącznie zachowanie zewnętrzne (publiczna powierzchnia modułu,
pinned `now`, asercje na wartościach/tekstach) — nie white-box wewnętrznych helperów.

- **Moduł reguł** — funkcja selektora testowana czysto, bez repozytorium i bazy
  (trzy gałęzie: trwający / otwarte okno / brak).
- **Moduł aplikacji** — nowy plik behawioralny nazwany po zachowaniu, pinujący
  priorytet bezpośrednio na `TyperService.active_match` z piniętym `now`; istniejące
  pliki adaptują się mechanicznie do zmian sygnatur (rozpakowania `MyPrediction` w
  testach poprzedniego typu, zwrot `list_predictions`). Istniejący test priorytetowy
  (legacy dwa-nierozliczone, seed przez repo) zostaje jako kontrakt end-to-end.
- **Moduł prezentacji** — czyste funkcje z fikcjami domeny; testy szablonów ogłoszeń
  przechodzą **bez zmiany asercji** (stringi bajtowo identyczne, tokeny `<t:…>` nie
  zależą od strefy po stronie serwera); jedyne zwiększenie churnu = wywołania
  `format_match_listing` zyskują argument strefy.
- **Moduł ogłoszeń** — tylko przez publiczną powierzchnię zdarzeń (bez white-box
  `_send_*`): dedup started przez podwójny `poll(now=kickoff+5min)` z asercją na
  liczbie wywołań resolvera; `match_settled` → dwie wiadomości przy pierwszym
  wywołaniu, tylko pominięcie wysłanego typu przy ponownym; `prediction_reply` →
  asercje na zwróconym stringu. Wzorzec `RecordingPublisher`/`FakeNameResolver`
  pozostaje; konstrukcja serwisu w testach **nie** zyskuje parametru strefy.
- **Moduł odpowiedzi** — duck-typing na fake-interaction; mała współdzielona klasa
  recordera mieszka w `tests/` (nie w produkcyjnym module odpowiedzi); test pinujący
  tekst acka + efemeralność; testy guardów (`begin()` przed I/O, podwójne `begin()`);
  chunking testowany jako czysta funkcja.
- **Walidacja configu** — czyste testy walidatora (puste / niecyfrowe / nieprawidłowe
  wartości); wiring fail-fast jest sprawą composition root i nie jest testowany
  unitowo. Test „brak konfiguracji kanału" pada i zostaje zastąpiony testem
  walidatora.
- **Mechaniczna migracja istniejących testów**: monkeypatche env w testach checka
  kanału → fabryka z intem; monkeypatche env w testach publishera → skalar w
  konstruktorze; konstruktory cogów dostosowane do nowej liczby argumentów;
  `parse_kickoff` testowany ze strefą jako argumentem.
- Brak dedykowanego testu flipu semantyki `/typ` w stanie legacy (W1 przycięte:
  nie analizujemy sytuacji nieosiągalnych normalną drogą).

## Out of Scope

- Żadna zmiana widocznych stringów (kontrakt bajtowej identyczności) ani modelu
  rozliczania 5/3/1/0.
- Żadna migracja Alembic (`MATCH_RESULT` = wartość danych, nie zmiana row shape).
- Rename istniejących wartości typów ogłoszeń w bazie; żadne czyszczenie danych.
- Przenoszenie `DISCORD_TOKEN`/`DATABASE_URL` do `BotConfig`; konfigurowalne okno
  typowania przez env (stała zostaje w domenie — osobna przyszła decyzja).
- Odchudzanie redundancyjnej pętli `can_predict` w fetcherze „bieżący mecz"
  (defensywne, ustalone zachowanie).
- Zmiana granularności pętli ogłoszeń (5 min), per-guild polling, gwarancje czasowe
  ogłoszeń.
- Nowe uprzywilejowane intenty, APScheduler/httpx, wielogildijność.
- UX `/typ` poza pojazdem D (placeholder + publiczne ogłoszenie) — brak nowych
  wiadomości prywatnych, brak zmiany fraz.

## Further Notes

### Rejestr korekt cross-thread C1–C7

- **C1 · Strefa B zawężona**: `display_timezone` konsumują wyłącznie komponenty
  `TyperCog` (`parse_kickoff`, `format_match_listing`/`_describe_match` — jedyny
  serwerowy strftime); pozostałe ogłoszenia używają tokenów `<t:…>` lokalizowanych po
  stronie klienta → konstruktor serwisu ogłoszeń bez parametru strefy.
- **C2 · Pojazd `/typ` = D** (defer-first): nadpisuje sformułowanie T4 o „braku
  defer"; interfejs `prediction_reply -> str` nietknięty, zmienia się ciało handlera.
- **C3 · `prediction_reply(...)` zwraca `str`** (build-and-return), nie publikuje;
  metoda powstała z `publish_prediction`.
- **C4 · Nazewnictwo prezentacji = `format_*` z T2**; szkicowa seria nazw T4
  (`*_text`) nadpisana; mapowanie zdarzeń→funkcji: added→configured(+opened),
  kickoff_changed→edited, started→started, result→result, reply→typing_announcement.
- **C5 · Dwie stałe w domenie**: `MAN_UTD` (T2) + `PREDICTION_WINDOW` (T5, przejmuje T1).
- **C6 · `/moj-typ`**: cog użytkownika nie zyskuje strefy (formatter nie renderuje
  czasu); zyskuje tylko serwis ogłoszeń (C7).
- **C7 · Konstruktor coga użytkownika = `(service, announcements)`** — korekta
  stwierdzenia T5 „bez zmian" (wymuszone przełączeniem `/typ` na `prediction_reply`).

### Plan wykonania (3 spójne sesje, TDD wewnątrz, code-review na końcu)

Każde cięcie zostawia suite zielony i czystą granicę; `/clear` między sesjami.

1. **Sesja S1 — domena + reguły + aplikacja + prezentacja** (T1 + T2 + C5):
   stałe domeny, `select_active_match`, szew `active_match` z nosicielami, nowy moduł
   prezentacji z pełnym wyciągnięciem stringów, mechaniczna adaptacja handlerów
   (`/moj-typ`, `/wszystkie-typy`) i testów do nowych zwrotów serwisu.
2. **Sesja S2 — odpowiedzi + ogłoszenia** (T3 + T4 + C2/C3): nowy moduł odpowiedzi
   z pojazdem D na `/typ`, event-shaped interfejs serwisu ogłoszeń, `match_settled`,
   `prediction_reply`, konsolidacja acków admina, chunking do jednego domu.
3. **Sesja S3 — config + wiring + dokumentacja** (T5 + adapter): `BotConfig`,
   walidator, fail-fast, fabryka checka, scalary w publisherze, strefa przez coga,
   `.env.example`, AGENTS.md, domknięcie cienkich cogów.

### Inne notatki

- Gate jakości każdej sesji: `ruff check .` (E/F/I, line-length 100) + `pytest`
  (asyncio_mode=auto), oba zielone na granicy sesji.
- Teksty użytkownika po polsku, identyfikatory po angielsku; frozen dataclass-y z
  walidacją w `__post_init__`; datetimes zawsze tz-aware.
- Zgodność z terminologią glosariusza (`CONTEXT.md`) jest częścią review: nazwy
  identyfikatorów mają odzwierciedlać hasła („Aktywny mecz do typowania" →
  `active_match`/`ActiveMatch`).
