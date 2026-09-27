from datetime import datetime
from app import db


class Game(db.Model):
    __tablename__ = 'games'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    banner = db.Column(db.String(500), nullable=True)
    icon = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    game_ids = db.relationship('GameID', back_populates='game', cascade='all, delete-orphan')
    tournaments = db.relationship('Tournament', back_populates='game')

    def __repr__(self):
        return f'<Game {self.name}>'


class GameID(db.Model):
    __tablename__ = 'game_ids'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)
    game_uid = db.Column(db.String(100), nullable=False)
    game_username = db.Column(db.String(100), nullable=True)
    server_region = db.Column(db.String(50), nullable=True)
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', back_populates='game_ids')
    game = db.relationship('Game', back_populates='game_ids')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'game_id', 'game_uid', name='uq_user_game_uid'),
    )

    def __repr__(self):
        return f'<GameID {self.game_uid} for user {self.user_id}>'
