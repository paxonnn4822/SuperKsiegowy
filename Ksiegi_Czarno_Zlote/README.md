# Księgi Czarno-Złote

Lokalna aplikacja desktopowa do wprowadzania dekretów dwustronnych i podstawowego przeglądu obrotów/sald. Interfejs Tkinter, dane przechowywane lokalnie w SQLite. Zawiera osobne karty weryfikacji Deloitte i PwC: użytkownik wprowadza NIP właściwej osoby prawnej, a aplikacja pyta oficjalny wykaz VAT Ministerstwa Finansów. KRS i REGON otwierają oficjalne wyszukiwarki w przeglądarce.

## Uruchomienie w Windows

1. Zainstaluj Python 3.12 (z opcją dodania do PATH).
2. Uruchom `build_windows.bat`.
3. Plik `dist/Ksiegi_CzarnoZlote.exe` będzie gotowy do użycia. Aplikacja przechowuje bazę w `%APPDATA%\\KsiegiCzarnoZlote`.

Możesz też pobrać EXE z artefaktu GitHub Actions po wypchnięciu repozytorium i uruchomieniu workflow `Windows EXE`.

## Testy

Uruchom `python -m unittest discover -s tests -v`. Testy sprawdzają walidację dekretów, sumy obrotów, filtr okresu RZiS, sumę kontrolną NIP oraz obsługę odpowiedzi API (mock, bez sieci).

## Ważne ograniczenia

To prototyp pomocniczy, a nie certyfikowany program finansowo-księgowy. Przykładowy plan kont i raporty należy dostosować do polityki rachunkowości, zakresu działalności i aktualnych przepisów. Program nie generuje JPK_KR_PD, JPK_V7, e-sprawozdań ani deklaracji, nie wykonuje automatycznych zamknięć okresów i nie zastępuje kontroli księgowego/audytora. Sprawdzenie VAT nie stanowi pełnego due diligence ani potwierdzenia uprawnień do reprezentacji. Dane należy chronić i regularnie archiwizować.
