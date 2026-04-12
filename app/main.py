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
import plotly.graph_objects as go

st.set_page_config(
    page_title="Restaurant Intelligence Platform",
    page_icon="👨🏻‍🍳",
    layout="wide",
)

# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------

with st.sidebar:
    st.title("Restaurant Intelligence")
    st.caption("Strategic market intelligence for London's food scene")
    st.markdown("---")

    neighbourhood = st.selectbox(
        "Focus neighbourhood",
        ["All", "Shoreditch", "Peckham", "Hackney"],
    )

    min_rating = st.slider("Min Google rating", 0.0, 5.0, 0.0, 0.1)

    st.markdown("---")
    st.markdown("**Data sources**")
    st.markdown("Google Places — Ratings & Reviews")
    st.markdown("FSA — Hygiene Ratings")
    st.markdown("Companies House — Financials")
    st.markdown("Deliveroo — Menus & Pricing")
    st.markdown("ONS Census — dDmographics")
    st.markdown("TfL — Transport ccessibility")
    st.markdown("---")
    st.markdown("**Coverage**")
    st.markdown("📍 Shoreditch · Peckham · Hackney")
    st.markdown("2,528 raw records")
    st.markdown("12 agent tools")


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------

def get_restaurants(neighbourhood=None, min_rating=0.0, limit=500):
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

st.title("Restaurant Intelligence Platform 👨🏻‍🍳")
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
    "Strategic Chat",
    "Restaurant Explorer",
    "Hygiene Intelligence",
    "Demographics",
    "Sentiment Analysis",
    "Market Opportunity",
    "Location Analysis",
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
        if st.button("Best neighbourhood to open?"):
            st.session_state["prefill"] = "Which neighbourhood should I open a new restaurant in and why? Use demand analysis, demographics and sentiment."
        if st.button("Compare all three areas"):
            st.session_state["prefill"] = "Compare the restaurant market across Shoreditch, Peckham and Hackney including transport accessibility"
        if st.button("Best transport links"):
            st.session_state["prefill"] = "Which restaurants in Shoreditch have the best transport accessibility?"
    with col2:
        if st.button("Financial distress signals"):
            st.session_state["prefill"] = "Are there any restaurants with financial distress signals in Shoreditch? What cuisine gaps does this create?"
        if st.button("Indian restaurant analysis"):
            st.session_state["prefill"] = "Analyse the Indian restaurant market in Shoreditch — ratings, hygiene, sentiment and competition"
        if st.button("Price point gaps"):
            st.session_state["prefill"] = "What price point gaps exist in Peckham's restaurant market based on menu pricing and demographics?"
    with col3:
        if st.button("Market opportunity Peckham"):
            st.session_state["prefill"] = "What is the market opportunity in Peckham? Chain your analysis across demand, demographics, sentiment and catchment."
        if st.button("Deliveroo market analysis"):
            st.session_state["prefill"] = "Which cuisines dominate the Deliveroo market in Hackney and what gaps exist?"
        if st.button("Hygiene risk analysis"):
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
        st.info("No restaurants found.")
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
                df_r = df.dropna(subset=["google_rating"]).copy()

                def rating_band(r):
                    if r < 4.0:
                        return "<4.0"
                    elif r < 4.5:
                        return "4.0–4.4"
                    elif r < 4.8:
                        return "4.5–4.7"
                    else:
                        return "4.8+"

                df_r["rating_band"] = df_r["google_rating"].apply(rating_band)

                band_counts = (
                    df_r["rating_band"]
                    .value_counts()
                    .reindex(["<4.0", "4.0–4.4", "4.5–4.7", "4.8+"], fill_value=0)
                    .reset_index()
                )
                band_counts.columns = ["Rating band", "Count"]
                band_counts["Percentage"] = (
                    band_counts["Count"] / band_counts["Count"].sum() * 100
                ).round(1)

                fig = px.bar(
                    band_counts,
                    x="Rating band",
                    y="Count",
                    title="Restaurant Quality Distribution",
                    text=band_counts["Percentage"].astype(str) + "%",
                    labels={
                        "Rating band": "Rating Band",
                        "Count": "Number of Restaurants"
                    }
                )

                fig.update_traces(
                    marker_color=["#E8ECE6", "#CFC8BE", "#B7AE9F", "#959D90"],
                    textposition="outside",
                    customdata=band_counts[["Percentage"]].values,
                    hovertemplate="<b>%{x}</b><br>Restaurants: %{y:,}<br>Share: %{customdata[0]:.1f}%<extra></extra>"
                )

                fig.update_layout(
                    showlegend=False,
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    xaxis_title="Rating Band",
                    yaxis_title="Number of Restaurants",
                    hoverlabel=dict(align="left")
                )

                st.plotly_chart(fig, use_container_width=True)
                
                
        with col2:
            if "neighbourhood" in df.columns and "google_rating" in df.columns:
                fig = px.box(
                    df.dropna(subset=["google_rating"]),
                    x="neighbourhood",
                    y="google_rating",
                    title="Rating by Neighbourhood",
                    color="neighbourhood",
                    labels={
                        "neighbourhood": "Neighbourhood",
                        "google_rating": "Google Rating"
                    },
                    color_discrete_sequence=["#959D90", "#CFC8BE", "#B7AE9F", "#959D90"]
                )
                st.plotly_chart(fig, use_container_width=True)

        # Transport accessibility charts
        if "transport_score" in df.columns:
            st.subheader("Transport Accessibility")
            col1, col2 = st.columns(2)
    
            with col1:
                transport_df = df.dropna(subset=["transport_score"]).copy()
                transport_df["transport_score_pct"] = transport_df["transport_score"] * 100

                def transport_band(score):
                    if score < 40:
                        return "Low"
                    elif score < 70:
                        return "Moderate"
                    elif score < 85:
                        return "High"
                    else:
                        return "Excellent"

                transport_df["transport_band"] = transport_df["transport_score_pct"].apply(transport_band)

                band_counts = (
                    transport_df["transport_band"]
                    .value_counts()
                    .reindex(["Low", "Moderate", "High", "Excellent"], fill_value=0)
                    .reset_index()
                )
                band_counts.columns = ["Accessibility", "Count"]
                band_counts["Percentage"] = (
                    band_counts["Count"] / band_counts["Count"].sum() * 100
                ).round(1)

                band_counts["Colour"] = [
                    "#E8ECE6",  # Low
                    "#CFC8BE",  # Moderate
                    "#B7AE9F",  # High
                    "#959D90",  # Excellent
                ]

                fig = px.bar(
                    band_counts,
                    x="Accessibility",
                    y="Count",
                    title="Restaurant Accessibility Mix",
                    text=band_counts["Percentage"].astype(str) + "%",
                    labels={
                        "Accessibility": "Accessibility Level",
                        "Count": "Number of Restaurants"
                    }
                )

                fig.update_traces(
                    marker_color=band_counts["Colour"],
                    textposition="outside",
                    customdata=band_counts[["Percentage"]].values,
                    hovertemplate="""
                    <b>%{x}</b><br>
                    Restaurants: %{y:,}<br>
                    Share of total: %{customdata[0]:.1f}%<br>
                    <extra></extra>
                    """
                )

                fig.update_layout(
                    showlegend=False,
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    xaxis_title="Accessibility Level",
                    yaxis_title="Number of Restaurants"
                )

                st.plotly_chart(fig, use_container_width=True)
                
                                
            with col2:
                if "nearest_station" in df.columns and "google_rating" in df.columns:
                    station_summary = (
                        df.dropna(subset=["nearest_station"])
                        .groupby("nearest_station")
                        .agg(
                            restaurant_count=("name", "count"),
                            avg_rating=("google_rating", "mean"),
                            avg_reviews=("google_review_count", "mean"),
                        )
                        .reset_index()
                    )

                    station_summary = station_summary.sort_values(
                        ["restaurant_count", "avg_rating"],
                        ascending=[False, False]
                    ).head(10)

                    fig = px.bar(
                        station_summary.sort_values("restaurant_count"),
                        x="restaurant_count",
                        y="nearest_station",
                        orientation="h",
                        color="avg_rating",
                        title="Top Stations by Restaurant Density",
                        color_continuous_scale=[
                            "#F4F4F2",
                            "#DCDAD4",
                            "#BFBDB5",
                            "#959D90"
                        ],
                    )

                    fig.update_traces(
                        hovertemplate="""
                        <b>%{y}</b><br>
                        Restaurants: %{x}<br>
                        Avg rating: %{customdata[0]:.2f}<br>
                        Avg reviews: %{customdata[1]:,.0f}<br>
                        <extra></extra>
                        """,
                        customdata=station_summary[["avg_rating", "avg_reviews"]],
                    )

                    fig.update_layout(
                        xaxis_title="Number of Restaurants",
                        yaxis_title="Transport Station",
                        coloraxis_colorbar_title="Average Rating",
                        yaxis=dict(categoryorder="total ascending")
                    )

                    st.plotly_chart(fig, use_container_width=True)

        if "latitude" in df.columns and "longitude" in df.columns:
            map_df = df.dropna(subset=["latitude", "longitude"]).copy()
            if not map_df.empty:
                st.subheader("Restaurant Locations")

                map_df["google_rating"] = map_df["google_rating"].round(2)
                map_df["google_review_count"] = map_df["google_review_count"].fillna(0).astype(int)

                fig = px.scatter_mapbox(
                    map_df,
                    lat="latitude",
                    lon="longitude",
                    zoom=12.5,
                    height=550,
                )

                fig.update_traces(
                    marker=dict(size=8, color="#959D90", opacity=0.85),
                    hovertemplate="""
                    <b>%{customdata[0]}</b><br>
                    Rating: %{customdata[1]}<br>
                    Reviews: %{customdata[2]}<br>
                    Type: %{customdata[3]}<br>
                    <extra></extra>
                    """,
                    customdata=map_df[[
                        "name",
                        "google_rating",
                        "google_review_count",
                        "business_type"
                    ]].fillna("")
                )

                fig.update_layout(
                    mapbox_style="carto-positron",
                    margin={"r": 0, "t": 40, "l": 0, "b": 0},
                    showlegend=False
                )

                st.plotly_chart(fig, use_container_width=True)

        st.subheader("Restaurant Data")
        st.caption("Raw data transformed into investment-relevant signals")

        def build_investor_df(df):
            investor_rows = []

            for _, r in df.iterrows():
                rating_raw = r.get("google_rating")
                rating = float(rating_raw) if pd.notna(rating_raw) else 0.0

                reviews_raw = r.get("google_review_count")
                reviews = int(reviews_raw) if pd.notna(reviews_raw) else 0

                price = r.get("google_price_level")

                transport_raw = r.get("transport_score")
                transport = float(transport_raw) if pd.notna(transport_raw) else 0.0

                pattern = r.get("trading_pattern") or ""
                raw_status = r.get("company_status")
                status = raw_status.lower() if isinstance(raw_status, str) else ""
                sources = r.get("sources_matched") or []
                on_deliveroo = (r.get("menu_item_count") or 0) > 0

                n_sources = len(sources) if isinstance(sources, list) else 0

                # Price tier
                price_map = {
                    1: "£",
                    2: "££",
                    3: "£££",
                    4: "££££"
                }
                price_tier = price_map.get(price, "—")

                # Transport accessibility
                if transport >= 0.85:
                    accessibility = "Excellent"
                elif transport >= 0.70:
                    accessibility = "High"
                elif transport >= 0.40:
                    accessibility = "Moderate"
                elif transport > 0:
                    accessibility = "Low"
                else:
                    accessibility = "No data"

                # Operating model
                pattern_map = {
                    "all_day_dining": "All-day",
                    "breakfast_cafe": "Breakfast",
                    "dinner_restaurant": "Dinner",
                    "late_night": "Late night",
                    "family_restaurant": "Family",
                    "business_dining": "Business",
                    "standard": "Standard",
                }
                operating_model = pattern_map.get(pattern, "Unknown")

                # Data quality
                if n_sources >= 4:
                    data_quality = "High"
                elif n_sources >= 2:
                    data_quality = "Moderate"
                elif n_sources == 1:
                    data_quality = "Low"
                else:
                    data_quality = "No data"

                # Company status
                if status == "active":
                    company_status = "Active"
                elif status in ("liquidation", "dissolved"):
                    company_status = "Distressed"
                elif status:
                    company_status = status.title()
                else:
                    company_status = "N/A"

                # Brand score
                brand_score = 0
                if rating >= 4.5:
                    brand_score += 3
                elif rating >= 4.0:
                    brand_score += 2
                elif rating >= 3.5:
                    brand_score += 1

                if reviews >= 500:
                    brand_score += 3
                elif reviews >= 100:
                    brand_score += 2
                elif reviews >= 20:
                    brand_score += 1

                if on_deliveroo:
                    brand_score += 1

                # Shortlist status
                invest_score = 0

                if rating >= 4.5:
                    invest_score += 3
                elif rating >= 4.0:
                    invest_score += 2

                if reviews >= 500:
                    invest_score += 3
                elif reviews >= 100:
                    invest_score += 2
                elif reviews >= 20:
                    invest_score += 1

                if transport >= 0.85:
                    invest_score += 3
                elif transport >= 0.70:
                    invest_score += 2
                elif transport >= 0.40:
                    invest_score += 1

                if n_sources >= 3:
                    invest_score += 1

                if status == "active":
                    invest_score += 1

                if on_deliveroo:
                    invest_score += 1

                if invest_score >= 9:
                    shortlist_status = "Strong"
                elif invest_score >= 6:
                    shortlist_status = "Watch"
                elif invest_score >= 3:
                    shortlist_status = "Caution"
                else:
                    shortlist_status = "Avoid"

                # Why this restaurant received its shortlist status
                reasons = []

                if rating >= 4.5:
                    reasons.append("Excellent rating")
                elif rating >= 4.0:
                    reasons.append("High rating")

                if reviews >= 500:
                    reasons.append("High review volume")
                elif reviews >= 100:
                    reasons.append("Moderate review volume")

                if transport >= 0.85:
                    reasons.append("Excellent transport accessibility")
                elif transport >= 0.70:
                    reasons.append("High transport accessibility")
                elif transport >= 0.40:
                    reasons.append("Moderate transport accessibility")

                if status == "active":
                    reasons.append("Active company status")

                if on_deliveroo:
                    reasons.append("Delivery presence")

                reason_text = ", ".join(reasons[:3]) if reasons else "Limited supporting signals"

                investor_rows.append({
                    "Name": r.get("name", ""),
                    "Neighbourhood": r.get("neighbourhood", ""),
                    "Rating": round(rating, 1) if rating else None,
                    "Reviews": reviews,
                    "Price tier": price_tier,
                    "Transport accessibility": accessibility,
                    "Operating model": operating_model,
                    "Brand score": brand_score,
                    "Data quality": data_quality,
                    "Company status": company_status,
                    "Shortlist status": shortlist_status,
                    "Why": reason_text,
                })

            return pd.DataFrame(investor_rows)

        investor_df = build_investor_df(df)

        status_filter = st.multiselect(
            "Filter by shortlist status",
            ["Strong", "Watch", "Caution", "Avoid"],
            default=["Strong", "Watch"],
        )

        filtered_df = (
            investor_df[investor_df["Shortlist status"].isin(status_filter)]
            if status_filter else investor_df
        )

        status_order = {
            "Strong": 0,
            "Watch": 1,
            "Caution": 2,
            "Avoid": 3
        }

        filtered_df = filtered_df.assign(
            sort_order=filtered_df["Shortlist status"].map(status_order)
        ).sort_values(
            ["sort_order", "Brand score", "Reviews", "Rating"],
            ascending=[True, False, False, False]
        ).drop(columns=["sort_order"])

        st.dataframe(
            filtered_df.style.set_properties(
                subset=["Why"],
                **{"white-space": "normal"}
            ),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rating": st.column_config.NumberColumn("Rating", format="%.1f"),
                "Reviews": st.column_config.NumberColumn("Reviews", format="%d"),
                "Why": st.column_config.TextColumn("Why", width="large"),
            }
        )

        st.caption(
            "Shortlist status is a screening indicator combining rating, demand, accessibility, company status and data quality."
        )
        st.caption(
            "Strong = prioritise for diligence; Watch = monitor; Caution = limited potential; Avoid = low priority."
        )

        st.caption(f"Showing {len(filtered_df)} of {len(investor_df)} restaurants")

# Trading patterns
        if "trading_pattern" in df.columns:
            st.subheader("Trading Patterns")
            st.caption(
                "Operating model inferred from opening hours, indicating the primary customer segment."
            )

            col1, col2 = st.columns(2)

            with col1:
                pattern_counts = df["trading_pattern"].value_counts().reset_index()
                pattern_counts.columns = ["Operating model", "Count"]

                pattern_counts["Operating model"] = (
                    pattern_counts["Operating model"]
                    .str.replace("_", " ")
                    .str.title()
                )

                fig = px.bar(
                    pattern_counts,
                    x="Operating model",
                    y="Count",
                    title="Restaurant Operating Models",
                    color_discrete_sequence=["#959D90"],
                    labels={
                        "Operating model": "Operating model",
                        "Count": "Number of restaurants"
                    }
                )

                fig.update_traces(
                    hovertemplate="<b>%{x}</b><br>Restaurants: %{y:,}<extra></extra>"
                )

                fig.update_layout(
                    showlegend=False,
                    xaxis_title="Operating Model",
                    yaxis_title="Number of Restaurants",
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    xaxis=dict(tickangle=-30)
                )

                st.plotly_chart(fig, use_container_width=True)
                
            with col2:
                col1, col2, col3 = st.columns(3)

                non_standard = (df["trading_pattern"] != "standard").mean() * 100
                late_night = (df["trading_pattern"] == "breakfast_cafe").mean() * 100
                breakfast = (df["trading_pattern"] == "late_night").mean() * 100

                with col1:
                    st.metric("Non-standard models", f"{non_standard:.1f}%")

                with col2:
                    st.metric("Breakfast cafe share", f"{late_night:.1f}%")

                with col3:
                    st.metric("Late night share", f"{breakfast:.1f}%")
                    
with tab3:
    st.header("Hygiene Intelligence")
    st.caption("FSA hygiene ratings — a key indicator of operational standards")

    if neighbourhood == "All":
        st.warning(
            "Select a neighbourhood from the sidebar to view detailed hygiene analysis. "
            "Use the 'Focus neighbourhood' dropdown on the left to explore Shoreditch, Peckham or Hackney."
        )
    else:
        hygiene = get_hygiene(neighbourhood=neighbourhood, limit=500)

        if not hygiene:
            st.info("No hygiene data found for the selected neighbourhood.")
        else:
            df_h = pd.DataFrame(hygiene)
            df_h["rating_numeric"] = pd.to_numeric(df_h["rating_value"], errors="coerce")

            total_rated = len(df_h)
            five_star = (df_h["rating_numeric"] == 5).sum()
            avg_rating = df_h["rating_numeric"].mean()
            below_3 = (df_h["rating_numeric"] < 3).sum()
            median_rating = df_h["rating_numeric"].median()

            k1, k2, k3, k4, k5 = st.columns(5)

            with k1:
                st.metric("Total rated", total_rated)
            with k2:
                st.metric("5★", int(five_star))
            with k3:
                st.metric("Average rating", f"{avg_rating:.2f}" if pd.notna(avg_rating) else "-")
            with k4:
                st.metric("Below 3", int(below_3))
            with k5:
                st.metric("Median rating", f"{median_rating:.1f}" if pd.notna(median_rating) else "-")

            col1, col2 = st.columns(2)

            with col1:
                if "rating_value" in df_h.columns:
                    rating_series = df_h["rating_value"].dropna().apply(
                        lambda x: str(int(x)) if isinstance(x, (int, float)) and pd.notna(x) else str(x)
                    )

                    rating_counts = rating_series.value_counts().reset_index()
                    rating_counts.columns = ["Rating", "Count"]

                    rating_order = ["0", "1", "2", "3", "4", "5"]
                    rating_counts["Rating"] = pd.Categorical(
                        rating_counts["Rating"],
                        categories=rating_order,
                        ordered=True
                    )
                    rating_counts = rating_counts.sort_values("Rating")

                    fig = px.bar(
                        rating_counts,
                        x="Rating",
                        y="Count",
                        title="Hygiene Rating Distribution",
                        color="Rating",
                        color_discrete_map={
                            "0": "#670E10",
                            "1": "#B22222",
                            "2": "#E67E22",
                            "3": "#F4D03F",
                            "4": "#2ECC71",
                            "5": "#2E6F40",
                        },
                        labels={
                            "Rating": "Hygiene rating",
                            "Count": "Number of businesses"
                        }
                    )

                    fig.update_traces(
                        text=rating_counts["Count"],
                        textposition="outside",
                        hovertemplate="<b>%{x}</b><br>Businesses: %{y:,}<extra></extra>"
                    )

                    fig.update_layout(
                        showlegend=False,
                        plot_bgcolor="white",
                        paper_bgcolor="white",
                        xaxis_title="Hygiene rating",
                        yaxis_title="Number of businesses"
                    )

                    st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.markdown("### Hygiene insight")
                st.metric("Average rating", f"{avg_rating:.2f}" if pd.notna(avg_rating) else "-")
                st.caption("Distribution shows operational quality within the selected area.")

            st.subheader("Hygiene records")

            df_h["rating_date_clean"] = pd.to_datetime(
                df_h["rating_date"], errors="coerce"
            ).dt.strftime("%d %b %Y")

            display_cols = [
                "business_name",
                "neighbourhood",
                "rating_value",
                "rating_date_clean",
                "business_type",
                "score_hygiene",
                "score_structural",
                "score_management"
            ]

            available = [c for c in display_cols if c in df_h.columns]
            display_df = df_h.sort_values("rating_numeric", ascending=False)[available]

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "business_name": "Business",
                    "neighbourhood": "Area",
                    "rating_value": st.column_config.NumberColumn("Hygiene rating", format="%d"),
                    "rating_date_clean": "Last inspection",
                    "business_type": "Type",
                    "score_hygiene": "Hygiene",
                    "score_structural": "Structural",
                    "score_management": "Management",
                }
            )

            st.caption(f"Showing {len(display_df)} of {len(df_h)} restaurants")
            
# ------------------------------------------------------------------
# Tab 4 — Demographics
# ------------------------------------------------------------------

with tab4:
    st.header("Neighbourhood Demographics")
    st.caption("Catchment characteristics shaping local restaurant demand")

    demo_data = get_demographics(neighbourhood if neighbourhood != "All" else "Peckham")

    if not demo_data:
        st.info("No demographic data found.")
    else:
        area = demo_data.get("neighbourhood", "Unknown area")
        population_density = demo_data.get("avg_population_density")
        age_25_34 = demo_data.get("avg_age_25_34_pct")
        age_35_49 = demo_data.get("avg_age_35_49_pct")
        economically_active = demo_data.get("avg_economically_active_pct")
        household_single = demo_data.get("avg_household_single_pct")

        # ------------------------------------------------------------------
        # KPI row
        # ------------------------------------------------------------------
        k1, k2, k3, k4 = st.columns(4)

        with k1:
            st.metric("Population density", f"{population_density:,.0f}" if population_density is not None else "-")

        with k2:
            st.metric("Age 25–34", f"{age_25_34:.1f}%" if age_25_34 is not None else "-")

        with k3:
            st.metric("Economically active", f"{economically_active:.1f}%" if economically_active is not None else "-")

        with k4:
            st.metric("Single-person households", f"{household_single:.1f}%" if household_single is not None else "-")

        # ------------------------------------------------------------------
        # Chart + insight panel
        # ------------------------------------------------------------------
        col1, col2 = st.columns(2)

        with col1:
            profile_df = pd.DataFrame({
                "Measure": [
                    "Age 25–34",
                    "Age 35–49",
                    "Economically active",
                    "Single-person households",
                ],
                "Percentage": [
                    age_25_34,
                    age_35_49,
                    economically_active,
                    household_single,
                ]
            }).dropna()

            fig = px.bar(
                profile_df,
                x="Measure",
                y="Percentage",
                title=f"Demographic Profile: {area}",
                text_auto=".1f",
                color="Measure",
                color_discrete_map={
                    "Age 25–34": "#959D90",
                    "Age 35–49": "#BBA58F",
                    "Economically active": "#E8D9CD",
                    "Single-person households": "#CFC8BE",
                },
                labels={
                    "Measure": "Demographic measure",
                    "Percentage": "Percentage (%)"
                }
            )

            fig.update_traces(
                texttemplate="%{y:.1f}%",
                textposition="outside",
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "Value: %{y:.1f}%"
                    "<extra></extra>"
                )
            )

            fig.update_layout(
                showlegend=False,
                plot_bgcolor="white",
                paper_bgcolor="white",
                xaxis_title="Demographic measure",
                yaxis_title="Percentage (%)",
                xaxis=dict(tickangle=-20)
            )

            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("### Catchment interpretation")
            st.markdown("---")

            insights = []

            if age_25_34 is not None and age_25_34 >= 25:
                insights.append("a strong young adult catchment")

            if economically_active is not None and economically_active >= 65:
                insights.append("high labour market participation")

            if household_single is not None and household_single >= 35:
                insights.append("a high share of single-person households")

            if population_density is not None and population_density >= 10000:
                insights.append("a dense residential base")

            if insights:
                st.success(
                    f"{area} shows " + ", ".join(insights) +
                    ", supporting demand for casual, convenience-led and delivery-oriented formats."
                )
            else:
                st.info(
                    f"{area} shows a mixed demographic profile with no single dominant catchment characteristic."
                )

            st.caption(
                "Demographic data is aggregated from ONS Census 2021 LSOA-level records within the selected neighbourhood."
            )

        st.markdown("---")

        # ------------------------------------------------------------------
        # Detail table
        # ------------------------------------------------------------------
        st.subheader("Demographic summary")

        display_df = pd.DataFrame([{
            "Neighbourhood": area,
            "Population density": population_density,
            "Age 25–34": age_25_34,
            "Age 35–49": age_35_49,
            "Economically active": economically_active,
            "Single-person households": household_single,
        }])

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Population density": st.column_config.NumberColumn("Population density", format="%.0f"),
                "Age 25–34": st.column_config.NumberColumn("Age 25–34", format="%.1f%%"),
                "Age 35–49": st.column_config.NumberColumn("Age 35–49", format="%.1f%%"),
                "Economically active": st.column_config.NumberColumn("Economically active", format="%.1f%%"),
                "Single-person households": st.column_config.NumberColumn("Single-person households", format="%.1f%%"),
            }
        )

        st.caption("Showing 1 neighbourhood summary")

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

        st.metric("Reviews analysed:", f"{sentiment_data.get('total_reviews', 0):,}")

        st.subheader("Sentiment by Cuisine")
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
                    "Reliable": "Reliable" if v.get("reliable", False) else "Low sample",
                }
                for k, v in cuisine_sentiment.items()
            ]).sort_values("Weighted score", ascending=False)

            fig = px.bar(
                df_cuisine,
                x="Cuisine",
                y="Avg sentiment",
                title="Customer Sentiment Across Cuisines",
                color="Reliable",
                color_discrete_map={
                    "Reliable": "#959D90",
                    "Low sample": "#CFC8BE"
                },
                labels={
                    "Cuisine": "Cuisine",
                    "Avg sentiment": "Average Sentiment"
                }
            )

            fig.update_traces(
                hovertemplate="<b>%{x}</b><br>Average sentiment: %{y:.3f}<extra></extra>"
            )

            fig.update_layout(
                plot_bgcolor="white",
                paper_bgcolor="white",
                xaxis_title="Cuisine",
                yaxis_title="Average sentiment"
            )

            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Cuisine Sentiment Summary")

            st.dataframe(
                df_cuisine,
                use_container_width=True,
                hide_index=True
            )

            st.caption(f"Showing {len(df_cuisine)} cuisines")


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

        st.subheader("Market Signals by Neighbourhood")
        st.caption("Key indicators for restaurant investment decisions")

        # Market signals
        cols = st.columns(3)
        for i, (area, data) in enumerate(demand_data.items()):
            with cols[i]:
                st.markdown(f"**{area}**")
                st.caption(f"Demand score: {data['demand_score']:.3f}")
                signals = data.get("market_signals", [])
                for signal in signals:
                    st.markdown(f"✦ {signal}")

        st.markdown("---")

        # Demand components
        st.subheader("Demand Driver Comparison")
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
                color_discrete_map={
                    "Shoreditch": "#E8D9CD",
                    "Peckham": "#BBA58F",
                    "Hackney": "#959D90",
                },
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Cuisine gap analysis
        st.subheader("Cuisine Gap Analysis")
        st.caption("High positive sentiment + low review count = underserved demand")

        for area, data in demand_data.items():
            with st.expander(f" {area} — Cuisine Gaps"):
                gaps = data.get("cuisine_gaps", {})
                if gaps:
                    df_gaps = pd.DataFrame([
                        {
                            "Cuisine": k,
                            "Positive rate": v["positive_rate"],
                            "Review count": v["review_count"],
                            "Gap score": v["gap_score"],
                            "Reliable": "Reliable" if v["reliable"] else "⚠️ Low sample",
                        }
                        for k, v in sorted(gaps.items(), key=lambda x: -x[1]["gap_score"])
                    ])
                    st.dataframe(df_gaps, use_container_width=True, hide_index=True)

        st.markdown("---")

        # Catchment analysis
        if catchment_path.exists():
            st.subheader("Competitive Positioning Analysis")
            st.caption("Competitor density within walking and delivery zones")
            with open(catchment_path) as f:
                catchment_data = json.load(f)

            for restaurant, data in catchment_data.items():
                with st.expander(f" {restaurant}"):
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
            st.subheader("Restaurant Density Map")
            st.caption("Restaurant locations with rating, review volume and transport accessibility")

            with open(geojson_path) as f:
                geojson_data = json.load(f)

            coords = []
            for feature in geojson_data["features"]:
                if feature["geometry"]["type"] == "Point":
                    props = feature.get("properties", {})
                    coords.append({
                        "lat": feature["geometry"]["coordinates"][1],
                        "lon": feature["geometry"]["coordinates"][0],
                        "name": props.get("name", ""),
                        "neighbourhood": props.get("neighbourhood", ""),
                        "google_rating": props.get("google_rating"),  # keep from geojson
                    })

            if coords:
                map_df = pd.DataFrame(coords)

                # Merge only the fields you do NOT want to rely on from GeoJSON
                merge_cols = [
                    c for c in [
                        "name",
                        "google_review_count",
                        "business_type",
                        "transport_score",
                    ] if c in df.columns
                ]

                if "name" in merge_cols:
                    map_df = map_df.merge(
                        df[merge_cols].drop_duplicates(subset=["name"]),
                        on="name",
                        how="left"
                    )

                # Clean fields
                map_df["google_rating"] = pd.to_numeric(
                    map_df["google_rating"], errors="coerce"
                ).round(1)

                if "google_review_count" in map_df.columns:
                    map_df["google_review_count"] = pd.to_numeric(
                        map_df["google_review_count"], errors="coerce"
                    )

                if "transport_score" in map_df.columns:
                    map_df["transport_score"] = pd.to_numeric(
                        map_df["transport_score"], errors="coerce"
                    ).round(2)

                # Display-friendly fields for hover
                map_df["rating_display"] = map_df["google_rating"].apply(
                    lambda x: f"{x:.1f}" if pd.notna(x) else "No data"
                )

                map_df["reviews_display"] = map_df["google_review_count"].apply(
                    lambda x: f"{int(x):,}" if pd.notna(x) else "No data"
                ) if "google_review_count" in map_df.columns else "No data"

                map_df["transport_display"] = map_df["transport_score"].apply(
                    lambda x: f"{x:.2f}" if pd.notna(x) else "No data"
                ) if "transport_score" in map_df.columns else "No data"

                map_df["type_display"] = (
                    map_df["business_type"].fillna("No data")
                    if "business_type" in map_df.columns else "No data"
                )

                map_df["area_display"] = map_df["neighbourhood"].fillna("Unknown area")

                fig = px.scatter_mapbox(
                    map_df,
                    lat="lat",
                    lon="lon",
                    zoom=12,
                    height=550,
                )

                fig.update_traces(
                    marker=dict(
                        size=8,
                        color="#959D90",
                        opacity=0.85
                    ),
                    customdata=map_df[[
                        "name",
                        "area_display",
                        "rating_display",
                        "reviews_display",
                        "type_display",
                        "transport_display",
                    ]],
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "Area: %{customdata[1]}<br>"
                        "Rating: %{customdata[2]}<br>"
                        "Reviews: %{customdata[3]}<br>"
                        "Type: %{customdata[4]}<br>"
                        "Transport score: %{customdata[5]}"
                        "<extra></extra>"
                    )
                )

                fig.update_layout(
                    mapbox_style="carto-positron",
                    margin={"r": 0, "t": 40, "l": 0, "b": 0},
                    showlegend=False,
                    hoverlabel=dict(align="left")
                )

                st.plotly_chart(fig, use_container_width=True)
        
# ------------------------------------------------------------------
# Tab 7 — Location Analysis
# ------------------------------------------------------------------

with tab7:
    st.header("Location Analysis")
    st.caption("Enter a postcode to find nearby restaurants, competitors and transport links")

    col1, col2 = st.columns([2, 1])
    with col1:
        postcode_input = st.text_input(
            "Enter a London postcode",
            placeholder="e.g. E2 7JE",
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
        import requests as req
        from sqlalchemy import create_engine, text
        import os
        from processing.catchment_modeller import haversine_km

        postcode_clean = postcode_input.strip().upper().replace(" ", "")
        geo_url = f"https://api.postcodes.io/postcodes/{postcode_clean}"

        try:
            geo_resp = req.get(geo_url, timeout=10)

            if geo_resp.status_code == 200:
                geo_data = geo_resp.json()["result"]
                user_lat = geo_data["latitude"]
                user_lng = geo_data["longitude"]
                area = geo_data.get("admin_ward", "Unknown area")

                st.success(f"Found: {postcode_input.upper()} — {area} ({user_lat:.4f}, {user_lng:.4f})")

                engine = create_engine(
                    os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/restaurants")
                )

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
                    high_rated = sum(1 for r in nearby if (r.get("google_rating") or 0) >= 4.5)
                    st.metric("Highly rated (4.5+)", high_rated)

                st.markdown("---")

                # Interactive map
                st.subheader("Nearby restaurants map")

                if nearby:
                    map_df = pd.DataFrame(nearby).copy()

                    map_df["google_rating"] = pd.to_numeric(map_df["google_rating"], errors="coerce").round(1)
                    map_df["google_review_count"] = pd.to_numeric(
                        map_df["google_review_count"], errors="coerce"
                    )
                    map_df["transport_score"] = pd.to_numeric(
                        map_df["transport_score"], errors="coerce"
                    ).round(2)

                    map_df["rating_display"] = map_df["google_rating"].apply(
                        lambda x: f"{x:.1f}" if pd.notna(x) else "No data"
                    )
                    map_df["reviews_display"] = map_df["google_review_count"].apply(
                        lambda x: f"{int(x):,}" if pd.notna(x) else "No data"
                    )
                    map_df["transport_display"] = map_df["transport_score"].apply(
                        lambda x: f"{x:.2f}" if pd.notna(x) else "No data"
                    )
                    map_df["station_display"] = map_df["nearest_station"].fillna("No data")
                    map_df["type_display"] = map_df["business_type"].fillna("No data")
                    map_df["area_display"] = map_df["neighbourhood"].fillna("Unknown area")

                    # Restaurants
                    fig = px.scatter_mapbox(
                        map_df,
                        lat="latitude",
                        lon="longitude",
                        zoom=13,
                        height=550,
                    )

                    fig.update_traces(
                        marker=dict(
                            size=9,
                            color="#959D90",
                            opacity=0.85
                        ),
                        customdata=map_df[[
                            "name",
                            "area_display",
                            "rating_display",
                            "reviews_display",
                            "type_display",
                            "distance_km",
                            "station_display",
                            "transport_display",
                        ]],
                        hovertemplate=(
                            "<b>%{customdata[0]}</b><br>"
                            "Area: %{customdata[1]}<br>"
                            "Rating: %{customdata[2]}<br>"
                            "Reviews: %{customdata[3]}<br>"
                            "Type: %{customdata[4]}<br>"
                            "Distance: %{customdata[5]:.2f} km<br>"
                            "Nearest station: %{customdata[6]}<br>"
                            "Transport score: %{customdata[7]}"
                            "<extra></extra>"
                        )
                    )

                    # User postcode marker
                    fig.add_scattermapbox(
                        lat=[user_lat],
                        lon=[user_lng],
                        mode="markers",
                        marker=dict(size=14, color="#670E10"),
                        name="Selected postcode",
                        hovertemplate=(
                            f"<b>{postcode_input.upper()}</b><br>"
                            f"Area: {area}<br>"
                            "<extra></extra>"
                        )
                    )

                    fig.update_layout(
                        mapbox_style="carto-positron",
                        margin={"r": 0, "t": 40, "l": 0, "b": 0},
                        hoverlabel=dict(align="left"),
                        legend_title_text=""
                    )

                    st.plotly_chart(fig, use_container_width=True)

                # Nearby restaurants table
                st.subheader(f"Restaurants within {radius_choice}")
                if nearby:
                    df_nearby = pd.DataFrame(nearby)
                    display_cols = [
                        "name", "distance_km", "neighbourhood",
                        "google_rating", "google_review_count", "business_type",
                        "nearest_station", "nearest_station_distance_km",
                        "transport_score", "menu_item_count"
                    ]
                    available = [c for c in display_cols if c in df_nearby.columns]

                    st.dataframe(
                        df_nearby[available],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "name": "Restaurant",
                            "distance_km": st.column_config.NumberColumn("Distance (km)", format="%.2f"),
                            "neighbourhood": "Neighbourhood",
                            "google_rating": st.column_config.NumberColumn("Rating", format="%.1f"),
                            "google_review_count": st.column_config.NumberColumn("Reviews", format="%d"),
                            "business_type": "Type",
                            "nearest_station": "Nearest station",
                            "nearest_station_distance_km": st.column_config.NumberColumn("Station distance (km)", format="%.2f"),
                            "transport_score": st.column_config.NumberColumn("Transport score", format="%.2f"),
                            "menu_item_count": st.column_config.NumberColumn("Deliveroo items", format="%d"),
                        }
                    )

                    st.caption(f"Showing {len(df_nearby)} nearby restaurants")

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

                # Cuisine analysis
                st.subheader("Cuisine analysis for this location")
                if nearby:
                    business_types = [
                        r.get("business_type", "Unknown")
                        for r in nearby
                        if r.get("business_type")
                    ]

                    if business_types:
                        type_counts = pd.Series(business_types).value_counts().reset_index()
                        type_counts.columns = ["Business Type", "Count"]

                        fig = px.bar(
                            type_counts,
                            x="Business Type",
                            y="Count",
                            title=f"Restaurant types within {radius_choice}",
                            color="Business Type",
                            color_discrete_sequence=[
                                "#959D90",
                                "#BBA58F",
                                "#E8D9CD",
                                "#CFC8BE",
                                "#A8B5A2",
                                "#D8C3A5",
                                "#8FA6A3",
                                "#CAB8A2",
                            ],
                            labels={
                                "Business Type": "Restaurant type",
                                "Count": "Number of restaurants"
                            }
                        )

                        fig.update_traces(
                            text=type_counts["Count"],
                            textposition="outside",
                            hovertemplate=(
                                "<b>%{x}</b><br>"
                                "Restaurants: %{y:,}"
                                "<extra></extra>"
                            )
                        )

                        fig.update_layout(
                            showlegend=False,
                            plot_bgcolor="white",
                            paper_bgcolor="white",
                            xaxis_title="Restaurant type",
                            yaxis_title="Number of restaurants",
                            xaxis=dict(tickangle=-25)
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