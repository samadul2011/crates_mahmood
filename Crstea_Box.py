import streamlit as st
import duckdb
import pandas as pd
import requests
from datetime import datetime, timedelta
import os

# ==============================================================
# 1️⃣  Page configuration
# ==============================================================
st.set_page_config(page_title="Sales Dashboard", layout="wide")
st.title("📊 Sales Data Dashboard")

# ==============================================================
# 2️⃣  Database file setup (Google Drive link)
# ==============================================================
db_filename = "dispatch.duckdb"
url = "https://drive.google.com/uc?export=download&id=1tYt3Z5McuQYifmNImZyACPHW9C9ju7L4"

@st.cache_resource
def download_database():
    """Download the database file from Google Drive if not already cached."""
    if not os.path.exists(db_filename):
        st.info("⬇️ Downloading database file from Google Drive...")
        response = requests.get(url)
        with open(db_filename, "wb") as f:
            f.write(response.content)
        st.success("✅ Database downloaded successfully.")
    return duckdb.connect(db_filename)

# ==============================================================
# 3️⃣  Load data
# ==============================================================
@st.cache_data
def load_data():
    conn = download_database()
    query = """
    SELECT 
        s.Code,
        s.Sales_Date,
        s.Qty,
        s.Route,
        p.Description,
        p.Cake,
        p.Cr_Bo AS Crates_Box,
        sup.Supervisor,
        CASE 
            WHEN p.Cake IS NOT NULL AND p.Cake <> 0 
                THEN CAST(s.Qty AS DOUBLE) / CAST(p.Cake AS DOUBLE)
            ELSE NULL
        END AS Crt_Box
    FROM sales AS s
    LEFT JOIN Products AS p
        ON TRIM(CAST(s.Code AS VARCHAR)) = TRIM(CAST(p.Code AS VARCHAR))
    LEFT JOIN Supervisors AS sup
        ON s.Route = sup.Route;
    """
    complete_df = conn.execute(query).fetchdf()
    df = complete_df[['Sales_Date', 'Route', 'Crates_Box', 'Crt_Box', 'Supervisor']]
    df['Sales_Date'] = pd.to_datetime(df['Sales_Date'])
    df['Crt_Box'] = df['Crt_Box'].round(0)  # Round to whole numbers
    return df

# ==============================================================
# 4️⃣  Dashboard Logic
# ==============================================================
try:
    data = load_data()

    st.sidebar.header("🔍 Filters")

    # Date Range Filter
    st.sidebar.subheader("Date Range")
    min_date = data['Sales_Date'].min().date()
    max_date = data['Sales_Date'].max().date()
    start_date = st.sidebar.date_input("From Date", value=min_date, min_value=min_date, max_value=max_date)
    end_date = st.sidebar.date_input("To Date", value=max_date, min_value=min_date, max_value=max_date)

    # Supervisor Filter
    st.sidebar.subheader("Supervisor")
    supervisors = sorted(data['Supervisor'].dropna().unique().tolist())
    selected_supervisors = st.sidebar.multiselect("Select Supervisor(s)", options=supervisors, default=supervisors)

    # Crates/Box Filter
    st.sidebar.subheader("Crates/Box")
    crates_box = sorted(data['Crates_Box'].dropna().unique().tolist())
    selected_crates_box = st.sidebar.multiselect("Select Crates/Box", options=crates_box, default=crates_box)

    # Filtered Data
    filtered_data = data[
        (data['Sales_Date'].dt.date >= start_date)
        & (data['Sales_Date'].dt.date <= end_date)
        & (data['Supervisor'].isin(selected_supervisors))
        & (data['Crates_Box'].isin(selected_crates_box))
    ].copy()

    # ==============================================================
    #  Summary Metrics
    # ==============================================================
    st.subheader("📈 Summary Metrics")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Records", f"{len(filtered_data):,}")
    with col2:
        st.metric("Total Crt_Box", f"{filtered_data['Crt_Box'].sum():,.0f}")
    with col3:
        st.metric("Unique Routes", f"{filtered_data['Route'].nunique()}")
    with col4:
        st.metric("Date Range", f"{(end_date - start_date).days + 1} days")

    st.divider()

    # ==============================================================
    #  Pivot Table
    # ==============================================================
    st.subheader("📊 Pivot Table: Sum of Crt_Box by Route and Date")

    if not filtered_data.empty:
        pivot_data = filtered_data.groupby(['Sales_Date', 'Route'])['Crt_Box'].sum().reset_index()
        pivot_table = pivot_data.pivot(index='Route', columns='Sales_Date', values='Crt_Box')
        pivot_table.columns = [col.strftime('%Y-%m-%d') for col in pivot_table.columns]
        pivot_table['Total'] = pivot_table.sum(axis=1)
        pivot_table = pivot_table.sort_values('Total', ascending=False).round(0)

        # Display pivot table (no matplotlib)
        st.dataframe(
            pivot_table.style.format("{:,.0f}"),  # Show rounded integers with commas
            use_container_width=True,
            height=400
        )

        csv = pivot_table.to_csv()
        st.download_button(
            label="📥 Download Pivot Table as CSV",
            data=csv,
            file_name=f"pivot_table_{start_date}_{end_date}.csv",
            mime="text/csv"
        )

        st.divider()

        # Raw Data View
        with st.expander("📋 View Filtered Raw Data"):
            st.dataframe(
                filtered_data[['Sales_Date', 'Route', 'Crates_Box', 'Crt_Box', 'Supervisor']],
                use_container_width=True,
                height=300
            )
            raw_csv = filtered_data.to_csv(index=False)
            st.download_button(
                label="📥 Download Raw Data as CSV",
                data=raw_csv,
                file_name=f"raw_data_{start_date}_{end_date}.csv",
                mime="text/csv"
            )
    else:
        st.warning("⚠️ No data available for the selected filters.")

except Exception as e:
    st.error(f"❌ Error loading data: {str(e)}")
    st.info("Please make sure the Google Drive file is publicly accessible.")
