"""
gunb_loader.py — pobieranie i wstępne filtrowanie danych RWDZ (GUNB) dla HalaRadar.

Źródło: https://wyszukiwarka.gunb.gov.pl/pobranie.html
  - jeden plik ZIP na województwo (wnioski i decyzje o pozwoleniu na budowę od 2016 r.),
  - aktualizacja codzienna w nocy, kodowanie UTF-8, separator '#' (dla pewności
    separator jest wykrywany automatycznie: '#', ';', tabulator, ',' lub '|').

Moduł nie zależy od Streamlit, więc można go testować i uruchamiać samodzielnie:
    python gunb_loader.py --regions mazowieckie,slaskie --days 365 --out-dir out
(tak robi codzienny GitHub Action: zapisuje out/<region>.json.gz na gałąź „data”).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import io
import os
import json
import re
import sys
import urllib.request
import zipfile

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Warsaw")
except Exception:  # brak bazy stref czasowych
    _TZ = None

GUNB_URL = "https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_{slug}.zip"

REGIONS = {
    "dolnoslaskie": "dolnośląskie",
    "kujawsko-pomorskie": "kujawsko-pomorskie",
    "lubelskie": "lubelskie",
    "lubuskie": "lubuskie",
    "lodzkie": "łódzkie",
    "mazowieckie": "mazowieckie",
    "malopolskie": "małopolskie",
    "opolskie": "opolskie",
    "podkarpackie": "podkarpackie",
    "podlaskie": "podlaskie",
    "pomorskie": "pomorskie",
    "slaskie": "śląskie",
    "swietokrzyskie": "świętokrzyskie",
    "warminsko-mazurskie": "warmińsko-mazurskie",
    "wielkopolskie": "wielkopolskie",
    "zachodniopomorskie": "zachodniopomorskie",
}

# Kanoniczne pola (ta sama lista i kolejność co w index.html → HR_CORE.CANON_FIELDS)
CANON_FIELDS = [
    "key", "nr_urzad", "data_wplywu", "data_decyzji", "typ", "organ", "woj", "powiat",
    "gmina", "terc", "miejscowosc", "ulica", "nr_domu", "kategoria", "nazwa", "rodzaj",
    "kubatura", "jednostka", "obreb", "dzialka", "arkusz", "inwestor", "stan",
    "cel", "projektant", "projektant_imie", "nr_decyzji",
]

# (pole, wzorce w kolejności preferencji, wykluczenia) — nagłówki po normalizacji
COLUMN_RULES = [
    ("key", ["numer_gunb", "numer_ewidencyjny_system", "id_wniosku", "identyfikator"], []),
    ("nr_decyzji", ["numer_decyzji_urzedu", "numer_decyzji", "nr_decyzji"], []),
    ("nr_urzad", ["numer_urzad", "numer_ewidencyjny_urzad", "numer_ewidencyjny", "znak_sprawy", "nr_sprawy", "numer_sprawy", "znak"], ["system", "decyz", "gunb", "uprawn"]),
    ("cel", ["nazwa_zamierzenia_bud", "rodzaj_zamierzenia_bud", "cel_inwestycji"], []),
    ("data_decyzji", ["data_wydania_decyzji", "data_wydania", "data_decyzji"], []),
    ("data_wplywu", ["data_wplywu_wniosku_do_urzedu", "data_wplywu", "data_zlozenia", "data_wniosku", "data_wplyw"], []),
    ("typ", ["typ_dokumentu", "rodzaj_dokumentu", "typ", "rejestr", "dokument"], ["inwest", "obiekt", "zamierz"]),
    ("organ", ["nazwa_organu", "organ"], ["adres"]),
    ("woj", ["wojewodztwo"], []),
    ("powiat", ["powiat"], []),
    ("gmina", ["gmina"], []),
    ("terc", ["terc", "teryt"], ["dzialk"]),
    ("miejscowosc", ["miasto", "miejscowosc"], []),
    ("ulica", ["ulica"], ["dalej"]),
    ("nr_domu", ["nr_domu", "numer_domu", "nr_budynku"], []),
    ("kategoria", ["kategoria"], []),
    ("nazwa", ["nazwa_zam_budowlanego", "nazwa_zam", "nazwa_zamierzenia", "zamierzenie", "nazwa_inwestycji"], ["organ", "inwestor"]),
    ("rodzaj", ["rodzaj_zam_budowlanego", "rodzaj_zam", "rodzaj_inwestycji", "rodzaj_zamierzenia", "rodzaj_robot"], []),
    ("kubatura", ["kubatura"], []),
    ("jednostka", ["jednosta_numer_ew", "jednostka_numer_ew", "jednostki_numer", "jednostka_numer", "jednostka_ewid", "jednosta", "jednostki", "jednostka"], ["nazwa", "stara"]),
    ("obreb", ["obreb_numer", "numer_obrebu", "obreb"], ["nazwa", "stara"]),
    ("dzialka", ["numer_dzialki", "nr_dzialki", "dzialki", "dzialka"], ["arkusz", "stara"]),
    ("arkusz", ["arkusz"], []),
    ("inwestor", ["nazwa_inwestor", "nazwa_inwestora", "inwestor", "wnioskodawca"], []),
    ("projektant", ["projektant_nazwisko", "projektant"], ["imie", "uprawn"]),
    ("projektant_imie", ["projektant_imie"], []),
    ("stan", ["stan_prawny", "stan_sprawy", "stan", "status"], ["budow", "obiekt"]),
]

_PL = str.maketrans("ąćęłńóśźż", "acelnoszz")


def norm_header(h: str) -> str:
    h = (h or "").replace("\ufeff", "").strip().strip('"').lower().translate(_PL)
    return re.sub(r"[\s\-./]+", "_", h)


def map_columns(headers: list[str]) -> dict[str, int]:
    norm = [norm_header(h) for h in headers]
    used: set[int] = set()
    mapping: dict[str, int] = {}
    for field, pats, excl in COLUMN_RULES:
        idx = -1
        for mode in ("eq", "inc"):
            for p in pats:
                for i, h in enumerate(norm):
                    if i in used:
                        continue
                    ok = (h == p) if mode == "eq" else (p in h)
                    if ok and not any(e in h for e in excl):
                        idx = i
                        break
                if idx != -1:
                    break
            if idx != -1:
                break
        if field == "data_wplywu" and idx == -1:
            for i, h in enumerate(norm):
                if i not in used and "data" in h and not re.search(r"decyz|wydan|modyf|aktualiz", h):
                    idx = i
                    break
        if field == "nazwa" and idx == -1:
            for i, h in enumerate(norm):
                if i not in used and "nazwa" in h and "organ" not in h and "inwestor" not in h:
                    idx = i
                    break
        if idx != -1:
            mapping[field] = idx
            used.add(idx)
    return mapping


def detect_separator(line: str) -> str:
    cands = ["#", ";", "\t", ",", "|"]
    return max(cands, key=lambda c: line.count(c))


def normalize_date(s: str) -> str:
    s = (s or "").strip()
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return ""


def parse_kubatura(s: str) -> int:
    t = re.sub(r"[^0-9.,]", "", (s or "").replace("\xa0", ""))
    if not t:
        return 0
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", t):
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
        if t.count(".") > 1:
            head, _, tail = t.rpartition(".")
            t = head.replace(".", "") + "." + tail
    try:
        v = float(t)
    except ValueError:
        return 0
    return int(round(v)) if v < 10_000_000 else 0  # większe wartości to błędy wpisu w RWDZ


_ROMAN = re.compile(r"^(XXX|XX[IVX]?I{0,3}|X{0,2}(IX|IV|V?I{0,3}))$")


def _to_roman(n: int) -> str:
    vals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, sym in vals:
        while n >= v:
            out += sym
            n -= v
    return out


def normalize_categories(raw: str) -> list[str]:
    s = (raw or "").upper()
    s = re.sub(r"KATEGORI[AI]|KAT\.?", " ", s)
    out: list[str] = []
    for tok in re.split(r"[^IVX0-9]+", s):
        if not tok:
            continue
        if tok.isdigit():
            n = int(tok)
            if 1 <= n <= 30:
                tok = _to_roman(n)
            else:
                continue
        if _ROMAN.match(tok) and tok not in out:
            out.append(tok)
    return out


# ---- Smart Match (ten sam algorytm co analyzeSmartFields w index.html) ----
_L = "a-ząćęłńóśźż"
_B = rf"(?:^|[^{_L}])"
SMART_RULES = [
    (re.compile(rf"{_B}hal(?:a|i|ę|e|ą|ach|ami|om|owa|owy|owe|owej|owego)?(?![{_L}])"), 45, True),
    (re.compile(r"magazyn"), 45, True),
    (re.compile(r"produkc"), 40, True),
    (re.compile(r"logisty"), 40, True),
    (re.compile(r"przemys[lł]"), 35, True),
    (re.compile(rf"{_B}sk[lł]ad(?:ow|u|y|ów)"), 35, True),
    (re.compile(r"ch[lł]odni|mro[zź]ni"), 40, True),
    (re.compile(r"warsztat"), 35, True),
    (re.compile(r"montowni|wytw[oó]rni|hangar|sortowni|dystrybuc"), 40, True),
    (re.compile(r"us[lł]ugow"), 25, False),
    (re.compile(r"handlow|hurtowni|pawilon"), 25, False),
    (re.compile(r"serwis|stacj[aiey] obs[lł]ugi|myjni|salon"), 20, False),
    (re.compile(r"inwentarsk|obor[ayę]|chlewni|kurnik|stodo[lł]|wiat[aeyę]"), 20, False),
    (re.compile(r"gospodarcz"), 10, False),
    (re.compile(r"biurow"), 10, False),
    (re.compile(r"zesp[oó][lł]|centrum|zaplecz"), 10, False),
]
NEG_RES = re.compile(r"mieszkaln|jednorodzin|wielorodzin")
NEG_INFRA = re.compile(
    rf"sieci|sieć|przy[lł][aą]cz|{_B}lini[ia]|gazoci[aą]g|wodoci[aą]g|kanalizac|{_B}drog[aiy]|drogow|chodnik|"
    r"o[sś]wietleni|fotowolt|elektrowni|transformator|kablow|[sś]wiat[lł]owod|telekomunik|maszt|ogrodzeni"
)
NEG_DEMO = re.compile(r"rozbi[oó]rk")
MAIN_INFRA = re.compile(
    r"^(?:\S+\s+){0,2}(?:instalacj|sieci|sie[cć]\b|przy[lł][aą]cz|lini[ia]|kabl|gazoci[aą]g|wodoci[aą]g|kanaliz|"
    r"stacj[iay]\s+(?:transf|[lł]adowania|bazow|elektroenerget)|zbiornik[aóo]?w?\s+(?:na\s+gaz|lpg|gazu)|fotowolt|elektrowni|"
    r"farm[yaę]\s+(?:fotow|wiatr|pv)|bess\b|mikroinstalac|o[sś]wietleni|drog|chodnik|ogrodzeni|masztu|wie[zż]y\s+telekom)"
)
CAT_W = {"XVIII": 35, "XVII": 25, "XIX": 20, "XX": 20, "XVI": 15, "XV": 15, "II": 15}


def smart_score(nazwa: str, rodzaj: str, cats: list[str], kub: int) -> int:
    n = re.sub(r"hal[a-ząćęłńóśźż]*\s+gara[zż]\S*", " garaż ", (nazwa or "").lower())
    n = re.sub(r"magazyn[a-ząćęłńóśźż]*\s+energii", " bess ", n)
    r = (rodzaj or "").lower()
    score = 0
    strong = False
    kw = 0
    for rx, w, is_strong in SMART_RULES:
        if rx.search(n):
            kw += w
            strong = strong or is_strong
    score += min(kw, 60)
    score += max([CAT_W.get(c, 0) for c in cats] or [0])
    if kub >= 50000:
        score += 25
    elif kub >= 10000:
        score += 20
    elif kub >= 3000:
        score += 15
    elif kub >= 1500:
        score += 10
    resid = bool(NEG_RES.search(n)) or r.startswith("budynek mieszkalny") or "XIII" in cats
    if resid and not strong:
        score -= 40
    if (NEG_INFRA.search(n) and not strong) or MAIN_INFRA.search(n.strip()):
        score -= 50
    if (NEG_DEMO.search(n) or NEG_DEMO.search(r)) and not strong:
        score -= 30
    return max(0, min(100, score))


# ---- Pobieranie i parsowanie ----
def download_region_zip(slug: str, timeout: int = 180) -> bytes:
    if slug not in REGIONS:
        raise ValueError(f"Nieznany region: {slug}")
    req = urllib.request.Request(
        GUNB_URL.format(slug=slug),
        headers={"User-Agent": "HalaRadar/2.0 (+https://streamlit.io)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _iter_text_members(raw: bytes):
    zf = zipfile.ZipFile(io.BytesIO(raw))
    names = [n for n in zf.namelist() if not n.endswith("/")]
    preferred = [n for n in names if n.lower().endswith((".csv", ".txt"))] or names
    for name in preferred:
        with zf.open(name) as fh:
            yield name, io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace", newline="")


def filter_rows(text_stream, days: int | None, smart_min: int, max_rows: int):
    """Zwraca (mapping_names, rows) — rows to listy w kolejności CANON_FIELDS."""
    csv.field_size_limit(10_000_000)
    header_line = text_stream.readline()
    sep = detect_separator(header_line)
    headers = next(csv.reader([header_line], delimiter=sep))
    mapping = map_columns(headers)
    # cudzysłowy wykrywamy w pierwszych wierszach danych (GUNB zapisuje puste pola jako "")
    peek = [text_stream.readline() for _ in range(50)]
    sample = header_line + "".join(peek)
    quoted = bool(re.search(r'(^|[' + re.escape(sep) + r'])"', sample, re.M))

    def lines():
        yield from (l for l in peek if l)
        yield from text_stream

    reader = csv.reader(lines(), delimiter=sep, quoting=csv.QUOTE_MINIMAL if quoted else csv.QUOTE_NONE)

    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat() if days else ""
    idx = [mapping.get(f, -1) for f in CANON_FIELDS]
    i_date, i_dec = mapping.get("data_wplywu", -1), mapping.get("data_decyzji", -1)
    i_naz, i_rodz = mapping.get("nazwa", -1), mapping.get("rodzaj", -1)
    i_kat, i_kub = mapping.get("kategoria", -1), mapping.get("kubatura", -1)

    def cell(row, i):
        return row[i].strip().strip('"') if 0 <= i < len(row) else ""

    stats = {"rows": 0, "kept": 0}
    out = []
    while True:
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error:
            continue
        stats["rows"] += 1
        if len(row) < 3:
            continue
        d = normalize_date(cell(row, i_date)) or normalize_date(cell(row, i_dec))
        if cutoff and d and d < cutoff:
            continue
        if smart_min > 0:
            sc = smart_score(cell(row, i_naz), cell(row, i_rodz), normalize_categories(cell(row, i_kat)), parse_kubatura(cell(row, i_kub)))
            if sc < smart_min:
                continue
        out.append([cell(row, i) for i in idx])
        stats["kept"] += 1

    # najnowsze najpierw, z limitem
    di = CANON_FIELDS.index("data_wplywu")
    out.sort(key=lambda r: normalize_date(r[di]), reverse=True)
    if len(out) > max_rows:
        out = out[:max_rows]
    return {
        "separator": sep,
        "headers": headers,
        "mapping": {f: headers[i] for f, i in mapping.items()},
        "stats": stats,
        "rows": out,
    }


def build_payload(slug: str, days: int = 365, smart_min: int = 25, max_rows: int = 40000, raw: bytes | None = None) -> dict:
    """Pełny pakiet danych dla index.html (wstrzykiwany jako window-owa stała SERVER_PAYLOAD)."""
    fetched = dt.datetime.now(_TZ).strftime("%Y-%m-%d %H:%M")
    meta = {
        "source": "GUNB RWDZ",
        "region": slug,
        "region_name": REGIONS.get(slug, slug),
        "fetched_at": fetched,
        "days": days,
        "smart_min": smart_min,
        "url": GUNB_URL.format(slug=slug),
    }
    try:
        if raw is None:
            raw = download_region_zip(slug)
        meta["zip_bytes"] = len(raw)
        all_rows: list[list[str]] = []
        members = []
        for name, stream in _iter_text_members(raw):
            res = filter_rows(stream, days, smart_min, max_rows)
            members.append({"name": name, "separator": res["separator"], "mapping": res["mapping"],
                            "headers": res["headers"], **res["stats"]})
            all_rows.extend(res["rows"])
        meta["members"] = members
        meta["kept_rows"] = len(all_rows)
        return {"meta": meta, "fields": CANON_FIELDS, "rows": all_rows[:max_rows]}
    except Exception as err:  # brak sieci, blokada, zmiana formatu…
        meta["error"] = f"{type(err).__name__}: {err}"
        return {"meta": meta, "fields": CANON_FIELDS, "rows": []}


def payload_to_js(payload: dict) -> str:
    """JSON bezpieczny do wklejenia wewnątrz <script>."""
    s = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return s.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def load_snapshot(url: str, timeout: int = 60) -> dict | None:
    """Wczytuje dzienną kopię (JSON.gz) opublikowaną przez GitHub Action. Zwraca None przy błędzie."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HalaRadar/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) and "rows" in data else None
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pobiera i filtruje dane GUNB RWDZ dla HalaRadar.")
    ap.add_argument("--regions", default="mazowieckie", help="lista województw po przecinku, np. mazowieckie,slaskie")
    ap.add_argument("--days", type=int, default=365, help="ile dni wstecz (data wpływu)")
    ap.add_argument("--out-dir", default="", help="katalog na pliki <region>.json.gz (bez tego: JSON na stdout)")
    args = ap.parse_args(argv)

    slugs = [r.strip().lower() for r in args.regions.split(",") if r.strip()]
    index, ok = {}, 0
    for slug in slugs:
        p = build_payload(slug, args.days)
        meta = p["meta"]
        print(f"{slug}: {len(p['rows'])} wierszy, błąd: {meta.get('error')}", file=sys.stderr)
        index[slug] = {k: meta.get(k) for k in ("fetched_at", "days", "kept_rows", "error")}
        if not args.out_dir:
            print(payload_to_js(p))
            continue
        if p["rows"]:
            os.makedirs(args.out_dir, exist_ok=True)
            body = json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            with open(os.path.join(args.out_dir, f"{slug}.json.gz"), "wb") as fh:
                fh.write(gzip.compress(body, compresslevel=9, mtime=0))
            ok += 1
    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)
        with open(os.path.join(args.out_dir, "index.json"), "w", encoding="utf-8") as fh:
            json.dump({"generated_at": dt.datetime.now(_TZ).strftime("%Y-%m-%d %H:%M"), "regions": index}, fh, ensure_ascii=False, indent=1)
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
