from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from config import config
import cloudinary
import os
from pathlib import Path


db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()


login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'warning'
login_manager.login_message = 'Please log in to access this page.'


def create_app(config_name=None):

    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    if config_name not in config:
        config_name = 'default'


    BASE_DIR = Path(__file__).resolve().parent


    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static")
    )


    app.config.from_object(config[config_name])

    app.config['PROPAGATE_EXCEPTIONS'] = True


    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)


    if app.config.get('CLOUDINARY_CLOUD_NAME'):
        cloudinary.config(
            cloud_name=app.config['CLOUDINARY_CLOUD_NAME'],
            api_key=app.config['CLOUDINARY_API_KEY'],
            api_secret=app.config['CLOUDINARY_API_SECRET']
        )


    # Import models
    from app.models import user, game, tournament, wallet, payment, news, leaderboard, notification, agent, audit


    # Routes
    from app.routes.public import public_bp
    from app.routes.auth import auth_bp
    from app.routes.user import user_bp
    from app.routes.admin import admin_bp
    from app.routes.agent import agent_bp
    from app.routes.wallet import wallet_bp


    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(wallet_bp)


    return app