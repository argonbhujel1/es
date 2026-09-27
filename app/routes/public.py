from flask import Blueprint, render_template, request
from app.models.tournament import Tournament, TournamentStatus, Room
from app.models.game import Game
from app.models.news import News
from app.services.leaderboard_service import get_leaderboard

public_bp = Blueprint('public', __name__)


@public_bp.route('/')
def index():
    # Top prize tournaments first
    tournaments = Tournament.query.filter(
        Tournament.status.in_([TournamentStatus.UPCOMING, TournamentStatus.LIVE, TournamentStatus.APPROVED])
    ).order_by(Tournament.prize_pool.desc(), Tournament.start_datetime.asc()).limit(6).all()
    # FCFO rooms: first come first out — oldest waiting first, max 5
    rooms = Room.query.filter(
        Room.status.in_(['waiting', 'joined']),
        (Room.is_public == True) | (Room.is_public.is_(None))
    ).order_by(Room.created_at.asc()).limit(5).all()
    games = Game.query.filter_by(is_active=True).all()
    news = News.query.filter_by(status='published').order_by(News.published_at.desc()).limit(3).all()
    top_players = get_leaderboard(limit=5)
    return render_template('public/index.html',
                           tournaments=tournaments, rooms=rooms, games=games,
                           news=news, top_players=top_players)


@public_bp.route('/games')
def games():
    games_list = Game.query.filter_by(is_active=True).all()
    return render_template('public/games.html', games=games_list)


@public_bp.route('/games/<slug>')
def game_detail(slug):
    game = Game.query.filter_by(slug=slug, is_active=True).first_or_404()
    tournaments = Tournament.query.filter(
        Tournament.game_id == game.id,
        Tournament.status.in_([TournamentStatus.UPCOMING, TournamentStatus.LIVE,
                               TournamentStatus.APPROVED, TournamentStatus.COMPLETED])
    ).order_by(Tournament.prize_pool.desc()).all()
    rooms = Room.query.filter(
        Room.game_id == game.id,
        Room.status.in_(['waiting', 'joined', 'active', 'playing']),
        (Room.is_public == True) | (Room.is_public.is_(None))
    ).order_by(Room.created_at.asc()).all()
    return render_template('public/game_detail.html', game=game,
                           tournaments=tournaments, rooms=rooms)


@public_bp.route('/rooms')
def rooms():
    # FCFO list: oldest open rooms first
    rooms_list = Room.query.filter(
        Room.status.in_(['waiting', 'joined', 'active', 'playing']),
        (Room.is_public == True) | (Room.is_public.is_(None))
    ).order_by(Room.created_at.asc()).all()
    return render_template('public/rooms.html', rooms=rooms_list)


@public_bp.route('/tournaments')
def tournaments():
    status = request.args.get('status')
    q = Tournament.query
    if status:
        q = q.filter_by(status=status)
    else:
        q = q.filter(Tournament.status.in_([
            TournamentStatus.UPCOMING, TournamentStatus.LIVE,
            TournamentStatus.APPROVED, TournamentStatus.COMPLETED
        ]))
    tournaments_list = q.order_by(Tournament.prize_pool.desc(), Tournament.start_datetime.desc()).all()
    return render_template('public/tournaments.html', tournaments=tournaments_list)


@public_bp.route('/tournaments/<slug>')
def tournament_detail(slug):
    tournament = Tournament.query.filter_by(slug=slug).first_or_404()
    return render_template('public/tournament_detail.html', tournament=tournament)


@public_bp.route('/leaderboard')
def leaderboard():
    period = request.args.get('period', 'overall')
    game_id = request.args.get('game_id', type=int)
    entries = get_leaderboard(period=period, game_id=game_id)
    games = Game.query.filter_by(is_active=True).all()
    return render_template('public/leaderboard.html', entries=entries, period=period, games=games, game_id=game_id)


@public_bp.route('/news')
def news_list():
    news_items = News.query.filter_by(status='published').order_by(News.published_at.desc()).all()
    return render_template('public/news.html', news_items=news_items)


@public_bp.route('/news/<slug>')
def news_detail(slug):
    item = News.query.filter_by(slug=slug, status='published').first_or_404()
    return render_template('public/news_detail.html', item=item)
