# Specyfikacja — `/admin-mecz-usun`

Status: ready-for-agent
Data: 2026-02-14
Zakres: usuwanie nierozliczonego meczu przez komendę administracyjną

## Problem Statement

Administrator nie potrafi skorygować błędnie dodanego meczu.
`/admin-mecz-edytuj` zmienia wyłącznie kickoff — nazwy drużyn i rozgrywek
nie da się edytować, a jedynym wyjściem jest ręczne usuwanie wiersza w bazie
SQLite (co reguły domenowe wprost opisują jako ścieżkę naprawy utkniętych
stanów). Co gorsza, źle dodany nierozliczony mecz **blokuje dodanie
poprawnego**, bo obowiązuje reguła „co najwyżej jeden nierozliczony mecz".
Z perspektywy admina: dodałem zły mecz i nie mam komendy, która usunie go
czysto.

## Solution

Nowa komenda administracyjna `/admin-mecz-usun id:<int>` usuwa nierozliczony
mecz po jego `#id` (takim, jaki widnieje w `/admin-mecze-lista`), kaskadowo
usuwając jego nierozliczone typy oraz wiersze ogłoszeń, atomowo, z prywatnym
potwierdzeniem. Usuwane są wyłącznie mecze nierozliczone (`SCHEDULED`).

## User Stories

1. As an admin, I want to delete a mis-added match so I can re-add it
   correctly without manual database edits.
2. As an admin, I want to specify the match by its `#id` from
   `/admin-mecze-lista`, so I target exactly the intended match.
3. As an admin, I want deletion to succeed for a scheduled match whose
   kickoff has already passed but which is still unsettled, so I can clean up
   a started-but-not-yet-settled fixture.
4. As an admin, I want settled (finished) matches protected from deletion, so
   historical results and awarded points cannot be erased.
5. As an admin, I want a clear error when the given id does not exist in my
   guild, so I know I mistyped rather than silently doing nothing.
6. As an admin, I want a clear error when trying to delete a finished match,
   naming the restriction.
7. As an admin, I want a private ephemeral confirmation after a successful
   deletion, so I get feedback without broadcasting housekeeping to the
   channel.
8. As a member, I want deletion restricted to admins (Manage Guild /
   Administrator), so arbitrary users cannot remove fixtures.
9. As a member, I want deletion usable only on the configured channel, so the
   command cannot be abused elsewhere.
10. As an admin, I want the match's unscored predictions removed when I delete
    the match, so no orphaned prediction rows linger referencing a gone match.
11. As an admin, I want the match's announcement records removed with it, so
    re-adding/re-configuring can re-publish announcements correctly.
12. As an admin, I want deletion to be atomic — either the match and all its
    dependent rows are removed or none are — so I never end up with orphaned
    rows.
13. As an admin, I want `/admin-mecze-lista` to reflect the deletion
    immediately, so I can verify.
14. As a developer, I want deletability governed by a single domain rule (only
    unresolved), so the business rule is explicit, tested and documented like
    the other operational rules.
15. As a developer, I want `delete_match` to live in the application service
    orchestrating the repositories, so Discord types stay out of the
    domain/application layer.
16. As a developer, I want `delete_match` to not require a `now` parameter,
    because deletability is status-only and the API should be honest about what
    it depends on.

## Implementation Decisions

- **Nowa reguła operacyjna `ensure_deletable(match)`** w istniejącym module
  reguł: rzutuje `DomainError`, gdy `match.status != SCHEDULED`; komunikat
  `Nie można usunąć rozliczonego meczu.` Dołącza do trzech obecnych reguł
  operacyjnych — to dokładnie „następna reguła", której oczekiwał opis w
  AGENTS.md; ponieważ moduł reguł już istnieje, dodajemy go tam (bez
  restrykturyzacji).
- **Nowy use case `TyperService.delete_match(guild_id, match_id)`**: pobiera
  mecz po `(id, guild_id)`; rzutuje `LookupError` z
  `Nie znaleziono meczu o identyfikatorze #<id>.`, gdy nie istnieje; wywołuje
  `ensure_deletable`; wykonuje atomową kaskadę; zwraca usunięty `Match` dla
  spójności logowania z pozostałymi komendami. Bez parametru `now`
  (decyzja zależna wyłącznie od statusu). Usunięcie celowo **nie** jest modelem
  jako metoda wartości `Match` (brak odpowiednika `with_*`/`finish`) — usuwa
  wiersz, zamiast transformować wartość.
- **Atomowa kaskada**: wiersze zależne (typy meczu, wiersze ogłoszeń meczu) i
  wiersz meczu są usuwane w jednej transakcji/sesji, więc żaden częściowy stan
  ani osierocone wiersze nie mogą powstać, nawet jeśli krok zawiedzie.
  Niezmiennik „usunięty mecz nie zostawia sierot" trzymany jest w jednym
  miejscu — w usuwaniu repozytorium meczów — dzięki czemu metoda aplikacji
  pozostaje cienka. Trade-off: repozytorium meczów dotyka dwóch tabel potomnych,
  bo te mają FK do matches; alternatywa (trzy osobne usuwania per tabela w
  osobnych sesjach) złamałaby atomowość i została odrzucona.
- **Zachowanie kluczy obcych**: schema utrzymuje `foreign_keys=ON`; kaskada
  wykonana jest jawnie wewnątrz transakcji (wiersze zależne usuwane razem z
  rodzicem), a nie opiera się na `ON DELETE CASCADE` w bazie, co trzyma politykę
  jawną w kodzie. **Brak migracji Alembic** — kształt tabel się nie zmienia.
- **Nowa komenda slash** w cogu administracyjnym o nazwie `/admin-mecz-usun`
  z pojedynczym argumentem całkowitym `id`. Guardy identyczne jak przy
  pozostałych komendach administracyjnych: check kanalu skonfigurowanego oraz
  wymaganie Manage Guild / Administrator. Odpowiedź wyłącznie prywatna
  (ephemeral) — bez publicznego ogłoszenia w kanale. Komunikaty: sukces
  `Usunięto mecz #<id>.`; brak → tekst LookupError; rozliczony → tekst
  DomainError. Nazwa argumentu odbija `#id` pokazywany w liście.
- **Dokumentacja**: doc reguł domenowych zyskuje sekcję „Usunięcie meczu"
  (usuwalność = tylko nierozliczone, niezależnie od kickoffu; kaskada na typy i
  ogłoszenia; komunikaty per błąd) z bumpem wersji. `AGENTS.md` korygowany w
  dwóch miejscach: dodajemy moduł reguł do „Where things live"; przepisujemy
  notatkę „Business rule placement" tak, aby odzwierciedliła, że moduł reguł
  jest teraz ustalonym domem reguł operacyjnych (oczekiwana restrykturyzacja już
  nastąpiła), usuwając stary framing „restructure first / don't tidy
  prematurely". `CONTEXT.md` zostaje nienaruszony (nie rozstrzygnięto tu nowego
  mglistego terminu); opcjonalny jednowierszowy wpis „Usunięcie meczu" jest
  dostępny, jeśli trzeba.

## Testing Decisions

- **Dobry test** = wyłącznie zachowanie zewnętrzne: funkcja napędzana przez
  serwis aplikacji (`TyperService`) i asercje na widocznych skutkach — mecz
  znika z `list_matches`, jego wiersze typów znikają, jego wiersze ogłoszeń
  znikają, a rzucany jest właściwy typ wyjątku z dokładnym polskim komunikatem.
  Brak asercji na kolejności wywołań wewnętrznych ani na SQL.
- **Jeden szew**, zgodny ze wszystkimi istniejącymi testami reguł
  operacyjnych: `TyperService` nad prawdziwymi repozytoriami na temp-SQLite
  (utrwalony wzór fixture `service` używany przez testy walidacji dodawania/
  edycji kickoff). Żaden nowy szew produkcyjny nie jest wprowadzany.
  Potwierdzone z użytkownikiem.
- Fixture testowy rozszerzamy względem tego prior artu tak, by dodatkowo
  odsłaniało repozytoria typów i ogłoszeń (ta sama fabryka sesji) wyłącznie do
  asercji stanu kaskady (usuniete wiersze zależne). Powierzchnia produkcyjna
  pod testem pozostaje pojedynczym serwisem aplikacji.
- **Pokrycie**: usuwa nierozliczony mecz i usuwa jego zależne typy/ogłoszenia;
  ponowne usunięcie tego samego id rzutuje not-found; usunięcie rozliczonego
  meczu odrzucone z dokładnym komunikatem domenowym; usunięcie nieznanego id w
  gildii rzutuje komunikat not-found; usunięcie działa dla rozpoczętego, ale
  nierozliczonego meczu (kickoff minął, status SCHEDULED); ponowne dodanie po
  usunięciu jest dozwolone (reguła pojedynczego nierozliczonego znów
  spełniona).
- **Prior art**: testy walidacji kickoff i pojedynczego nierozliczonego przy
  dodawaniu (ten sam kształt fixture; tu czas jest irrelewantny, więc bez
  zapiętego `now`).

## Out of Scope

- Usuwanie rozliczonych meczów (celowo wykluczone).
- Publiczne ogłoszenie w kanale o usunięciu (wyłącznie prywatne potwierdzenie).
- Soft-delete / archiwizacja zamiast twardego usunięcia; brak wartości statusu
  „deleted".
- Jakakolwiek zmiana reguły pojedynczego nierozliczonego meczu ani zachowania
  punktacji / okna typowania.
- Automatyczne rozliczanie / zarządzanie meczami przez API (niezależna przyszła
  robota).
- Okna potwierdzające poza prywatną odpowiedzią komendy slash.

## Further Notes

- Komenda zamienia udokumentowaną ścieżkę naprawy ręcznej w bazie („administrator
  ręcznie usuwa w bazie SQLite") na pierwszorzędną, strzeżoną operację; dzięki
  temu odblokowuje też odzyskiwanie ze stanów legacy z kilkoma nierozliczonymi
  meczami.
- Ponieważ usunięcie usuwa niepunktowane typy, admin usuwający rozpoczęty, ale
  nierozliczony mecz wyciera nietypowane jeszcze typy członków dla tego meczu; to
  zamierzone i pasuje do workflow (usuń → dodaj poprawny mecz).
- Nazwa komendy po polsku zgodnie z istniejącą rodziną administracyjną
  (`admin-mecz-dodaj/edytuj/wynik/mecze-lista`); identyfikatory w kodzie
  pozostają angielskie.
