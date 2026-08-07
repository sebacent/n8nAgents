from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./hamburger_bot.db"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = "whatsapp:+14155238886"
    SECRET_KEY: str = "changeme-use-a-strong-random-key"
    DEBUG: bool = False
    RESTAURANT_NAME: str = "Burger Palace"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
