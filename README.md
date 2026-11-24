# HalaRadar — wnioski o pozwolenie na budowę hal (GUNB RWDZ)

Mapa i tabela wniosków o pozwolenie na budowę obiektów kubaturowych (hale magazynowe, produkcyjne, usługowe) z rejestru RWDZ prowadzonego przez GUNB.

## Pliki
| Plik | Rola |
|---|---|
| `index.html` | cała aplikacja (mapa Leaflet, filtry, CRM, import ZIP/CSV z GUNB, ULDK) |
| `gunb_loader.py` | pobiera plik województwa z GUNB i wstępnie go filtruje (bez zależności) |
| `app.py` | uruchamia całość na Streamlit Community Cloud i wstrzykuje dane do `index.html` |
| `requirements.txt` | `streamlit` |

## Uruchomienie
**Streamlit Cloud:** wrzuć wszystkie pliki do repozytorium → share.streamlit.io → `app.py` → Deploy.
Dane z GUNB pobierają się same (cache 6 h). Parametry adresu: `?region=slaskie&dni=730`.

**GitHub Pages / lokalnie:** otwórz `index.html`, kliknij **Dane / Import** i upuść ZIP województwa z
https://wyszukiwarka.gunb.gov.pl/pobranie.html (bez rozpakowywania).

**Test loadera z konsoli:** `python gunb_loader.py mazowieckie 365 > dane.json`

## Jak to działa
1. Plik GUNB (ZIP, CSV z separatorem `#`) jest czytany strumieniowo; kolumny są rozpoznawane automatycznie (z podglądem i ręczną korektą w oknie importu).
2. Smart Match przyznaje 0–100 pkt (nazwa, kategoria, kubatura, kary za domy/bloki/sieci/drogi).
3. Działki są lokalizowane w ULDK GUGiK po pełnym identyfikatorze (`jednostka.obręb.numer`); stamtąd pochodzą też nazwy powiatów i gmin. Wyniki są zapamiętywane w przeglądarce.
4. Przyciski „Pokaż w GUNB” otwierają gotowe wyszukiwanie w wyszukiwarka.gunb.gov.pl (dla sprawy: działka + obręb + data; dla widoku: organ, okres, kategoria, rodzaj robót). GUNB poprosi wtedy o kod z obrazka.
5. Leady, etapy CRM i notatki zapisują się lokalnie w przeglądarce (localStorage); ostatni import — w IndexedDB.
