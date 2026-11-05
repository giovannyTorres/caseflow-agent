import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv('DATABASE_URL', 'postgresql://caseflow:caseflow-demo@localhost:5542/caseflow')
    mode: str = os.getenv('APP_MODE', 'DEMO').upper()
    provider: str = os.getenv('MODEL_PROVIDER', 'openai')
    model: str = os.getenv('MODEL_NAME', 'gemini-2.5-flash' if os.getenv('MODEL_PROVIDER') == 'gemini' else 'gpt-4.1-mini')
    max_tokens: int = int(os.getenv('MODEL_MAX_TOKENS', '1200'))
    timeout: float = float(os.getenv('MODEL_TIMEOUT_SECONDS', '30'))
    max_steps: int = 12
    execution_timeout: float = float(os.getenv('EXECUTION_TIMEOUT_SECONDS', '180'))
    cookie_secure: bool = os.getenv('COOKIE_SECURE', 'false') == 'true'
    allowed_origin: str = os.getenv('APP_ORIGIN', 'http://localhost:3102')

settings = Settings()
if not 1 <= settings.timeout <= 120 or not 1 <= settings.max_tokens <= 8192 or not 10 <= settings.execution_timeout <= 900:
    raise ValueError('Timeout/token/execution limits are outside supported bounds')
if settings.mode not in {'DEMO', 'LIVE'}:
    raise ValueError('APP_MODE must be DEMO or LIVE')

def live_missing():
    if settings.provider not in {'openai', 'gemini'}:
        return ['MODEL_PROVIDER must be openai or gemini']
    if not settings.model.strip():
        return ['MODEL_NAME must not be empty']
    if settings.provider == 'gemini' and not settings.model.startswith('gemini-'):
        return ['MODEL_NAME must select a Gemini model for Gemini provider']
    if settings.provider == 'openai' and settings.model.startswith('gemini-'):
        return ['MODEL_NAME does not belong to the selected OpenAI provider']
    key = 'OPENAI_API_KEY' if settings.provider == 'openai' else 'GEMINI_API_KEY'
    return [] if os.getenv(key) else [key]
