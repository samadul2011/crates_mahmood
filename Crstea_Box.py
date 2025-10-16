import streamlit as st
import duckdb
import pandas as pd
import os
import requests
from datetime import datetime, timedelta

@st.cache_resource
def get_duckdb():
    db_filename = "dispatch.duckdb"
    # Direct download link from Google Drive
    url = "https://drive.google.com/uc?export=download&id=1tYt3Z5McuQYifmNImZyACPHW9C9ju7L4"

    if not os.path.exists(db_filename):
        with st.spinner("Downloading database from Google Drive..."):
            try:
                resp = requests.get(url, allow_redirects=True, timeout=60)
                if resp.status_code != 200:
                    st.error(f"Failed to download database. Status code = {resp.status_code}")
                    st.stop()
                with open(db_filename, "wb") as f:
                    f.write(resp.content)
                st.success("✅ Database downloaded successfully!")
            except Exception as e:
                st.error(f"Error downloading database: {str(e)}")
                st.stop()

    return duckdb.connect(db_filename, read_only=False)

# Page configuration
st.set_page_config(page_title="Crates And Box Dashboard", layout="wide")

# Title
st.title("📊 Crates_Box Data Dashboard")

# Load data
@st.cache_data
def load_data():
    conn = get_duckdb()
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
    try:
        complete_df = conn.execute(query).fetchdf()
        df = complete_df[['Sales_Date', 'Route', 'Crates_Box', 'Crt_Box', 'Supervisor']]
        
        # Convert Sales_Date to datetime if it's not already
        df['Sales_Date'] = pd.to_datetime(df['Sales_Date'], errors='coerce')
        
        # Remove rows with invalid dates
        df = df.dropna(subset=['Sales_Date'])
        
        return df
    except Exception as e:
        st.error(f"Error executing query: {str(e)}")
        return pd.DataFrame()

# Load the data
try:
    data = load_data()
    
    if data.empty:
        st.error("No data loaded. Please check the database connection and query.")
        st.stop()
    
    # Sidebar filters
    st.sidebar.header("🔍 Filters")
    
    # Date range filter
    st.sidebar.subheader("Date Range")
    min_date = data['Sales_Date'].min().date()
    max_date = data['Sales_Date'].max().date()
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input(
            "From Date",
            value=min_date,
            min_value=min_date,
            max_value=max_date,
            key="start_date"
        )
    with col2:
        end_date = st.date_input(
            "To Date",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
            key="end_date"
        )
    
    # Validate date range
    if start_date > end_date:
        st.sidebar.error("⚠️ Start date must be before end date!")
        st.stop()
    
    # Supervisor filter
    st.sidebar.subheader("Supervisor")
    supervisors = sorted([str(s) for s in data['Supervisor'].dropna().unique().tolist()])
    
    if supervisors:
        selected_supervisors = st.sidebar.multiselect(
            "Select Supervisor(s)",
            options=supervisors,
            default=supervisors,
            key="supervisors"
        )
    else:
        st.sidebar.warning("No supervisors found in data")
        selected_supervisors = []
    
    # Crates_Box filter
    st.sidebar.subheader("Crates/Box")
    crates_box = sorted([float(c) for c in data['Crates_Box'].dropna().unique().tolist()])
    
    if crates_box:
        selected_crates_box = st.sidebar.multiselect(
            "Select Crates/Box",
            options=crates_box,
            default=crates_box,
            key="crates_box"
        )
    else:
        st.sidebar.warning("No Crates/Box values found in data")
        selected_crates_box = []
    
    # Filter data based on selections
    if selected_supervisors and selected_crates_box:
        filtered_data = data[
            (data['Sales_Date'].dt.date >= start_date) &
            (data['Sales_Date'].dt.date <= end_date) &
            (data['Supervisor'].isin(selected_supervisors)) &
            (data['Crates_Box'].isin(selected_crates_box))
        ].copy()
    else:
        filtered_data = pd.DataFrame()
    
    # Display metrics
    st.subheader("📈 Summary Metrics")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Records", f"{len(filtered_data):,}")
    with col2:
        total_crt = filtered_data['Crt_Box'].sum() if not filtered_data.empty else 0
        st.metric("Total Crt_Box", f"{total_crt:,.2f}")
    with col3:
        unique_routes = filtered_data['Route'].nunique() if not filtered_data.empty else 0
        st.metric("Unique Routes", f"{unique_routes}")
    with col4:
        st.metric("Date Range", f"{(end_date - start_date).days + 1} days")
    
    st.divider()
    
    # Create pivot table
    st.subheader("📊 Pivot Table: Sum of Crt_Box by Route and Date")
    
    if not filtered_data.empty:
        # Create pivot table
        pivot_data = filtered_data.groupby(['Sales_Date', 'Route'])['Crt_Box'].sum().reset_index()
        pivot_table = pivot_data.pivot(index='Route', columns='Sales_Date', values='Crt_Box')
        
        # Format the column headers to show only date
        pivot_table.columns = [col.strftime('%Y-%m-%d') for col in pivot_table.columns]
        
        # Add total column
        pivot_table['Total'] = pivot_table.sum(axis=1)
        
        # Sort by total descending
        pivot_table = pivot_table.sort_values('Total', ascending=False)
        
        # Fill NaN with 0 for better display
        pivot_table = pivot_table.fillna(0)
        
        # Display pivot table
        st.dataframe(
            pivot_table.style.format("{:.2f}").background_gradient(cmap='YlOrRd', axis=None),
            use_container_width=True,
            height=400
        )
        
        # Download button for pivot table
        csv = pivot_table.to_csv()
        st.download_button(
            label="📥 Download Pivot Table as CSV",
            data=csv,
            file_name=f"pivot_table_{start_date}_{end_date}.csv",
            mime="text/csv",
            key="download_pivot"
        )
        
        st.divider()
        
        # Display raw filtered data
        with st.expander("📋 View Filtered Raw Data"):
            st.dataframe(
                filtered_data[['Sales_Date', 'Route', 'Crates_Box', 'Crt_Box', 'Supervisor']],
                use_container_width=True,
                height=300
            )
            
            # Download button for raw data
            raw_csv = filtered_data.to_csv(index=False)
            st.download_button(
                label="📥 Download Raw Data as CSV",
                data=raw_csv,
                file_name=f"raw_data_{start_date}_{end_date}.csv",
                mime="text/csv",
                key="download_raw"
            )
    else:
        st.warning("⚠️ No data available for the selected filters.")

except Exception as e:
    st.error(f"❌ Error loading data: {str(e)}")
    st.exception(e)  # Shows full traceback for debugging
    st.info("Please check the database connection and try again.")
