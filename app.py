import pathlib
   import streamlit as st
   import streamlit.components.v1 as components

   st.set_page_config(page_title="HalaRadar — Mapa Wniosków", layout="wide")

   # Usunięcie domyślnych marginesów Streamlit, aby mapa zajmowała 100% ekranu
   st.markdown(
       "<style>.block-container{padding:0!important;max-width:100%!important;} header,footer{visibility:hidden;}</style>",
       unsafe_allow_html=True,
   )

   html_code = pathlib.Path("index.html").read_text(encoding="utf-8")
   components.html(html_code, height=920, scrolling=False)