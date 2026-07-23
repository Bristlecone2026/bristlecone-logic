import os

class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "your_openai_api_key_here")
    HMAC_SECRET: str = os.getenv("HMAC_SECRET", "bristlecone-zero-trust-secret-key")

settings = Settings()
