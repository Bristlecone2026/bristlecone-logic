import os

SECRET_KEY = os.getenv("SECRET_KEY", "bristlecone_dev_secret_key_change_in_production_32char")
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "bc_admin_master_secret_2026")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "11520"))
