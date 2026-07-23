import streamlit as st
import requests

st.set_page_config(page_title="Bristlecone Logic Core", layout="wide")
st.title("🌲 Bristlecone Logic Core Interface")

API_URL = "http://localhost:8000"

# Sidebar Health Check
st.sidebar.header("System Status")
try:
    r = requests.get(f"{API_URL}/health", timeout=2)
    if r.status_code == 200:
        st.sidebar.success("Status: ONLINE")
    else:
        st.sidebar.warning(f"Status: HTTP {r.status_code}")
except Exception:
    st.sidebar.error("Status: OFFLINE")

# Command Execution Interface
st.subheader("Command Pipeline")
prompt = st.text_input("Enter command:", placeholder="Please check status of system")

if st.button("Send Request", type="primary"):
    if prompt:
        try:
            res = requests.post(f"{API_URL}/execute", json={"command": prompt}, timeout=5)
            data = res.json()
            
            if res.status_code == 200 and data.get("status") == "approved":
                st.success("Execution Approved by Layer 3 ToolGater")
                st.json(data)
            else:
                st.error("Execution Blocked by Zero Trust Policy")
                st.json(data)
        except Exception as e:
            st.error(f"Error connecting to API Gateway: {e}")
