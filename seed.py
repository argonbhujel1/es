"""Seed ESPORTS ARENA database with sample data."""
from app import create_app, db
from app.models.user import User, Role
from app.models.wallet import Wallet
from app.models.game import Game
from app.models.payment import PaymentMethod
from app.models.tournament import Tournament, TournamentStatus
from app.models.news import News
from decimal import Decimal
from datetime import datetime, timedelta

app = create_app('development')

with app.app_context():
    db.create_all()

    if User.query.filter_by(username='admin').first():
        print('Already seeded.')
    else:
        admin = User(username='admin', email='admin@esportsarena.com', full_name='Admin', role=Role.ADMIN)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.flush()
        db.session.add(Wallet(user_id=admin.id, balance=Decimal('0')))

        player = User(username='player1', email='player1@test.com', full_name='Test Player', role=Role.PLAYER, phone='9800000001')
        player.set_password('player123')
        db.session.add(player)
        db.session.flush()
        db.session.add(Wallet(user_id=player.id, balance=Decimal('500'), total_deposited=Decimal('500')))

        player2 = User(username='player2', email='player2@test.com', full_name='Test Player 2', role=Role.PLAYER, phone='9800000003')
        player2.set_password('player123')
        db.session.add(player2)
        db.session.flush()
        db.session.add(Wallet(user_id=player2.id, balance=Decimal('500'), total_deposited=Decimal('500')))

        agent_user = User(username='agent1', email='agent1@test.com', full_name='Test Agent', role=Role.AGENT, phone='9800000002')
        agent_user.set_password('agent123')
        db.session.add(agent_user)
        db.session.flush()
        db.session.add(Wallet(user_id=agent_user.id, balance=Decimal('5000'), total_deposited=Decimal('5000')))
        from app.models.agent import AgentProfile
        db.session.add(AgentProfile(user_id=agent_user.id, display_name='Test Agent', contact='9800000002', commission_rate=Decimal('2.0')))

        games_data = [
            ('Free Fire', 'free-fire', 'Garena Free Fire — battle royale mobile', 'images/games/free-fire.png'),
            ('PUBG Mobile', 'pubg-mobile', 'PUBG Mobile — battle royale', 'images/games/pubg-mobile.png'),
            ('eFootball', 'efootball', 'Konami eFootball — football esports', 'images/games/efootball.png'),
            ('Mobile Legends', 'mobile-legends', 'Mobile Legends: Bang Bang — MOBA', 'images/games/mobile-legends.png'),
            ('DLS 26', 'dls-26', 'Dream League Soccer 26 — football', 'images/games/dls-26.png'),
        ]
        for name, slug, desc, icon in games_data:
            db.session.add(Game(
                name=name, slug=slug, description=desc, is_active=True,
                icon='/static/' + icon, banner='/static/' + icon
            ))

        db.session.add(PaymentMethod(
            name='eSewa', type='qr', account_name='ESPORTS ARENA',
            account_number='9800000000', instructions='Send payment and upload screenshot with reference.',
            min_deposit=100, max_deposit=50000, min_withdrawal=100, max_withdrawal=50000, is_active=True
        ))

        ff = Game.query.filter_by(slug='free-fire').first()
        if ff:
            t = Tournament(
                name='Free Fire Weekly Cup',
                slug='free-fire-weekly-cup',
                game_id=ff.id,
                description='Weekly Free Fire tournament. Top 3 win prizes.',
                rules='No hacking. Fair play only.',
                entry_fee=Decimal('50'),
                prize_pool=Decimal('2000'),
                max_players=50,
                status=TournamentStatus.UPCOMING,
                start_datetime=datetime.utcnow() + timedelta(days=3),
                registration_deadline=datetime.utcnow() + timedelta(days=2),
                prize_distribution='1st: 1000 | 2nd: 600 | 3rd: 400',
                created_by=admin.id
            )
            db.session.add(t)

        db.session.add(News(
            title='Welcome to ESPORTS ARENA',
            slug='welcome-to-esports-arena',
            content='ESPORTS ARENA is now live! Join tournaments, compete, and win prizes.',
            author_id=admin.id,
            status='published',
            is_featured=True,
            published_at=datetime.utcnow()
        ))

        db.session.commit()
        print('Seeded successfully!')
        print('Admin: admin / admin123')
        print('Player: player1 / player123')
        print('Player2: player2 / player123')
        print('Agent: agent1 / agent123')
