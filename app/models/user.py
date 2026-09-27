from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager


class Role:
    PLAYER = 'player'
    AGENT = 'agent'
    ADMIN = 'admin'


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120), nullable=True)
    avatar = db.Column(db.String(500), nullable=True)
    role = db.Column(db.String(20), default=Role.PLAYER, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    # Relationships
    wallet = db.relationship('Wallet', back_populates='user', uselist=False, cascade='all, delete-orphan')
    game_ids = db.relationship('GameID', back_populates='user', cascade='all, delete-orphan')
    deposit_requests = db.relationship('DepositRequest', foreign_keys='DepositRequest.user_id', back_populates='user', cascade='all, delete-orphan')
    withdrawal_requests = db.relationship('WithdrawalRequest', foreign_keys='WithdrawalRequest.user_id', back_populates='user', cascade='all, delete-orphan')
    agent_application = db.relationship('AgentApplication', foreign_keys='AgentApplication.user_id', back_populates='user', uselist=False, cascade='all, delete-orphan')
    agent_profile = db.relationship('AgentProfile', back_populates='user', uselist=False, cascade='all, delete-orphan')
    tournament_participations = db.relationship('TournamentParticipant', back_populates='user', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', back_populates='user', cascade='all, delete-orphan')
    transactions = db.relationship('WalletTransaction', foreign_keys='WalletTransaction.user_id', back_populates='user')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == Role.ADMIN

    def is_agent(self):
        return self.role == Role.AGENT

    def is_player(self):
        return self.role == Role.PLAYER

    def can_access_admin(self):
        return self.is_admin() and self.is_active and not self.is_blocked

    def can_access_agent(self):
        return self.is_agent() and self.is_active and not self.is_blocked

    def __repr__(self):
        return f'<User {self.username}>'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
