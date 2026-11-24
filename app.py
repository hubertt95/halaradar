"""
HalaRadar na Streamlit Community Cloud.

Co robi:
  1. Pobiera z GUNB aktualny plik RWDZ wybranego województwa (domyślnie mazowieckie),
  2. odfiltrowuje domy jednorodzinne, sieci i drogi (wstępny Smart Match) oraz stare sprawy,
  3. wstrzykuje wynik do index.html — aplikacja startuje od razu na prawdziwych danych.

Parametry w adresie (opcjonalne):
  ?region=slaskie   — inne województwo (nazwy jak w pliku GUNB: dolnoslaskie, lodzkie, malopolskie, …)
  ?dni=730          — ile dni wstecz pobierać (domyślnie 365)

Wymagane pliki w repozytorium: app.py, gunb_loader.py, index.html, requirements.txt (z wpisem: streamlit).
"""

import json
import pathlib

import streamlit as st
import streamlit.components.v1 as components

import gunb_loader

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


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=6)
def load_payload(region_slug: str, days_back: int) -> str:
    payload = gunb_loader.build_payload(region_slug, days_back)
    return gunb_loader.payload_to_js(payload)


html_path = pathlib.Path(__file__).parent / "index.html"
try:
    html_code = html_path.read_text(encoding="utf-8")
except FileNotFoundError:
    st.error("Nie znaleziono pliku `index.html` obok `app.py` w repozytorium.")
    st.stop()

with st.spinner(f"Pobieranie aktualnych danych GUNB RWDZ (woj. {gunb_loader.REGIONS[region]})… pierwsze uruchomienie trwa do ~1 min."):
    payload_js = load_payload(region, days)

query_js = json.dumps({k: str(v) for k, v in params.items()}, ensure_ascii=False).replace("</", "<\\/")
html_code = html_code.replace("/*__HALARADAR_SERVER_DATA__*/null", payload_js, 1)
html_code = html_code.replace("/*__HALARADAR_QUERY__*/null", query_js, 1)

components.html(html_code, height=950, scrolling=False)
