import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get(
        'SECRET_KEY',
        'dev-secret-key-change-in-production-esports-arena'
    )

    DATABASE_URL = os.environ.get('DATABASE_URL')

    if DATABASE_URL:
        if DATABASE_URL.startswith('postgres://'):
            DATABASE_URL = DATABASE_URL.replace(
                'postgres://',
                'postgresql://',
                1
            )
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR}/esports_arena.db"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    ALLOWED_EXTENSIONS = {
        'png',
        'jpg',
        'jpeg',
        'gif',
        'webp'
    }

    DEFAULT_COMMISSION_RATE = 2.0

    MIN_DEPOSIT = 100
    MAX_DEPOSIT = 50000

    MIN_WITHDRAWAL = 100
    MAX_WITHDRAWAL = 50000

    PERMANENT_SESSION_LIFETIME = 86400

    SESSION_COOKIE_SECURE = (
        os.environ.get('FLASK_ENV') == 'production'
    )

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    MAIL_SERVER = os.environ.get(
        'MAIL_SERVER',
        'smtp.gmail.com'
    )

    MAIL_PORT = int(
        os.environ.get('MAIL_PORT', 587)
    )

    MAIL_USE_TLS = os.environ.get(
        'MAIL_USE_TLS',
        'true'
    ).lower() in ('1', 'true', 'yes')

    MAIL_USERNAME = os.environ.get(
        'MAIL_USERNAME',
        'Esports.info@argan.com.np'
    )

    MAIL_PASSWORD = os.environ.get(
        'MAIL_PASSWORD',
        ''
    )

    MAIL_DEFAULT_SENDER = os.environ.get(
        'MAIL_DEFAULT_SENDER',
        'Esports.info@argan.com.np'
    )

    ADMIN_EMAIL = os.environ.get(
        'ADMIN_EMAIL',
        'info@argan.com.np'
    )


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
