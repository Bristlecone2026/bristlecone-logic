import os

SECRET_KEY = os.getenv("SECRET_KEY", "bristlecone_dev_secret_key_change_in_production_32char")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
