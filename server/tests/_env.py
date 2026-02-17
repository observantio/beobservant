import os


def ensure_test_env() -> None:
    os.environ.setdefault("DATABASE_URL", "postgresql://safeuser:safePass_123@db:5432/beobservant")
    os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
    os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "true")
    os.environ.setdefault("JWT_ALGORITHM", "RS256")
