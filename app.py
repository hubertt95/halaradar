"""
Uruchamia aplikację HalaRadar (index.html) na pełnym ekranie w Streamlit Community Cloud.
Upewnij się, że plik index.html znajduje się w tym samym folderze repozytorium co app.py.
"""

import pathlib
import streamlit as st
import streamlit.components.v1 as components

# Konfiguracja strony Streamlit (pełna szerokość okna)
st.set_page_config(
    page_title="HalaRadar — Mapa Wniosków o Pozwolenie na Budowę",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Ukrycie domyślnych marginesów, nagłówka i stopki Streamlit, aby mapa zajęła cały ekran
st.markdown(
    """
    <style>
        .block-container {
            padding: 0 !important;
            max-width: 100% !important;
        }
        header, footer, #MainMenu {
            visibility: hidden;
            height: 0;
        }
        iframe {
            display: block;
            width: 100%;
            height: 100vh !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# Ścieżka do pliku index.html w tym samym katalogu co app.py
html_path = pathlib.Path(__file__).parent / "index.html"

try:
    # Wczytanie kodu HTML i osadzenie go w aplikacji Streamlit
    html_code = html_path.read_text(encoding="utf-8")
    components.html(html_code, height=950, scrolling=False)
except FileNotFoundError:
    st.error(
        "Nie znaleziono pliku `index.html` w repozytorium. "
        "Upewnij się, że plik `index.html` znajduje się w tym samym katalogu co `app.py`."
    )
except Exception as err:
    st.error(f"Wystąpił nieoczekiwany błąd podczas ładowania aplikacji: {err}")
