"""
Restaurant Intelligence Platform
==================================
Strategic market intelligence for London's restaurant scene.
Powered by multi-source data and LLM reasoning.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import requests
import json
import pandas as pd
import plotly.express as px
from config import PROCESSED_DIR
import os
API_BASE = os.getenv("API_BASE", "http://localhost:8000/api")

st.set_page_config(
    page_title="Restaurant Intelligence Platform",
    page_icon="🍽️",
    layout="wide",
)

# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------

with st.sidebar:
    st.title("🍽️ Restaurant Intelligence")
    st.caption("Strategic market intelligence for London's food scene")
    st.markdown("---")

    neighbourhood = st.selectbox(
        "Focus neighbourhood",
        ["All", "Shoreditch", "Peckham", "Hackney"],
    )

    min_rating = st.slider("Min Google rating", 0.0, 5.0, 0.0, 0.1)

    st.markdown("---")
    st.markdown("**Data sources**")
    st.markdown("🟢 Google Places — ratings & reviews")
    st.markdown("🟢 FSA — hygiene ratings")
    st.markdown("🟢 Companies House — financials")
    st.markdown("🟢 Deliveroo — menus & pricing")
    st.markdown("🟢 ONS Census — demographics")
    st.markdown("🟢 TfL — transport accessibility")
    st.markdown("---")
    st.markdown("**Coverage**")
    st.markdown("📍 Shoreditch · Peckham · Hackney")
    st.markdown("📊 2,528 raw records")
    st.markdown("🧠 12 agent tools")


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------

def get_restaurants(neighbourhood=None, min_rating=0.0, limit=200):
    params = {"limit": limit}
    if neighbourhood and neighbourhood != "All":
        params["neighbourhood"] = neighbourhood
    if min_rating > 0:
        params["min_rating"] = min_rating
    try:
        r = requests.get(f"{API_BASE}/restaurants", params=params, timeout=10)
        return r.json() if r.status_code == 200 else []
    except:
        return []


def get_hygiene(neighbourhood=None, limit=500):
    params = {"limit": limit}
    if neighbourhood and neighbourhood != "All":
        params["neighbourhood"] = neighbourhood
    try:
        r = requests.get(f"{API_BASE}/hygiene", params=params, timeout=10)
        return r.json() if r.status_code == 200 else []
    except:
        return []


def get_demographics(neighbourhood):
    try:
        r = requests.get(f"{API_BASE}/demographics/{neighbourhood}", timeout=10)
        return r.json()[0] if r.status_code == 200 else {}
    except:
        return {}


def query_agent(question, neighbourhood=None, history=None):
    payload = {
        "question": question,
        "history": history or [],
    }
    if neighbourhood and neighbourhood != "All":
        payload["neighbourhood"] = neighbourhood
    try:
        r = requests.post(f"{API_BASE}/query", json=payload, timeout=90)
        return r.json() if r.status_code == 200 else {"answer": "Error contacting agent"}
    except Exception as e:
        return {"answer": f"Error: {str(e)}"}


# ------------------------------------------------------------------
# Hero section
# ------------------------------------------------------------------

st.title("🍽️ Restaurant Intelligence Platform")
st.markdown(
    "**Strategic market intelligence** for London's restaurant scene. "
    "Ask natural language questions across restaurant ratings, hygiene data, "
    "company financials, delivery menus, transport accessibility and neighbourhood demographics."
)
st.markdown("---")

col1, col2, col3, col4, col5, col6 = st.columns(6)
with col1:
    st.metric("Neighbourhoods", "3")
with col2:
    st.metric("Raw records", "2,528")
with col3:
    st.metric("Reviews analysed", "2,553")
with col4:
    st.metric("Data sources", "6")
with col5:
    st.metric("Agent tools", "12")
with col6:
    st.metric("TfL stations", "959")

st.markdown("---")

# ------------------------------------------------------------------
# Tabs
# ------------------------------------------------------------------

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "💬 Strategic Chat",
    "🗺️ Restaurant Explorer",
    "🧹 Hygiene Intelligence",
    "👥 Demographics",
    "💭 Sentiment Analysis",
    "📊 Market Opportunity",
    "📍 Location Analysis",
])


# ------------------------------------------------------------------
# Tab 1 — Chat
# ------------------------------------------------------------------

with tab1:
    st.header("Strategic Market Intelligence Chat")
    st.caption("Ask questions across all data sources. The agent reasons over restaurants, hygiene, financials, menus, transport and demographics.")

    st.markdown("**Try these strategic queries:**")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🏆 Best neighbourhood to open?"):
            st.session_state["prefill"] = "Which neighbourhood should I open a new restaurant in and why? Use demand analysis, demographics and sentiment."
        if st.button("📊 Compare all three areas"):
            st.session_state["prefill"] = "Compare the restaurant market across Shoreditch, Peckham and Hackney including transport accessibility"
        if st.button("🚇 Best transport links"):
            st.session_state["prefill"] = "Which restaurants in Shoreditch have the best transport accessibility?"
    with col2:
        if st.button("⚠️ Financial distress signals"):
            st.session_state["prefill"] = "Are there any restaurants with financial distress signals in Shoreditch? What cuisine gaps does this create?"
        if st.button("🍛 Indian restaurant analysis"):
            st.session_state["prefill"] = "Analyse the Indian restaurant market in Shoreditch — ratings, hygiene, sentiment and competition"
        if st.button("💰 Price point gaps"):
            st.session_state["prefill"] = "What price point gaps exist in Peckham's restaurant market based on menu pricing and demographics?"
    with col3:
        if st.button("📈 Market opportunity Peckham"):
            st.session_state["prefill"] = "What is the market opportunity in Peckham? Chain your analysis across demand, demographics, sentiment and catchment."
        if st.button("🚴 Deliveroo market analysis"):
            st.session_state["prefill"] = "Which cuisines dominate the Deliveroo market in Hackney and what gaps exist?"
        if st.button("🏥 Hygiene risk analysis"):
            st.session_state["prefill"] = "Which areas have the highest concentration of low hygiene ratings and what does this signal?"

    st.markdown("---")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prefill = st.session_state.pop("prefill", None)
    prompt = st.chat_input("Ask a strategic question about London restaurants...") or prefill

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analysing across all data sources..."):
                result = query_agent(
                    prompt,
                    neighbourhood if neighbourhood != "All" else None,
                    history=st.session_state.messages[:-1]
                )
            answer = result.get("answer", "No answer returned")
            st.markdown(answer)

            validation = result.get("validation", {})
            latency = result.get("latency_ms", 0)

            col1, col2, col3 = st.columns(3)
            with col1:
                if validation.get("is_valid"):
                    st.success("✓ Response validated")
                else:
                    st.warning("⚠ Some claims unverified")
            with col2:
                verified = validation.get("verified_restaurants", [])
                if verified:
                    st.caption(f"Verified: {', '.join(verified[:3])}")
            with col3:
                st.caption(f"⏱ {latency/1000:.1f}s")

        st.session_state.messages.append({"role": "assistant", "content": answer})

    if st.session_state.messages:
        if st.button("Clear conversation"):
            st.session_state.messages = []
            st.rerun()


# ------------------------------------------------------------------
# Tab 2 — Restaurant Explorer
# ------------------------------------------------------------------

with tab2:
    st.header("Restaurant Explorer")
    st.caption("Browse and filter restaurants with transport accessibility, financial health and multi-source data")

    restaurants = get_restaurants(
        neighbourhood if neighbourhood != "All" else None,
        min_rating
    )

    if not restaurants:
        st.info("No restaurants found. Adjust filters in the sidebar.")
    else:
        df = pd.DataFrame(restaurants)

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Restaurants", len(restaurants))
        with col2:
            rated = [r for r in restaurants if r.get("google_rating")]
            avg = round(sum(r["google_rating"] for r in rated) / len(rated), 2) if rated else 0
            st.metric("Avg rating", avg)
        with col3:
            on_deliveroo = sum(1 for r in restaurants if r.get("menu_item_count", 0) > 0)
            st.metric("On Deliveroo", on_deliveroo)
        with col4:
            multi = sum(1 for r in restaurants if len(r.get("sources_matched", [])) >= 3)
            st.metric("3+ sources matched", multi)
        with col5:
            if "transport_score" in df.columns:
                avg_transport = round(df["transport_score"].mean(), 2)
                st.metric("Avg transport score", avg_transport)

        st.markdown("---")

        col1, col2 = st.columns(2)
        with col1:
            if "google_rating" in df.columns:
                fig = px.histogram(
                    df.dropna(subset=["google_rating"]),
                    x="google_rating",
                    nbins=20,
                    title="Rating distribution",
                    color_discrete_sequence=["#FF4B4B"],
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            if "neighbourhood" in df.columns and "google_rating" in df.columns:
                fig = px.box(
                    df.dropna(subset=["google_rating"]),
                    x="neighbourhood",
                    y="google_rating",
                    title="Rating by neighbourhood",
                    color="neighbourhood",
                )
                st.plotly_chart(fig, use_container_width=True)

        # Transport accessibility charts
        if "transport_score" in df.columns:
            st.subheader("Transport accessibility")
            col1, col2 = st.columns(2)
            with col1:
                fig = px.histogram(
                    df.dropna(subset=["transport_score"]),
                    x="transport_score",
                    nbins=20,
                    title="Transport score distribution",
                    color_discrete_sequence=["#AB63FA"],
                )
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                if "nearest_station" in df.columns:
                    top_stations = df["nearest_station"].value_counts().head(10).reset_index()
                    top_stations.columns = ["Station", "Count"]
                    fig = px.bar(
                        top_stations,
                        x="Count",
                        y="Station",
                        orientation="h",
                        title="Most common nearest stations",
                        color_discrete_sequence=["#AB63FA"],
                    )
                    st.plotly_chart(fig, use_container_width=True)

        if "latitude" in df.columns:
            map_df = df.dropna(subset=["latitude", "longitude"])
            if not map_df.empty:
                st.subheader("Restaurant locations")
                st.map(map_df[["latitude", "longitude"]])

        st.subheader("Restaurant data")
        display_cols = [
            "name", "neighbourhood", "google_rating", "google_review_count",
            "google_price_level", "business_type", "company_status",
            "nearest_station", "nearest_station_distance_km", "transport_score",
            "menu_item_count", "sources_matched"
        ]
        available = [c for c in display_cols if c in df.columns]
        st.dataframe(
            df[available].sort_values("google_rating", ascending=False),
            use_container_width=True,
            hide_index=True,
        )


# ------------------------------------------------------------------
# Tab 3 — Hygiene Intelligence
# ------------------------------------------------------------------

with tab3:
    st.header("Hygiene Intelligence")
    st.caption("FSA hygiene ratings — a key indicator of operational standards and risk")

    hygiene = get_hygiene(neighbourhood if neighbourhood != "All" else None)

    if not hygiene:
        st.info("No hygiene data found.")
    else:
        df_h = pd.DataFrame(hygiene)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total rated", len(hygiene))
        with col2:
            five_star = sum(1 for h in hygiene if h.get("rating_value") == 5)
            st.metric("5-star ✓", five_star)
        with col3:
            pct = round(five_star / len(hygiene) * 100, 1) if hygiene else 0
            st.metric("% 5-star", f"{pct}%")
        with col4:
            low = sum(1 for h in hygiene if isinstance(h.get("rating_value"), (int, float)) and h["rating_value"] < 3)
            st.metric("Below 3 ⚠", low)

        col1, col2 = st.columns(2)
        with col1:
            if "rating_value" in df_h.columns:
                fig = px.bar(
                    df_h["rating_value"].value_counts().reset_index(),
                    x="rating_value",
                    y="count",
                    title="Hygiene rating distribution",
                    color_discrete_sequence=["#00CC96"],
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            if "neighbourhood" in df_h.columns and "rating_value" in df_h.columns:
                fig = px.box(
                    df_h.dropna(subset=["rating_value"]),
                    x="neighbourhood",
                    y="rating_value",
                    title="Hygiene ratings by neighbourhood",
                    color="neighbourhood",
                )
                st.plotly_chart(fig, use_container_width=True)

        st.subheader("Hygiene records")
        display_cols = ["business_name", "neighbourhood", "rating_value",
                       "rating_date", "business_type",
                       "score_hygiene", "score_structural", "score_management"]
        available = [c for c in display_cols if c in df_h.columns]
        st.dataframe(
            df_h[available].sort_values("rating_value", ascending=False),
            use_container_width=True,
            hide_index=True,
        )


# ------------------------------------------------------------------
# Tab 4 — Demographics
# ------------------------------------------------------------------

with tab4:
    st.header("Neighbourhood Demographics")
    st.caption("ONS Census 2021 — understanding the customer base for each area")

    areas = ["Shoreditch", "Peckham", "Hackney"] if neighbourhood == "All" else [neighbourhood]
    demo_data = [get_demographics(a) for a in areas]
    demo_data = [d for d in demo_data if d]

    if not demo_data:
        st.info("No demographic data found.")
    else:
        for d in demo_data:
            st.subheader(d.get("neighbourhood", ""))
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                pop = d.get("total_population", 0)
                st.metric("Population", f"{int(pop):,}" if pop else "N/A")
            with col2:
                age = d.get("avg_age_25_34_pct", 0)
                st.metric("Age 25-34", f"{round(age, 1)}%" if age else "N/A")
            with col3:
                econ = d.get("avg_economically_active_pct", 0)
                st.metric("Economically active", f"{round(econ, 1)}%" if econ else "N/A")
            with col4:
                single = d.get("avg_household_single_pct", 0)
                st.metric("Single households", f"{round(single, 1)}%" if single else "N/A")

        if len(demo_data) > 1:
            df_d = pd.DataFrame(demo_data)
            fig = px.bar(
                df_d,
                x="neighbourhood",
                y=["avg_age_25_34_pct", "avg_economically_active_pct", "avg_household_single_pct"],
                title="Demographic comparison across neighbourhoods",
                labels={"value": "Percentage (%)", "neighbourhood": "Neighbourhood"},
                barmode="group",
            )
            st.plotly_chart(fig, use_container_width=True)


# ------------------------------------------------------------------
# Tab 5 — Sentiment
# ------------------------------------------------------------------

with tab5:
    st.header("Review Sentiment Analysis")
    st.caption("NLP sentiment scoring of 2,553 Google Places reviews using RoBERTa transformer model")

    sentiment_path = PROCESSED_DIR / "sentiment_results.json"
    if not sentiment_path.exists():
        st.info("Run: python -m processing.sentiment")
    else:
        with open(sentiment_path) as f:
            sentiment_data = json.load(f)

        st.metric("Reviews analysed", f"{sentiment_data.get('total_reviews', 0):,}")

        st.subheader("Sentiment by cuisine")
        st.caption("Weighted by review volume — low sample cuisines flagged as unreliable")
        cuisine_sentiment = sentiment_data.get("by_cuisine", {})
        if cuisine_sentiment:
            df_cuisine = pd.DataFrame([
                {
                    "Cuisine": k,
                    "Avg sentiment": round(v.get("avg_score", 0), 3),
                    "Weighted score": round(v.get("weighted_score", 0), 3),
                    "Positive": v.get("positive", 0),
                    "Negative": v.get("negative", 0),
                    "Total reviews": v.get("total", 0),
                    "Reliable": "✅" if v.get("reliable", False) else "⚠️ Low sample",
                }
                for k, v in cuisine_sentiment.items()
            ]).sort_values("Avg sentiment", ascending=False)

            fig = px.bar(
                df_cuisine,
                x="Cuisine",
                y="Avg sentiment",
                title="Sentiment by cuisine (⚠️ = fewer than 30 reviews)",
                color="Reliable",
                color_discrete_map={"✅": "#00CC96", "⚠️ Low sample": "#FFA15A"},
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_cuisine, use_container_width=True, hide_index=True)


# ------------------------------------------------------------------
# Tab 6 — Market Opportunity
# ------------------------------------------------------------------

with tab6:
    st.header("Market Opportunity Analysis")
    st.caption("Strategic market intelligence for restaurant investors")

    demand_path = PROCESSED_DIR / "demand_scores.json"
    catchment_path = PROCESSED_DIR / "catchment_results.json"

    if not demand_path.exists():
        st.info("Run: python -m processing.demand_mapper")
    else:
        with open(demand_path) as f:
            demand_data = json.load(f)

        st.subheader("Market signals by neighbourhood")
        st.caption("Key indicators for restaurant investment decisions")

        # Market signals
        cols = st.columns(3)
        for i, (area, data) in enumerate(demand_data.items()):
            with cols[i]:
                st.markdown(f"**{area}**")
                st.caption(f"Demand score: {data['demand_score']:.3f}")
                signals = data.get("market_signals", [])
                for signal in signals:
                    st.markdown(f"✅ {signal}")

        st.markdown("---")

        # Demand components
        st.subheader("Demand driver comparison")
        all_components = []
        for area, data in demand_data.items():
            for component, score in data.get("demand_components", {}).items():
                all_components.append({
                    "Neighbourhood": area,
                    "Driver": component.replace("_score", "").replace("_", " ").title(),
                    "Score": score,
                })
        if all_components:
            df_comp = pd.DataFrame(all_components)
            fig = px.bar(
                df_comp,
                x="Driver",
                y="Score",
                color="Neighbourhood",
                barmode="group",
                title="Demand drivers by neighbourhood",
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Cuisine gap analysis
        st.subheader("Cuisine gap analysis")
        st.caption("High positive sentiment + low review count = underserved demand")

        for area, data in demand_data.items():
            with st.expander(f"📊 {area} — cuisine gaps"):
                gaps = data.get("cuisine_gaps", {})
                if gaps:
                    df_gaps = pd.DataFrame([
                        {
                            "Cuisine": k,
                            "Positive rate": v["positive_rate"],
                            "Review count": v["review_count"],
                            "Gap score": v["gap_score"],
                            "Reliable": "✅" if v["reliable"] else "⚠️ Low sample",
                        }
                        for k, v in sorted(gaps.items(), key=lambda x: -x[1]["gap_score"])
                    ])
                    st.dataframe(df_gaps, use_container_width=True, hide_index=True)

        st.markdown("---")

        # Catchment analysis
        if catchment_path.exists():
            st.subheader("Competitive positioning analysis")
            st.caption("Competitor density within walking and delivery zones")
            with open(catchment_path) as f:
                catchment_data = json.load(f)

            for restaurant, data in catchment_data.items():
                with st.expander(f"📍 {restaurant}"):
                    zones = data.get("zones", {})
                    df_zones = pd.DataFrame([
                        {
                            "Zone": zone.replace("_", " ").title(),
                            "Radius (km)": info.get("radius_km", 0),
                            "Total competitors": info.get("total_competitors", 0),
                            "Same type": info.get("same_type_competitors", 0),
                            "High rated (4.5+)": info.get("high_rated_competitors", 0),
                            "Avg competitor rating": info.get("avg_competitor_rating", 0),
                            "Intensity": info.get("competitive_intensity", ""),
                        }
                        for zone, info in zones.items()
                    ])
                    st.dataframe(df_zones, use_container_width=True, hide_index=True)

        # Map
        geojson_path = PROCESSED_DIR / "restaurants.geojson"
        if geojson_path.exists():
            st.subheader("Restaurant density map")
            with open(geojson_path) as f:
                geojson_data = json.load(f)
            coords = [
                {"lat": f["geometry"]["coordinates"][1],
                 "lon": f["geometry"]["coordinates"][0]}
                for f in geojson_data["features"]
                if f["geometry"]["type"] == "Point"
            ]
            if coords:
                st.map(pd.DataFrame(coords))
                
# ------------------------------------------------------------------
# Tab 7 — Location Analysis
# ------------------------------------------------------------------

with tab7:
    st.header("📍 Location Analysis")
    st.caption("Enter a postcode to find nearby restaurants, competitors and transport links")

    col1, col2 = st.columns([2, 1])
    with col1:
        postcode_input = st.text_input(
            "Enter a London postcode",
            placeholder="e.g. E2 7JE, SE15 4DH, E8 4QJ",
            help="Enter any postcode in Shoreditch, Peckham or Hackney"
        )
    with col2:
        radius_choice = st.selectbox(
            "Search radius",
            ["5 min walk (0.4km)", "10 min walk (0.8km)", "Deliveroo zone (3km)"],
        )

    radius_map = {
        "5 min walk (0.4km)": 0.4,
        "10 min walk (0.8km)": 0.8,
        "Deliveroo zone (3km)": 3.0,
    }
    radius_km = radius_map[radius_choice]

    if postcode_input:
        # Geocode postcode using postcodes.io
        import requests as req
        postcode_clean = postcode_input.strip().upper().replace(" ", "")
        geo_url = f"https://api.postcodes.io/postcodes/{postcode_clean}"

        try:
            geo_resp = req.get(geo_url, timeout=10)
            if geo_resp.status_code == 200:
                geo_data = geo_resp.json()["result"]
                user_lat = geo_data["latitude"]
                user_lng = geo_data["longitude"]
                area = geo_data.get("admin_ward", "Unknown area")

                st.success(f"✅ Found: {postcode_input.upper()} — {area} ({user_lat:.4f}, {user_lng:.4f})")

                # Find nearby restaurants
                from sqlalchemy import create_engine, text
                import os
                engine = create_engine(os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/restaurants"))

                with engine.connect() as conn:
                    rows = conn.execute(text("""
                        SELECT name, neighbourhood, address, postcode,
                               latitude, longitude, google_rating,
                               google_review_count, business_type,
                               nearest_station, nearest_station_distance_km,
                               transport_score, menu_item_count,
                               nearest_station_lines
                        FROM restaurants
                        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                    """)).fetchall()

                all_restaurants = [dict(r._mapping) for r in rows]

                # Calculate distances
                from processing.catchment_modeller import haversine_km
                nearby = []
                for r in all_restaurants:
                    dist = haversine_km(user_lat, user_lng, r["latitude"], r["longitude"])
                    if dist <= radius_km:
                        r["distance_km"] = round(dist, 3)
                        nearby.append(r)

                nearby = sorted(nearby, key=lambda x: x["distance_km"])

                st.markdown("---")

                # Metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Nearby restaurants", len(nearby))
                with col2:
                    rated = [r for r in nearby if r.get("google_rating")]
                    avg_r = round(sum(r["google_rating"] for r in rated) / len(rated), 2) if rated else 0
                    st.metric("Avg rating", avg_r)
                with col3:
                    on_del = sum(1 for r in nearby if r.get("menu_item_count", 0) > 0)
                    st.metric("On Deliveroo", on_del)
                with col4:
                    high_rated = sum(1 for r in nearby if r.get("google_rating", 0) >= 4.5)
                    st.metric("Highly rated (4.5+)", high_rated)

                st.markdown("---")

                # Map
                st.subheader("Nearby restaurants map")
                map_data = pd.DataFrame([
                    {"lat": r["latitude"], "lon": r["longitude"]}
                    for r in nearby
                ] + [{"lat": user_lat, "lon": user_lng}])
                st.map(map_data)

                # Nearby restaurants table
                st.subheader(f"Restaurants within {radius_choice}")
                if nearby:
                    df_nearby = pd.DataFrame(nearby)
                    display_cols = ["name", "distance_km", "neighbourhood",
                                   "google_rating", "business_type",
                                   "nearest_station", "nearest_station_distance_km",
                                   "transport_score", "menu_item_count"]
                    available = [c for c in display_cols if c in df_nearby.columns]
                    st.dataframe(
                        df_nearby[available],
                        use_container_width=True,
                        hide_index=True,
                    )

                # Nearest TfL stations
                st.subheader("Nearest TfL stations")
                tfl_cache = PROCESSED_DIR / "tfl_stations.json"
                if tfl_cache.exists():
                    with open(tfl_cache) as f:
                        stations = json.load(f)

                    station_distances = []
                    for s in stations:
                        dist = haversine_km(user_lat, user_lng, s["lat"], s["lng"])
                        station_distances.append({
                            "Station": s["name"],
                            "Distance (km)": round(dist, 3),
                            "Lines": ", ".join(s.get("lines", [])[:3]),
                            "Mode": s.get("mode", ""),
                        })

                    station_distances = sorted(station_distances, key=lambda x: x["Distance (km)"])[:10]
                    st.dataframe(
                        pd.DataFrame(station_distances),
                        use_container_width=True,
                        hide_index=True,
                    )

                # Market gap analysis
                st.subheader("Cuisine analysis for this location")
                if nearby:
                    business_types = [r.get("business_type", "Unknown") for r in nearby if r.get("business_type")]
                    if business_types:
                        type_counts = pd.Series(business_types).value_counts().reset_index()
                        type_counts.columns = ["Business Type", "Count"]
                        fig = px.bar(
                            type_counts,
                            x="Business Type",
                            y="Count",
                            title=f"Restaurant types within {radius_choice}",
                            color_discrete_sequence=["#FF4B4B"],
                        )
                        st.plotly_chart(fig, use_container_width=True)

            else:
                st.error(f"Postcode '{postcode_input}' not found. Please enter a valid London postcode.")

        except Exception as e:
            st.error(f"Error looking up postcode: {str(e)}")

    else:
        st.info("Enter a postcode above to analyse the location's restaurant market.")
        st.markdown("**Example postcodes to try:**")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**Shoreditch**")
            st.code("E2 7JE")
            st.code("EC2A 3JX")
        with col2:
            st.markdown("**Peckham**")
            st.code("SE15 4DH")
            st.code("SE15 5RS")
        with col3:
            st.markdown("**Hackney**")
            st.code("E8 4QJ")
            st.code("E8 2AH")