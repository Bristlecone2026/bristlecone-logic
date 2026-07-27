import streamlit as st
from api_client import APIClient

st.set_page_config(page_title="Bristlecone Logic", page_icon="🌲", layout="wide")

client = APIClient()

# Initialize session state keys
if "token" not in st.session_state:
    st.session_state["token"] = None
if "user" not in st.session_state:
    st.session_state["user"] = None

# Restore session from URL query parameters if memory state drops
if not st.session_state["token"]:
    token_param = st.query_params.get("token")
    if token_param:
        user_info = client.get_me(token_param)
        if user_info and "error" not in user_info:
            st.session_state["token"] = token_param
            st.session_state["user"] = user_info
        else:
            st.query_params.clear()

def login_form():
    st.title("🌲 Bristlecone Logic")
    st.subheader("Sign In")
    
    with st.form("login_form"):
        username = st.text_input("Username or Email")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Log In")
        
        if submit:
            if not username or not password:
                st.error("Please enter both username and password.")
                return

            auth_data = client.login(username, password)
            if auth_data and "access_token" in auth_data:
                token = auth_data["access_token"]
                user_info = client.get_me(token)
                
                st.session_state["token"] = token
                st.session_state["user"] = user_info
                st.query_params["token"] = token
                st.success("Authenticated successfully!")
                st.rerun()
            else:
                st.error("Invalid credentials or server unreachable.")

def main_dashboard():
    user = st.session_state.get("user") or {}
    username = user.get("username", "User")
    
    st.sidebar.title("Navigation")
    st.sidebar.write(f"Logged in as: **{username}**")
    
    view = st.sidebar.radio("Module", ["Dashboard", "Agent Orchestrator"])

    if st.sidebar.button("Log Out"):
        st.session_state["token"] = None
        st.session_state["user"] = None
        st.query_params.clear()
        st.rerun()

    if view == "Dashboard":
        st.title("System Dashboard")
        st.success("API Integration Active & Authenticated")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("API Status", "Connected")
        col2.metric("Active Session", "Valid")
        col3.metric("Role", user.get("role", "Standard"))

    elif view == "Agent Orchestrator":
        st.title("⚡ Agent Workflow Orchestrator")
        st.markdown("Trigger multi-layer execution across taxonomy, model inference, tool gating, and telemetry.")

        intent_input = st.text_area("User Intent / Prompt", placeholder="e.g., Analyze recent system metrics and generate a summary report.")
        
        col_run, _ = st.columns([1, 4])
        if col_run.button("Run Agent Workflow", type="primary"):
            if not intent_input.strip():
                st.warning("Please enter an intent before running.")
            else:
                with st.spinner("Executing multi-layer pipeline..."):
                    res = client.run_agent(st.session_state["token"], intent_input)
                    
                    if res and "error" in res:
                        st.error(f"Execution Error: {res['error']}")
                    elif res:
                        st.success("Workflow Execution Complete")
                        
                        col_cat, col_status, col_stage = st.columns(3)
                        col_cat.metric("Taxonomy Category", res.get("category", "N/A"))
                        col_status.metric("Pipeline Status", res.get("status", "N/A"))
                        col_stage.metric("Stage Reached", res.get("pipeline_stage", "N/A"))

                        st.subheader("Pipeline Response Details")
                        st.json(res)

if not st.session_state["token"]:
    login_form()
else:
    main_dashboard()
