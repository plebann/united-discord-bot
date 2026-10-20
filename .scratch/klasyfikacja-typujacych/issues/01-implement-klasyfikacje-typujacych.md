Status: resolved

# Implementacja Klasyfikacji typujących

Spec: [../spec.md](../spec.md)

## Zakres

Wdrożyć pionowy przekrój `/klasyfikacja`: agregację zachowanych typów w
gildii, przypadek użycia, prywatną komendę użytkownika i formatowanie
Klasyfikacji typujących zgodne ze specyfikacją.

## Kryteria akceptacji

- Typujący są uwzględniani po każdym zachowanym typie, również
  nierozliczonym.
- Punkty, Dokładne trafienia i liczba typów są wyliczane oraz sortowane
  zgodnie ze specyfikacją.
- Pełne remisy mają stabilny porządek nazwą i ID, ale współdzielą pozycję w
  numeracji zawodniczej.
- Komenda jest prywatna, dostępna bez uprawnienia administratora, używa
  istniejącego resolvera nazw i dzieli długie odpowiedzi po wierszach.
- Nowy test kontraktowy pokrywa obserwowalne zachowanie komendy.

## Zależności

Brak.

## Answer

Zaimplementowano i scalono do gałęzi integracyjnej `feature/klasyfikacja-typujacych`
w commicie `9bff4b6899b2007fb3c8bc6ce8e0943147c12798`. Weryfikacja gałęzi:
89 testów, `ruff check .` i kontrola formatu zmienionych plików zakończone
powodzeniem.

## Comments
