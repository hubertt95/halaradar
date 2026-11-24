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
**Streamlit Cloud:** share.streamlit.io → to repozytorium → `app.py` → Deploy.
Dane odświeżają się same, bez ręcznego wgrywania:
- przy pierwszym otwarciu danego dnia (po 5:00) serwer pobiera świeży plik z GUNB,
- gdy GUNB nie odpowiada, używa kopii dziennej z gałęzi `data`, którą co noc tworzy GitHub Action `.github/workflows/gunb-daily.yml`.

Parametry adresu: `?region=slaskie`, `?dni=730`, `?odswiez=1` (wymuszenie pobrania).

**GitHub Pages / lokalnie:** `index.html` sam pobiera kopię dzienną z gałęzi `data` (gdy ta w przeglądarce ma ponad 24 h).
Ręczny import ZIP z https://wyszukiwarka.gunb.gov.pl/pobranie.html (**Dane / Import**) jest potrzebny tylko dla innych województw lub okresów.

**Kopia dzienna — pierwsze uruchomienie:** zakładka **Actions** → „Dane GUNB (codziennie)” → **Run workflow**
(można podać kilka województw, np. `mazowieckie,lodzkie`).

**Loader z konsoli:** `python gunb_loader.py --regions mazowieckie --days 365 --out-dir out`

## Jak to działa
1. Plik GUNB (ZIP, CSV z separatorem `#`) jest czytany strumieniowo; kolumny są rozpoznawane automatycznie (z podglądem i ręczną korektą w oknie importu).
2. Smart Match przyznaje 0–100 pkt (nazwa, kategoria, kubatura, kary za domy/bloki/sieci/drogi).
3. Działki są lokalizowane w ULDK GUGiK po pełnym identyfikatorze (`jednostka.obręb.numer`); stamtąd pochodzą też nazwy powiatów i gmin. Wyniki są zapamiętywane w przeglądarce.
4. Przyciski „Pokaż w GUNB” otwierają gotowe wyszukiwanie w wyszukiwarka.gunb.gov.pl (dla sprawy: działka + obręb + data; dla widoku: organ, okres, kategoria, rodzaj robót). GUNB poprosi wtedy o kod z obrazka.
5. Leady, etapy CRM i notatki zapisują się lokalnie w przeglądarce (localStorage); ostatni import — w IndexedDB.
