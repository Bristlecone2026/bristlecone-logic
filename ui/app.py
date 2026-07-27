import streamlit as st
from api_client import APIClient

st.set_page_config(page_title="Bristlecone Logic", page_icon="🌲", layout="wide")

client = APIClient()

# Initialize session state for auth token
if "token" not in st.session_state:
    st.session_state["token"] = None
if "user" not in st.session_state:
    st.session_state["user"] = None

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
                st.success("Authenticated successfully!")
                st.rerun()
            else:
                st.error("Invalid credentials or server unreachable.")

def main_dashboard():
    # Sidebar Navigation & User Info
    user = st.session_state.get("user") or {}
    username = user.get("username", "User")
    
    st.sidebar.title("Navigation")
    st.sidebar.write(f"Logged in as: **{username}**")
    
    if st.sidebar.button("Log Out"):
        st.session_state["token"] = None
        st.session_state["user"] = None
        st.rerun()

    # Main Workspace
    st.title("System Dashboard")
    st.success("API Integration Active & Authenticated")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("API Status", "Connected")
    col2.metric("Active Session", "Valid")
    col3.metric("Role", user.get("role", "Standard"))

# Render layout based on auth state
if not st.session_state["token"]:
    login_form()
else:
    main_dashboard()
