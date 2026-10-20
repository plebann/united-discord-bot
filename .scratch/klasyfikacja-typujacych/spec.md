Status: ready-for-agent

# Klasyfikacja typujących

## Problem Statement

Typujący nie mają obecnie jednego miejsca, w którym mogą sprawdzić swoją
pozycję oraz wyniki względem innych osób w danej gildii. Punkty są rozliczane
po meczu, lecz pełna historia osiągnięć — w tym Dokładne trafienia i liczba
typów — pozostaje niewidoczna.

## Solution

Bot udostępnia komendę `/klasyfikacja` dla każdego użytkownika na
skonfigurowanym kanale. Komenda prywatnie wyświetla pełną Klasyfikację
typujących bieżącej gildii.

Każdy Typujący z co najmniej jednym zachowanym typem jest uwzględniony.
Kolejność wynika kolejno z sumy punktów malejąco, liczby Dokładnych trafień
malejąco i liczby typów rosnąco. Pełny remis tych trzech wartości jest
prezentowany według nazwy typującego bez uwzględniania wielkości liter, a potem
identyfikatora użytkownika; te dwa kryteria zapewniają stabilny porządek, lecz
nie zmieniają współdzielonej pozycji. Pozycje stosują numerację zawodniczą,
np. `1., 1., 3.`.

Każdy wiersz zawiera pozycję, nazwę, punkty, Dokładne trafienia i liczbę
typów. Gdy nie istnieje żaden zachowany typ, bot odpowiada `Nikt jeszcze nie
typował.`. Pełna odpowiedź jest dzielona na prywatne wiadomości między
wierszami, bez ograniczania jej do Top N.

## User Stories

1. Jako Typujący chcę wywołać `/klasyfikacja`, aby prywatnie zobaczyć pełną Klasyfikację typujących mojej gildii.
2. Jako Typujący chcę widzieć siebie po pierwszym zapisanym typie, aby udział w klasyfikacji nie zależał od tego, czy mecz został już rozliczony.
3. Jako Typujący chcę widzieć sumę punktów wyłącznie za rozliczone mecze, aby nierozliczony typ nie dawał mi przedwcześnie punktów.
4. Jako Typujący chcę widzieć liczbę Dokładnych trafień, aby odróżnić precyzyjne wyniki od pozostałych punktowanych typów.
5. Jako Typujący chcę, aby liczba typów obejmowała także typy na nierozliczone mecze, aby odzwierciedlała wszystkie moje zachowane typy.
6. Jako Typujący chcę, aby Klasyfikacja typujących była sortowana malejąco po punktach, aby wyższy dorobek dawał wyższą pozycję.
7. Jako Typujący z taką samą liczbą punktów jak inna osoba chcę, aby większa liczba Dokładnych trafień dawała mi wyższą pozycję.
8. Jako Typujący z takim samym dorobkiem i liczbą Dokładnych trafień chcę, aby mniejsza liczba typów dawała mi wyższą pozycję.
9. Jako Typujący w pełnym remisie chcę współdzielić pozycję z osobą o identycznych trzech statystykach, aby wynik nie był arbitralnie rozstrzygany nazwą.
10. Jako Typujący chcę widzieć numerację `1., 1., 3.` przy współdzielonej pozycji, aby numer wskazywał faktyczne miejsce w Klasyfikacji typujących.
11. Jako Typujący chcę stabilnego porządku pełnego remisu po nazwie, a następnie identyfikatorze użytkownika, aby kolejne wywołania komendy nie zmieniały kolejności bez powodu.
12. Jako Typujący chcę widzieć nazwy ustalane tak samo jak w `/wszystkie-typy`, aby listy bota używały spójnej tożsamości użytkownika.
13. Jako Typujący chcę, aby osoba, która opuściła gildię, nadal zachowała historię w klasyfikacji, aby opuszczenie serwera nie przepisywało wyników.
14. Jako Typujący chcę zastępczej nazwy `Użytkownik <id>` dla osoby bez dostępnej nazwy, aby żaden zachowany typ nie znikał z Klasyfikacji typujących.
15. Jako Typujący chcę, aby Klasyfikacja typujących była widoczna wyłącznie dla mnie, aby wynik komendy nie publikował się automatycznie na kanale.
16. Jako Typujący chcę otrzymać jasny komunikat przy braku typów w gildii, aby pusta odpowiedź nie wyglądała jak błąd.
17. Jako Typujący chcę otrzymać całą długą Klasyfikację typujących w kolejnych wiadomościach, aby żadna osoba nie została pominięta przez limit Discorda.
18. Jako członek wielu gildii chcę widzieć tylko typujących z bieżącej gildii, aby dane i pozycje nie mieszały się między serwerami.
19. Jako administrator chcę, aby usunięty mecz i jego usunięte typy nie wpływały na Klasyfikację typujących, aby prezentowała wyłącznie zachowaną historię.
20. Jako opiekun bota chcę, aby zwykły Typujący mógł użyć komendy bez uprawnień administratora, aby klasyfikacja była dostępna całej społeczności.

## Implementation Decisions

- Dodać odczytowy przypadek użycia Klasyfikacji typujących w warstwie
  aplikacyjnej oraz zwracany przez niego niemutowalny model statystyk
  pojedynczego Typującego.
- Rozszerzyć adapter trwałości o agregację per użytkownik ograniczoną do jednej
  gildii. Agregacja obejmuje wszystkie zachowane typy dla liczby typów, tylko
  rozliczone typy dla punktów i tylko rozliczone typy zgodne z wynikiem
  regulaminowym dla Dokładnych trafień.
- Dokładne trafienie ustalać przez porównanie wyniku typowanego z wynikiem
  regulaminowym meczu, a nie przez porównanie z konkretną wartością punktów.
  Dzięki temu znaczenie pojęcia nie zależy od przyszłej konfiguracji
  punktacji.
- Nie zmieniać schematu bazy ani nie dodawać migracji: wszystkie dane potrzebne
  do Klasyfikacji typujących istnieją w zachowanych meczach i typach.
- Dodać `/klasyfikacja` do istniejącego cog'a komend użytkownika i zachować
  istniejące ograniczenie do skonfigurowanego kanału, bez bramki
  administratora.
- Handler ma odroczyć odpowiedź jako prywatną przed operacjami I/O, następnie
  pobrać statystyki, rozwiązać nazwy przez istniejący resolver używany przez
  `/wszystkie-typy`, zastosować końcowe kryteria porządku i wyprowadzić
  pozycje współdzielone.
- Wykorzystać istniejący mechanizm dzielenia odpowiedzi na granicach wierszy.
  Każdy wiersz ma format `pozycja. nazwa — punkty pkt · dokładne trafienia ·
  typy`; tekst pozostaje po polsku.
- Utrzymać podział odpowiedzialności: trwałość zwraca statystyki, przypadek
  użycia je udostępnia, a adapter Discorda rozwiązuje nazwy oraz formatuje
  prywatną odpowiedź. Żaden typ Discorda nie trafia do warstwy aplikacyjnej
  ani domenowej.
- Reguły domenowe i kanoniczna terminologia są już zapisane jako
  „Klasyfikacja typujących”, „Typujący” i „Dokładne trafienie”; implementacja
  używa tych nazw zamiast synonimów.

## Testing Decisions

- Dobry test sprawdza obserwowalny rezultat wywołania komendy: prywatne
  wiadomości, ich kolejność i treść — nie strukturę zapytania, prywatne metody
  ani liczbę wywołań adapterów.
- Głównym i jedynym nowym punktem testowym jest kontraktowy test
  `UserTyperCog` z prawdziwym `TyperService`, tymczasową SQLite, fałszywą
  interakcją Discorda i kontrolowanym resolverem nazw.
- Test zasiewa rozliczone oraz nierozliczone typy wielu użytkowników i
  weryfikuje: izolację gildii, sumę punktów, Dokładne trafienia, liczbę typów,
  kolejność trzech kryteriów, pełny remis po nazwie i identyfikatorze,
  numerację `1., 1., 3.`, nazwy zastępcze, pustą Klasyfikację oraz podział
  długiej odpowiedzi.
- Test zachowuje istniejący wzorzec testów integracji z tymczasową SQLite oraz
  lekkimi fałszywymi obiektami Discorda, używany dla zachowań komend i
  wieloczęściowych wiadomości.

## Out of Scope

- Sezony, reset klasyfikacji, filtry dat, rozgrywek lub statusu meczu.
- Ograniczanie listy do Top N, paginacja interaktywna i eksport danych.
- Publiczne ogłoszenia klasyfikacji, harmonogram automatycznych publikacji oraz
  uprawnienia administratora dla komendy.
- Zmiana reguł punktacji, ponowne rozliczanie meczów lub modyfikacja danych
  historycznych.
- Dodanie nowych tabel, kolumn, migracji lub integracji z zewnętrznym API.

## Further Notes

Specyfikacja wykorzystuje lokalny tracker zgodnie z konfiguracją repozytorium.
Usunięcie meczu już usuwa zależne typy, dlatego Klasyfikacja typujących
automatycznie pozostaje zgodna z zachowaną historią. Nazwa typującego może się
zmieniać wraz z nazwą na serwerze; w pełnym remisie wpływa to wyłącznie na
stabilną kolejność prezentacji, nie na współdzieloną pozycję.
