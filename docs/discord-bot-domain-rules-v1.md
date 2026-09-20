# Reguły domenowe — typer i oceny zawodników

## Status

- Wersja: 1.1
- Zakres: punktacja typowania, walidacja terminu meczu oraz definicja czasu gry zawodników
- Cel: jednoznaczna podstawa do implementacji i testów domenowych

## 1. Słownik pojęć

### Wynik regulaminowy

**Wynik regulaminowy** to wynik po zakończeniu podstawowego czasu gry:

```text
90 minut
+ czas doliczony do pierwszej połowy
+ czas doliczony do drugiej połowy
```

Dla potrzeb typera nie uwzględnia się:

- dogrywki;
- czasu doliczonego w dogrywce;
- serii rzutów karnych;
- rezultatu awansu w dwumeczu.

Przykład: po 90 minutach wraz z doliczonym czasem jest 1:1, a po dogrywce 2:1. Do rozliczenia typu obowiązuje wynik 1:1.

### Wynik typowany

Wynik oddany przez użytkownika, składający się z dwóch nieujemnych liczb całkowitych:

```text
bramki gospodarzy : bramki gości
```

Przykład: `4:1`.

### Rezultat

Rezultat jest klasyfikacją wyniku niezależną od liczby bramek:

```text
HOME_WIN — wygrana gospodarzy
DRAW     — remis
AWAY_WIN — wygrana gości
```

### Trafienie liczby bramek drużyny

Trafienie następuje, gdy użytkownik poprawnie wskazał liczbę bramek zdobytych przez gospodarzy albo gości.

Dla wyniku faktycznego `4:1`:

```text
Typ 4:0 → trafione gole gospodarzy
Typ 2:1 → trafione gole gości
Typ 4:4 → trafione gole gospodarzy
Typ 2:2 → brak trafionej liczby goli
```

## 2. Reguły punktacji

### Kolejność priorytetów

Punktacja zawsze stosuje pierwszą pasującą regułę:

1. Dokładny wynik.
2. Poprawny rezultat oraz trafiona liczba bramek co najmniej jednej drużyny.
3. Niepoprawny rezultat, ale trafiona liczba bramek co najmniej jednej drużyny.
4. Brak punktów.

### Reguła 1 — dokładny wynik

Jeśli obie liczby bramek w typie są zgodne z wynikiem regulaminowym, użytkownik otrzymuje maksymalną liczbę punktów.

```text
wynik: 4:1
typ:   4:1
```

### Reguła 2 — poprawny rezultat plus gole jednej drużyny

Jeżeli wynik nie jest dokładny, ale typ wskazuje prawidłowy rezultat i prawidłową liczbę bramek przynajmniej jednej drużyny, użytkownik otrzymuje punkty za rezultat oraz bonus za trafione gole.

```text
wynik: 4:1
typ:   4:0
→ poprawny rezultat: HOME_WIN
→ trafione gole gospodarzy: 4
```

```text
wynik: 4:1
typ:   2:1
→ poprawny rezultat: HOME_WIN
→ trafione gole gości: 1
```

### Reguła 3 — punkty pocieszenia

Jeżeli rezultat jest niepoprawny, ale poprawnie wskazano liczbę bramek co najmniej jednej drużyny, użytkownik otrzymuje wyłącznie punkty pocieszenia.

```text
wynik: 4:1
typ:   4:4
→ błędny rezultat: DRAW zamiast HOME_WIN
→ trafione gole gospodarzy: 4
```

### Reguła 4 — brak punktów

Jeżeli rezultat jest niepoprawny i nie trafiono liczby bramek żadnej drużyny, użytkownik nie otrzymuje punktów.

```text
wynik: 4:1
typ:   2:2
→ błędny rezultat
→ brak trafionej liczby goli
```

### Proponowana punktacja liczbowa

Poniższe wartości są proponowaną domyślną konfiguracją i mogą zostać później przeniesione do ustawień sezonu:

| Trafienie | Punkty |
|---|---:|
| Dokładny wynik | 5 |
| Poprawny rezultat | 2 |
| Bonus za trafioną liczbę goli jednej drużyny | 1 |
| Niepoprawny rezultat, ale trafione gole jednej drużyny | 1 |
| Brak trafienia | 0 |

W konsekwencji:

| Wynik | Typ | Rozliczenie | Punkty |
|---:|---:|---|---:|
| 4:1 | 4:1 | Dokładny wynik | 5 |
| 4:1 | 4:0 | Rezultat + gole gospodarzy | 3 |
| 4:1 | 2:1 | Rezultat + gole gości | 3 |
| 4:1 | 4:4 | Gole gospodarzy, błędny rezultat | 1 |
| 4:1 | 2:2 | Brak trafienia | 0 |

Trafienie liczby goli obu drużyn poza dokładnym wynikiem jest niemożliwe: poprawne wskazanie obu wartości zawsze oznacza dokładny wynik.

## 3. Algorytm punktacji

```python
from enum import StrEnum


class ResultType(StrEnum):
    HOME_WIN = "HOME_WIN"
    DRAW = "DRAW"
    AWAY_WIN = "AWAY_WIN"


def result_type(home: int, away: int) -> ResultType:
    if home > away:
        return ResultType.HOME_WIN
    if home < away:
        return ResultType.AWAY_WIN
    return ResultType.DRAW


def calculate_prediction_points(
    actual_home: int,
    actual_away: int,
    predicted_home: int,
    predicted_away: int,
) -> int:
    if (predicted_home, predicted_away) == (actual_home, actual_away):
        return 5

    correct_result = result_type(actual_home, actual_away) == result_type(
        predicted_home,
        predicted_away,
    )
    correct_one_goal_count = (
        actual_home == predicted_home
        or actual_away == predicted_away
    )

    if correct_result:
        return 2 + int(correct_one_goal_count)

    if correct_one_goal_count:
        return 1

    return 0
```

Implementacja produkcyjna powinna korzystać z obiektu konfiguracyjnego punktacji sezonu zamiast stałych `5`, `2` i `1`.

## 4. Walidacja terminu meczu (kickoff)

### Reguła — kickoff musi być w przyszłości

Przy dodawaniu meczu (`/admin-mecz-dodaj`) oraz przy zmianie terminu meczu
(`/admin-mecz-edytuj`) podany kickoff musi leżeć **ściśle w przyszłości**
względem bieżącego czasu:

```text
kickoff > now
```

Kickoff równy bieżącemu czasowi jest odrzucany.

Warunek jest sprawdzany przed zapisem meczu lub jego edycją przez funkcję domeny
`ensure_kickoff_in_future` wywoływaną z serwisu aplikacji.
Odrzucona operacja kończy się błędem domenowym; interfejs użytkownika wyświetla
oddzielne komunikaty dla każdej komendy:

```text
/admin-mecz-dodaj  → „Kickoff musi być w przyszłości."
/admin-mecz-edytuj → „Nowy kickoff musi być w przyszłości."
```

### Testy domenowe

```text
kickoff = now - 1 min   → odrzucone
kickoff = now           → odrzucone
kickoff = now + 1 min   → przyjęte
```

## 5. Przypadki wymagające późniejszej decyzji

Przed wdrożeniem rozliczania automatycznego trzeba zdefiniować zasady dla:

- meczu przełożonego;
- meczu odwołanego;
- meczu przerwanego;
- walkoweru;
- korekty wyniku przez dostawcę API;
- meczu pucharowego z dogrywką i rzutami karnymi;
- ręcznego ponownego rozliczenia przez administratora;
- końca sezonu przed zakończeniem wszystkich spotkań.

Domyślna bezpieczna zasada: bot nie rozlicza typu, jeśli nie ma potwierdzonego wyniku regulaminowego o odpowiedniej jakości danych.

## 6. Definicja czasu gry zawodnika

### Zakres czasu

Czas gry zawodnika oznacza czas od rozpoczęcia jego uczestnictwa w grze do zakończenia tego uczestnictwa.

Początek czasu gry:

- `0` dla zawodnika w wyjściowym składzie;
- absolutna minuta wejścia na boisko dla rezerwowego.

Koniec czasu gry:

- absolutna minuta zejścia z boiska dla zmienionego zawodnika;
- absolutna minuta końcowego gwizdka dla zawodnika, który pozostał na boisku.

### Czas wliczany do występu

Do `minutes_played` wlicza się pełny czas gry:

```text
podstawowy czas gry
+ doliczony czas pierwszej połowy
+ doliczony czas drugiej połowy
+ pierwsza połowa dogrywki
+ druga połowa dogrywki
+ doliczony czas obu połów dogrywki
```

Nie wlicza się serii rzutów karnych.

To rozróżnienie jest celowe:

- typer rozlicza wynik po podstawowym czasie gry;
- oceny zawodników uwzględniają pełny czas faktycznie rozegrany, także w dogrywce.

### Wzór

\[
minutes\_played = end\_minute - start\_minute
\]

gdzie `start_minute` i `end_minute` są absolutnymi minutami meczu.

### Minuty absolutne

Dane API mogą przedstawiać doliczony czas jako zapis `45+3` lub `90+6`. W logice domenowej należy przekształcać go do absolutnej minuty:

```text
45+3  → 48
90+6  → 96
105+2 → 107
120+1 → 121
```

Dzięki temu czas gry oblicza się prostym odejmowaniem.

### Konwencja zmiany

Dla zmiany w minucie `X`:

```text
zawodnik schodzący: end_minute = X
zawodnik wchodzący: start_minute = X
```

Nie dodajemy ani nie odejmujemy jednej minuty. Model traktuje czas jako ciągły, nie jako liczbę dyskretnych minut zegarowych.

## 7. Przykłady czasu gry

| Sytuacja | Początek | Koniec | Czas gry |
|---|---:|---:|---:|
| Wyjściowy skład, koniec w 90+5 | 0 | 95 | 95 min |
| Wejście w 72. minucie, koniec w 90+5 | 72 | 95 | 23 min |
| Wejście w 89. minucie, koniec w 90+6 | 89 | 96 | 7 min |
| Wejście w 105. minucie, koniec w 120+2 | 105 | 122 | 17 min |
| Wyjściowy skład, zejście w 63. minucie | 0 | 63 | 63 min |
| Wyjściowy skład, zejście w 45+2 | 0 | 47 | 47 min |

## 8. Kwalifikacja do ocen

Na obecnym etapie obowiązuje reguła:

```text
zawodnik kwalifikuje się do ocen, gdy minutes_played > 5
```

Konsekwencje:

```text
5 minut dokładnie  → brak kwalifikacji
6 minut            → kwalifikacja
```

Do doprecyzowania w kolejnej iteracji:

- okno czasowe wystawiania ocen;
- możliwość edycji oceny;
- zachowanie dla przerwanego meczu;
- zachowanie przy brakujących danych o zmianach;
- zachowanie przy czerwonej kartce;
- minimalna jakość danych konieczna do otwarcia ocen.

## Prezentacja listy typów

Komenda `/wszystkie-typy` zwraca prywatną listę wszystkich typów złożonych na
bieżący mecz (mecz z otwartym oknem typowania, ten sam co `/typ`). Lista jest
posortowana według własnego przewidywanego rezultatu każdego typu, a następnie
według liczby bramek:

### Kolejność grup

Grupy są prezentowane w stałej kolejności:

```text
1. Wygrana gospodarzy  — typ, w którym gole_gospodarzy > gole_goście
2. Remis               — typ, w którym gole_gospodarzy = gole_goście
3. Wygrana gości       — typ, w którym gole_goście > gole_gospodarzy
```

Kolejność grup wynika z wyniku typowanego (rezultat), nie z faktycznego wyniku
meczu — komenda działa przed rozliczeniem i porządkuje typy tak, jak je
przewidział użytkownik.

### Sortowanie wewnątrz grupy

W obrębie tej samej grupy typy są sortowane malejąco po:

1. różnicy bramek na korzyść zwycięzcy (`|gospodarze - goście|`);
2. liczbie goli strzelonych przez zwycięzcę;
3. liczbie goli strzelonych przez przegranego.

Dla remisu jedynym kryterium jest suma goli w typie (`gospodarze + goście`).

### Łamanie pełnego remisu kryteriów

Jeśli dwa typy mają identyczny wynik i identyczne wartości wszystkich kryteriów,
porządek wyznacza czas złożenia typu (`submitted_at` rosnąco) — najpierw
złożony typ pojawia się wyżej.

### Przykład

Dla typów `3:0`, `4:2`, `2:0`, `2:2`, `1:1`, `0:2` lista wygląda tak:

```text
Wygrana gospodarzy
3:0   (różnica 3)
4:2   (różnica 2, gole zwycięzcy 4)
2:0   (różnica 2, gole zwycięzcy 2)

Remis
2:2   (4 gole)
1:1   (2 gole)

Wygrana gości
0:2   (różnica 2)
```

## 8. Testy domenowe

Przed integracją z Discordem i SQLite należy pokryć testami przynajmniej:

### Punktacja

```text
4:1 vs 4:1 → 5
4:1 vs 4:0 → 3
4:1 vs 2:1 → 3
4:1 vs 4:4 → 1
4:1 vs 2:2 → 0
0:0 vs 0:1 → 1 (trafione gole gospodarzy, zły rezultat)
0:0 vs 1:0 → 1 (trafione gole gości, zły rezultat)
2:2 vs 1:2 → 1 (trafione gole gości, niepoprawny rezultat)
```

### Czas gry

```text
start 0, end 95    → 95
start 72, end 95   → 23
start 89, end 96   → 7
start 105, end 122 → 17
start 0, end 63    → 63
```

### Kwalifikacja

```text
5 minut → false
6 minut → true
95 minut → true
```

### Sortowanie listy typów

```text
typy: 0:2, 1:1, 3:0, 4:2, 2:2, 2:0
→ 3:0, 4:2, 2:0, 2:2, 1:1, 0:2
  (grupa gospodarzy: różnica goli, gole zwycięzcy;
   remis: suma goli; goście: różnica goli)

identyczne typy 2:0 złożone o 18:00 i 18:01
→ typ z 18:00 wyżej (kolejność złożenia)
```
