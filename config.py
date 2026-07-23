import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

API_KEY = os.getenv("API_KEY", "default_key")
HMAC_SECRET_KEY = os.getenv("HMAC_SECRET_KEY", "default_secret_key")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
