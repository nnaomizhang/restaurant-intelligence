"""
Restaurant Intelligence — Streamlit Frontend
============================================
Chat interface + metric cards + data visualisations.
Calls FastAPI backend for all data.
"""

import streamlit as st
import requests
import json
import pandas as pd
import plotly.express as px
from pathlib import Path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import PROCESSED_DIR

API_BASE = "http://localhost:8000/api"

st.set_page_config(
    page_title="Restaurant Intelligence",
    page_icon="🍽️",
    layout="wide",
)

# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------

with st.sidebar:
    st.title("🍽️ Restaurant Intelligence")
    st.markdown("Analysing London's food scene in Shoreditch, Peckham and Hackney.")

    neighbourhood = st.selectbox(
        "Select neighbourhood",
        ["All", "Shoreditch", "Peckham", "Hackney"],
        index=0,
    )

    min_rating = st.slider("Minimum Google rating", 0.0, 5.0, 0.0, 0.1)

    st.markdown("---")
    st.markdown("**Data sources:**")
    st.markdown("- Google Places")
    st.markdown("- FSA Hygiene Ratings")
    st.markdown("- Companies House")
    st.markdown("- Deliveroo")
    st.markdown("- ONS Census 2021")


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------

def get_restaurants(neighbourhood=None, min_rating=0.0, limit=50):
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


def get_hygiene(neighbourhood=None, limit=100):
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


def query_agent(question, neighbourhood=None):
    payload = {"question": question}
    if neighbourhood and neighbourhood != "All":
        payload["neighbourhood"] = neighbourhood
    try:
        r = requests.post(f"{API_BASE}/query", json=payload, timeout=60)
        return r.json() if r.status_code == 200 else {"answer": "Error contacting agent"}
    except Exception as e:
        return {"answer": f"Error: {str(e)}"}


# ------------------------------------------------------------------
# Main tabs
# ------------------------------------------------------------------

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "💬 Chat", "🗺️ Restaurants", "🧹 Hygiene", "👥 Demographics",
    "💭 Sentiment", "📊 Market Analysis"
])


# ------------------------------------------------------------------
# Tab 1 — Chat
# ------------------------------------------------------------------

with tab1:
    st.header("Ask anything about London restaurants")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("e.g. What are the best restaurants in Shoreditch?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result = query_agent(
                    prompt,
                    neighbourhood if neighbourhood != "All" else None
                )
            answer = result.get("answer", "No answer returned")
            st.markdown(answer)

            # Show validation status
            validation = result.get("validation", {})
            if validation:
                is_valid = validation.get("is_valid", True)
                verified = validation.get("verified_restaurants", [])
                col1, col2 = st.columns(2)
                with col1:
                    if is_valid:
                        st.success("✓ Response validated")
                    else:
                        st.warning("⚠ Some claims unverified")
                with col2:
                    if verified:
                        st.caption(f"Verified: {', '.join(verified[:3])}")

            latency = result.get("latency_ms", 0)
            st.caption(f"Response time: {latency/1000:.1f}s")

        st.session_state.messages.append({"role": "assistant", "content": answer})

    if st.button("Clear chat"):
        st.session_state.messages = []
        st.rerun()


# ------------------------------------------------------------------
# Tab 2 — Restaurants
# ------------------------------------------------------------------

with tab2:
    st.header("Restaurant Explorer")

    restaurants = get_restaurants(
        neighbourhood if neighbourhood != "All" else None,
        min_rating
    )

    if not restaurants:
        st.info("No restaurants found. Adjust filters in the sidebar.")
    else:
        # Metric cards
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total restaurants", len(restaurants))
        with col2:
            rated = [r for r in restaurants if r.get("google_rating")]
            avg = round(sum(r["google_rating"] for r in rated) / len(rated), 2) if rated else 0
            st.metric("Avg Google rating", avg)
        with col3:
            on_deliveroo = sum(1 for r in restaurants if r.get("menu_item_count", 0) > 0)
            st.metric("On Deliveroo", on_deliveroo)
        with col4:
            multi_source = sum(1 for r in restaurants if len(r.get("sources_matched", [])) > 1)
            st.metric("Multi-source matched", multi_source)

        st.markdown("---")

        # Chart — rating distribution
        df = pd.DataFrame(restaurants)
        if "google_rating" in df.columns:
            fig = px.histogram(
                df.dropna(subset=["google_rating"]),
                x="google_rating",
                nbins=20,
                title="Rating distribution",
                labels={"google_rating": "Google Rating", "count": "Count"},
                color_discrete_sequence=["#FF4B4B"],
            )
            st.plotly_chart(fig, use_container_width=True)

        # Map
        if "latitude" in df.columns and "longitude" in df.columns:
            map_df = df.dropna(subset=["latitude", "longitude"])
            if not map_df.empty:
                st.subheader("Restaurant map")
                st.map(map_df[["latitude", "longitude"]])

        # Table
        st.subheader("Restaurant list")
        display_cols = ["name", "neighbourhood", "google_rating",
                       "google_review_count", "google_price_level",
                       "business_type", "menu_item_count"]
        available = [c for c in display_cols if c in df.columns]
        st.dataframe(
            df[available].sort_values("google_rating", ascending=False),
            use_container_width=True,
            hide_index=True,
        )


# ------------------------------------------------------------------
# Tab 3 — Hygiene
# ------------------------------------------------------------------

with tab3:
    st.header("FSA Hygiene Ratings")

    hygiene = get_hygiene(neighbourhood if neighbourhood != "All" else None)

    if not hygiene:
        st.info("No hygiene data found.")
    else:
        df_h = pd.DataFrame(hygiene)

        # Metric cards
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total rated", len(hygiene))
        with col2:
            five_star = sum(1 for h in hygiene if h.get("rating_value") == 5)
            st.metric("5-star ratings", five_star)
        with col3:
            low = sum(1 for h in hygiene if isinstance(h.get("rating_value"), (int, float)) and h["rating_value"] < 3)
            st.metric("Below 3 stars", low)

        # Chart — hygiene rating distribution
        if "rating_value" in df_h.columns:
            fig = px.bar(
                df_h["rating_value"].value_counts().reset_index(),
                x="rating_value",
                y="count",
                title="Hygiene rating distribution",
                labels={"rating_value": "Hygiene Rating", "count": "Count"},
                color_discrete_sequence=["#00CC96"],
            )
            st.plotly_chart(fig, use_container_width=True)

        # Table
        st.subheader("Hygiene records")
        display_cols = ["business_name", "neighbourhood", "rating_value",
                       "rating_date", "business_type", "score_hygiene"]
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

    areas = ["Shoreditch", "Peckham", "Hackney"] if neighbourhood == "All" else [neighbourhood]
    demo_data = []

    for area in areas:
        d = get_demographics(area)
        if d:
            demo_data.append(d)

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

        # Comparison chart
        if len(demo_data) > 1:
            df_d = pd.DataFrame(demo_data)
            fig = px.bar(
                df_d,
                x="neighbourhood",
                y=["avg_age_25_34_pct", "avg_economically_active_pct", "avg_household_single_pct"],
                title="Demographic comparison",
                labels={"value": "Percentage (%)", "neighbourhood": "Neighbourhood"},
                barmode="group",
            )
            st.plotly_chart(fig, use_container_width=True)
            
# ------------------------------------------------------------------
# Tab 5 — Sentiment
# ------------------------------------------------------------------

with tab5:
    st.header("Review Sentiment Analysis")
    st.caption("NLP sentiment scoring of 2,553 Google Places reviews using RoBERTa")

    sentiment_path = PROCESSED_DIR / "sentiment_results.json"
    if not sentiment_path.exists():
        st.info("Run processing/sentiment.py to generate sentiment data")
    else:
        with open(sentiment_path) as f:
            sentiment_data = json.load(f)

        st.metric("Total reviews analysed", f"{sentiment_data.get('total_reviews', 0):,}")

        # By neighbourhood
        st.subheader("Sentiment by neighbourhood")
        neighbourhood_sentiment = sentiment_data.get("by_neighbourhood", {})
        if neighbourhood_sentiment:
            df_sent = pd.DataFrame([
                {
                    "Neighbourhood": k,
                    "Avg sentiment score": round(v.get("avg_score", 0), 3),
                    "Positive reviews": v.get("positive", 0),
                    "Negative reviews": v.get("negative", 0),
                    "Neutral reviews": v.get("neutral", 0),
                }
                for k, v in neighbourhood_sentiment.items()
            ])

            col1, col2 = st.columns(2)
            with col1:
                fig = px.bar(
                    df_sent,
                    x="Neighbourhood",
                    y="Avg sentiment score",
                    title="Average sentiment score by neighbourhood",
                    color="Avg sentiment score",
                    color_continuous_scale="RdYlGn",
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                fig = px.bar(
                    df_sent,
                    x="Neighbourhood",
                    y=["Positive reviews", "Negative reviews", "Neutral reviews"],
                    title="Review sentiment breakdown",
                    barmode="stack",
                    color_discrete_map={
                        "Positive reviews": "#00CC96",
                        "Negative reviews": "#FF4B4B",
                        "Neutral reviews": "#636EFA",
                    }
                )
                st.plotly_chart(fig, use_container_width=True)

        # By cuisine
        st.subheader("Sentiment by cuisine type")
        cuisine_sentiment = sentiment_data.get("by_cuisine", {})
        if cuisine_sentiment:
            df_cuisine = pd.DataFrame([
                {
                    "Cuisine": k,
                    "Avg sentiment": round(v.get("avg_score", 0), 3),
                    "Positive": v.get("positive", 0),
                    "Negative": v.get("negative", 0),
                    "Total": v.get("total", 0),
                }
                for k, v in cuisine_sentiment.items()
            ]).sort_values("Avg sentiment", ascending=False)

            fig = px.bar(
                df_cuisine,
                x="Cuisine",
                y="Avg sentiment",
                title="Average sentiment score by cuisine",
                color="Avg sentiment",
                color_continuous_scale="RdYlGn",
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_cuisine, use_container_width=True, hide_index=True)


# ------------------------------------------------------------------
# Tab 6 — Market Analysis
# ------------------------------------------------------------------

with tab6:
    st.header("Market Demand Analysis")
    st.caption("Supply/demand scoring using population, demographics, sentiment and restaurant density")

    demand_path = PROCESSED_DIR / "demand_scores.json"
    catchment_path = PROCESSED_DIR / "catchment_results.json"

    if not demand_path.exists():
        st.info("Run processing/demand_mapper.py to generate demand data")
    else:
        with open(demand_path) as f:
            demand_data = json.load(f)

        # Demand scores overview
        st.subheader("Neighbourhood opportunity scores")

        df_demand = pd.DataFrame([
            {
                "Neighbourhood": k,
                "Demand score": v["demand_score"],
                "Supply score": v["supply_score"],
                "Opportunity score": v["opportunity_score"],
                "Population": v["raw_metrics"]["population"],
                "Restaurants": v["raw_metrics"]["total_restaurants"],
                "Avg rating": v["raw_metrics"]["avg_rating"],
                "Sentiment": v["raw_metrics"]["sentiment"],
            }
            for k, v in demand_data.items()
        ])

        col1, col2, col3 = st.columns(3)
        for i, (_, row) in enumerate(df_demand.iterrows()):
            col = [col1, col2, col3][i]
            with col:
                st.metric(row["Neighbourhood"], f"{row['Opportunity score']:.3f}")
                st.caption(f"Demand: {row['Demand score']:.3f} | Supply: {row['Supply score']:.3f}")

        fig = px.bar(
            df_demand,
            x="Neighbourhood",
            y=["Demand score", "Supply score", "Opportunity score"],
            title="Market demand vs supply by neighbourhood",
            barmode="group",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Demand components breakdown
        st.subheader("Demand component breakdown")
        for area, data in demand_data.items():
            with st.expander(f"{area} — demand components"):
                components = data.get("demand_components", {})
                df_comp = pd.DataFrame([
                    {"Component": k.replace("_", " ").title(), "Score": v}
                    for k, v in components.items()
                ])
                fig = px.bar(
                    df_comp, x="Component", y="Score",
                    title=f"{area} demand components",
                    color="Score",
                    color_continuous_scale="Blues",
                )
                st.plotly_chart(fig, use_container_width=True)

        # Catchment analysis
        if catchment_path.exists():
            st.subheader("Catchment zone analysis")
            with open(catchment_path) as f:
                catchment_data = json.load(f)

            for restaurant, data in catchment_data.items():
                with st.expander(f"{restaurant}"):
                    zones = data.get("zones", {})
                    df_zones = pd.DataFrame([
                        {
                            "Zone": zone.replace("_", " ").title(),
                            "Radius (km)": info.get("radius_km", 0),
                            "Competitors": info.get("competitor_count", 0),
                            "Avg competitor rating": info.get("avg_competitor_rating", 0),
                        }
                        for zone, info in zones.items()
                    ])
                    st.dataframe(df_zones, use_container_width=True, hide_index=True)

        # GeoJSON map
        st.subheader("Restaurant map with catchment zones")
        geojson_path = PROCESSED_DIR / "restaurants.geojson"
        if geojson_path.exists():
            with open(geojson_path) as f:
                geojson_data = json.load(f)

            coords = [
                {
                    "lat": f["geometry"]["coordinates"][1],
                    "lon": f["geometry"]["coordinates"][0],
                }
                for f in geojson_data["features"]
                if f["geometry"]["type"] == "Point"
            ]
            if coords:
                df_map = pd.DataFrame(coords)
                st.map(df_map)