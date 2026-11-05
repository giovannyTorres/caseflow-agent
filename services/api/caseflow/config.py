import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv('DATABASE_URL', 'postgresql://caseflow:caseflow-demo@localhost:5542/caseflow')
    mode: str = os.getenv('APP_MODE', 'DEMO').upper()
    provider: str = os.getenv('MODEL_PROVIDER', 'openai')
    model: str = os.getenv('MODEL_NAME', 'gpt-4.1-mini')
    max_tokens: int = int(os.getenv('MODEL_MAX_TOKENS', '1200'))
    timeout: float = float(os.getenv('MODEL_TIMEOUT_SECONDS', '30'))
    max_steps: int = 12
    cookie_secure: bool = os.getenv('COOKIE_SECURE', 'false') == 'true'
    allowed_origin: str = os.getenv('APP_ORIGIN', 'http://localhost:3102')

settings = Settings()
if settings.mode not in {'DEMO', 'LIVE'}:
    raise ValueError('APP_MODE must be DEMO or LIVE')

def live_missing():
    if settings.provider not in {'openai', 'gemini'}:
        return ['MODEL_PROVIDER must be openai or gemini']
    key = 'OPENAI_API_KEY' if settings.provider == 'openai' else 'GEMINI_API_KEY'
    return [] if os.getenv(key) else [key]
