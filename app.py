"""
HalaRadar na Streamlit Community Cloud — dane GUNB pobierane automatycznie.

Skąd biorą się dane (bez ręcznego wgrywania):
  1. Na żywo z GUNB: przy otwarciu aplikacji, najwyżej raz na dobę (nowa „doba danych”
     zaczyna się o 5:00 czasu polskiego, po nocnej aktualizacji rejestru GUNB).
  2. Zapas: dzienna kopia, którą GitHub Action (.github/workflows/gunb-daily.yml)
     publikuje co noc na gałęzi „data” tego repozytorium. Używana, gdy GUNB nie odpowiada.

Parametry w adresie (opcjonalne):
  ?region=slaskie   — inne województwo (dolnoslaskie, lodzkie, malopolskie, wielkopolskie, …)
  ?dni=730          — ile dni wstecz (domyślnie 365)
  ?odswiez=1        — wymuś ponowne pobranie danych teraz
"""

import datetime as dt
import json
import pathlib
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

import gunb_loader

# Dzienna kopia danych (gałąź „data”, publikowana przez GitHub Action)
SNAPSHOT_URL = "https://raw.githubusercontent.com/hubertt95/halaradar/data/{slug}.json.gz"

st.set_page_config(
    page_title="HalaRadar — Mapa Wniosków o Pozwolenie na Budowę",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        .block-container { padding: 0 !important; max-width: 100% !important; }
        header, footer, #MainMenu { visibility: hidden; height: 0; }
        iframe { display: block; width: 100%; height: 100vh !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

params = st.query_params
region = str(params.get("region", "mazowieckie")).lower().strip()
if region not in gunb_loader.REGIONS:
    region = "mazowieckie"
try:
    days = max(30, min(3650, int(params.get("dni", 365))))
except ValueError:
    days = 365


def data_day() -> str:
    """Klucz bufora: zmienia się codziennie o 5:00 czasu polskiego."""
    now = dt.datetime.now(ZoneInfo("Europe/Warsaw")) - dt.timedelta(hours=5)
    return now.strftime("%Y-%m-%d")


@st.cache_data(ttl=24 * 3600, show_spinner=False, max_entries=8)
def load_payload(region_slug: str, days_back: int, day_key: str) -> str:
    payload = gunb_loader.build_payload(region_slug, days_back)
    if payload["rows"]:
        payload["meta"]["origin"] = "live"
        return gunb_loader.payload_to_js(payload)
    # GUNB nie odpowiedział → dzienna kopia z GitHub
    snap = gunb_loader.load_snapshot(SNAPSHOT_URL.format(slug=region_slug))
    if snap and snap.get("rows"):
        snap["meta"]["origin"] = "snapshot"
        snap["meta"]["live_error"] = payload["meta"].get("error")
        return gunb_loader.payload_to_js(snap)
    payload["meta"]["origin"] = "none"
    return gunb_loader.payload_to_js(payload)


if params.get("odswiez") == "1":
    load_payload.clear()

html_path = pathlib.Path(__file__).parent / "index.html"
try:
    html_code = html_path.read_text(encoding="utf-8")
except FileNotFoundError:
    st.error("Nie znaleziono pliku `index.html` obok `app.py` w repozytorium.")
    st.stop()

with st.spinner(f"Pobieranie aktualnych danych GUNB RWDZ (woj. {gunb_loader.REGIONS[region]})… pierwsze otwarcie danego dnia trwa do ~1 min."):
    payload_js = load_payload(region, days, data_day())

query_js = json.dumps({k: str(v) for k, v in params.items()}, ensure_ascii=False).replace("</", "<\\/")
html_code = html_code.replace("/*__HALARADAR_SERVER_DATA__*/null", payload_js, 1)
html_code = html_code.replace("/*__HALARADAR_QUERY__*/null", query_js, 1)

components.html(html_code, height=950, scrolling=False)
