from datetime import datetime
from app import db


class LeaderboardEntry(db.Model):
    __tablename__ = 'leaderboard_entries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=True, index=True)
    points = db.Column(db.Integer, default=0)
    wins = db.Column(db.Integer, default=0)
    matches_played = db.Column(db.Integer, default=0)
    prize_earned = db.Column(db.Numeric(12, 2), default=0)
    period = db.Column(db.String(20), default='overall')  # overall, weekly, monthly
    period_start = db.Column(db.DateTime, nullable=True)
    period_end = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User')
    game = db.relationship('Game')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'game_id', 'period', name='uq_leaderboard_user_game_period'),
    )

    def __repr__(self):
        return f'<LeaderboardEntry user={self.user_id} points={self.points}>'
