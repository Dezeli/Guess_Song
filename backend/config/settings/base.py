from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BASE_DIR.parent

env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, "unsafe-local-development-key"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, []),
    DATABASE_URL=(str, "postgres://guess_song:guess_song@postgres:5432/guess_song"),
    REDIS_URL=(str, "redis://redis:6379/0"),
    YOUTUBE_API_KEY=(str, ""),
)

environ.Env.read_env(ROOT_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "channels",
    "corsheaders",
]

LOCAL_APPS = [
    "apps.core",
    "apps.catalog",
    "apps.ingestion",
    "apps.moderation",
    "apps.quizzes",
    "apps.rooms",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db("DATABASE_URL"),
}

REDIS_URL = env("REDIS_URL")
YOUTUBE_API_KEY = env("YOUTUBE_API_KEY")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
