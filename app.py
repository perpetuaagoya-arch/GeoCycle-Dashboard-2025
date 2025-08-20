import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import altair as alt
from wordcloud import WordCloud
from io import BytesIO

st.set_page_config(page_title="GeoCycle KE – Eldoret", layout="wide")

@st.cache_data
def load_csv(path):
    df = pd.read_csv(path)
    # safety
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    df = df.dropna(subset=["Latitude","Longitude"])
    # helpers if missing
    for c in ["_WasteCategory","_Alert","_ReasonsNormalized","_InterventionsNormalized"]:
        if c not in df.columns: df[c] = "" if c != "_Alert" else False
    return df

df = load_csv("GeoCycle_Dashboard_Ready_Final.csv")

st.title("♻️ GeoCycle KE – Eldoret Waste Decision-Support")
st.caption("Photos • Actors • Alerts • Folium + Kepler.gl • Aligned with Kenya’s Sustainable Waste Management Act (2022)")

# ---- Sidebar filters
with st.sidebar:
    st.header("Filters")
    wards  = sorted(df["Ward"].dropna().astype(str).unique())
    wastes = sorted(df["Waste Types"].dropna().astype(str).unique())
    actors = sorted(df["Waste Management Actors"].dropna().astype(str).unique())

    sel_wards  = st.multiselect("Ward(s)", wards, default=wards)
    sel_wastes = st.multiselect("Waste type(s)", wastes, default=wastes)
    sel_actors = st.multiselect("Actors", actors, default=actors)
    alerts_only = st.checkbox("Only show Health/Burning alerts", value=False)

mask = pd.Series(True, index=df.index)
if sel_wards:  mask &= df["Ward"].astype(str).isin(sel_wards)
if sel_wastes: mask &= df["Waste Types"].astype(str).isin(sel_wastes)
if sel_actors: mask &= df["Waste Management Actors"].astype(str).isin(sel_actors)
if alerts_only: mask &= df["_Alert"] == True

dfv = df[mask].copy()

# ---- KPIs
c1,c2,c3,c4 = st.columns(4)
c1.metric("Dumpsites (filtered)", len(dfv))
c2.metric("Wards", dfv["Ward"].nunique())
c3.metric("Waste types", dfv["Waste Types"].nunique())
c4.metric("Alerts (health/burning)", int(dfv["_Alert"].sum()))

# ---- Folium map
def color_for(cat, alert=False):
    if alert: return "red"
    return {
        "Organic":"green","Plastic":"red","Paper":"orange","Glass":"blue",
        "Metal":"gray","E-waste":"black","Mixed":"purple","Others":"lightgray",
        "Unknown":"beige"
    }.get(str(cat), "blue")

center = [dfv["Latitude"].mean() if len(dfv) else 0.5167,
          dfv["Longitude"].mean() if len(dfv) else 35.2833]
m = folium.Map(location=center, zoom_start=12)
mc = MarkerCluster().add_to(m)

for _, r in dfv.iterrows():
    photo = r.get("Photo URL","")
    img_html = f'<br><img src="{photo}" width="220">' if isinstance(photo,str) and photo.strip() else ""
    popup = (
        f"<b>Dumpsite:</b> {r.get('Dumpsite Name','Unnamed')}"
        f"<br><b>Ward:</b> {r.get('Ward','Unknown')}"
        f"<br><b>Waste Types:</b> {r.get('Waste Types','—')}"
        f"<br><b>Actors:</b> {r.get('Waste Management Actors','—')}"
        f"<br><b>Community Action:</b> {r.get('Community Interventions','—')}"
        f"<br><b>Reasons:</b> {r.get('Reasons for Dumping','—')}"
        f"<br><b>Proposed Interventions:</b> {r.get('Proposed Interventions','—')}"
        f"{img_html}"
    )
    folium.Marker(
        [float(r["Latitude"]), float(r["Longitude"])],
        popup=popup,
        icon=folium.Icon(
            color=color_for(r.get("_WasteCategory","Unknown"), bool(r.get("_Alert", False))),
            icon='exclamation-sign' if bool(r.get("_Alert", False)) else 'trash',
            prefix='fa'
        )
    ).add_to(mc)

st_folium(m, height=680, width=None)

# ---- Insights (stacked bar + reasons/interventions)
tab1, tab2 = st.tabs(["📊 Waste by Ward","🧩 Reasons & Interventions"])

with tab1:
    d = dfv.copy()
    d["_cat"] = d["_WasteCategory"].replace("", "Unknown")
    if not d.empty:
        agg = d.groupby(["Ward","_cat"]).size().reset_index(name="count")
        chart = alt.Chart(agg).mark_bar().encode(
            x=alt.X("count:Q", title="Dumpsites"),
            y=alt.Y("Ward:N", sort='-x', title="Ward"),
            color=alt.Color("_cat:N", title="Waste Type"),
            tooltip=["Ward","_cat","count"]
        ).properties(height=420)
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No data in current filter.")

with tab2:
    # Reasons bar
    reasons_tokens = []
    for x in dfv["_ReasonsNormalized"].dropna().astype(str):
        reasons_tokens += [p.strip() for p in x.split(",") if p.strip() and p.strip() != "<NA>"]
    if reasons_tokens:
        reasons = pd.Series(reasons_tokens).value_counts().reset_index()
        reasons.columns = ["Reason","Count"]
        st.subheader("Top Reasons for Dumping")
        st.altair_chart(
            alt.Chart(reasons).mark_bar().encode(
                y=alt.Y("Reason:N", sort='-x'),
                x=alt.X("Count:Q"),
                tooltip=["Reason","Count"]
            ).properties(height=420),
            use_container_width=True
        )
    else:
        st.info("No non-empty 'Reasons for Dumping' yet — chart hidden.")

    # Interventions word cloud
    inter_tokens = []
    for x in dfv["_InterventionsNormalized"].dropna().astype(str):
        inter_tokens += [p.strip() for p in x.split(",") if p.strip() and p.strip() != "<NA>"]
    if inter_tokens:
        text = " ".join(inter_tokens)
        wc = WordCloud(width=1000, height=400, background_color="white").generate(text)
        buf = BytesIO()
        wc.to_image().save(buf, format="PNG")
        st.subheader("Proposed Interventions — Word Cloud")
        st.image(buf.getvalue(), use_container_width=True)
    else:
        st.info("No non-empty 'Proposed Interventions' yet — word cloud hidden.")

# ---- Data table + download
with st.expander("Show filtered data table"):
    st.dataframe(dfv.reset_index(drop=True))

@st.cache_data
def to_csv_bytes(df_in: pd.DataFrame) -> bytes:
    return df_in.to_csv(index=False).encode("utf-8")

st.download_button(
    "⬇️ Download filtered CSV",
    data=to_csv_bytes(dfv),
    file_name="GeoCycle_filtered.csv",
    mime="text/csv"
)

# ---- Kepler.gl WOW tab (optional later)
st.info("To add the Kepler.gl wow tab, we’ll enable it after deployment (it needs extra packages which are already listed).")
