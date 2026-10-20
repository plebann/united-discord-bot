Status: ready-for-agent

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

## Comments
