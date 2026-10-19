import os

SECRET_KEY = os.environ.get("APP_SECRET_KEY", "")
if not SECRET_KEY:
    # Nunca use um valor fixo em produção — falha alto e cedo.
    import secrets
    SECRET_KEY = secrets.token_hex(32)

SESSION_COOKIE_NAME = "nc_session"
CSRF_COOKIE_NAME = "nc_csrf"
SESSION_LIFETIME_MINUTES = int(os.environ.get("SESSION_LIFETIME_MINUTES", "480"))       # 8h deslizante
SESSION_ABSOLUTE_MAX_HOURS = int(os.environ.get("SESSION_ABSOLUTE_MAX_HOURS", "24"))    # limite absoluto

LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))
LOGIN_WINDOW_MINUTES = int(os.environ.get("LOGIN_WINDOW_MINUTES", "15"))

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "15"))

COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"

BOOTSTRAP_ADMIN_EMAIL = os.environ.get("BOOTSTRAP_ADMIN_EMAIL")
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
BOOTSTRAP_ADMIN_NOME = os.environ.get("BOOTSTRAP_ADMIN_NOME", "Administrador do Sistema")

ADMIN_NOTIFICATION_EMAIL = os.environ.get("ADMIN_NOTIFICATION_EMAIL", "admin@qualimatch.local")
PASSWORD_RESET_MINUTES = int(os.environ.get("PASSWORD_RESET_MINUTES", "30"))
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "").rstrip("/")
