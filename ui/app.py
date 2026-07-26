import os
import requests
import streamlit as st

# Internal Docker URL by default, falls back to localhost for local dev
API_URL = os.getenv("API_URL", "http://api:8000")

st.set_page_config(
    page_title="Bristlecone Logic",
    page_icon="🌲",
    layout="wide"
)

st.title("🌲 Bristlecone Logic Operations")

# Sidebar: Health Check Status
st.sidebar.header("System Monitor")
try:
    health_resp = requests.get(f"{API_URL}/health", timeout=3)
    if health_resp.status_code == 200:
        st.sidebar.success("API Status: Online")
        st.sidebar.json(health_resp.json())
    else:
        st.sidebar.error(f"API Error: HTTP {health_resp.status_code}")
except Exception as e:
    st.sidebar.error(f"API Unreachable ({e})")

# Tab 1: Log Management
st.header("Database Log Stream")

with st.expander("➕ Create New System Log", expanded=True):
    with st.form("new_log_form", clear_on_submit=True):
        col1, col2 = st.columns([1, 2])
        with col1:
            event_type = st.selectbox(
                "Event Type",
                ["INFO", "WARNING", "ERROR", "SYSTEM_INIT", "DEPLOYMENT"]
            )
        with col2:
            message = st.text_input("Log Message", placeholder="Enter event details...")
        
        submitted = st.form_submit_button("Submit Record")
        
        if submitted:
            if not message.strip():
                st.warning("Please enter a message before submitting.")
            else:
                try:
                    payload = {"event_type": event_type, "message": message}
                    res = requests.post(f"{API_URL}/logs", json=payload, timeout=5)
                    if res.status_code == 201:
                        st.success("Log saved to PostgreSQL!")
                        st.rerun()
                    else:
                        st.error(f"Failed to submit log: {res.status_code}")
                except Exception as ex:
                    st.error(f"Error communicating with API: {ex}")

# Fetch and Display Stored Logs
st.subheader("Stored Logs in PostgreSQL")
if st.button("🔄 Refresh Data"):
    st.rerun()

try:
    response = requests.get(f"{API_URL}/logs?limit=50", timeout=5)
    if response.status_code == 200:
        logs = response.json()
        if logs:
            st.dataframe(
                logs,
                column_config={
                    "id": "Log ID",
                    "event_type": "Event Type",
                    "message": "Message Payload",
                    "created_at": "Timestamp (UTC)"
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No records found in database.")
    else:
        st.error("Failed to retrieve logs from API.")
except Exception as ex:
    st.error(f"Could not connect to backend at {API_URL}: {ex}")
