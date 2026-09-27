from app.models.leaderboard import LeaderboardEntry
from app import db


def get_leaderboard(period='overall', game_id=None, limit=50):
    q = LeaderboardEntry.query.filter_by(period=period)
    if game_id:
        q = q.filter_by(game_id=game_id)
    else:
        q = q.filter(LeaderboardEntry.game_id.is_(None))
    return q.order_by(LeaderboardEntry.points.desc(), LeaderboardEntry.wins.desc()).limit(limit).all()
