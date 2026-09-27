from datetime import datetime
from app import db


class TournamentStatus:
    DRAFT = 'draft'
    PENDING = 'pending'
    APPROVED = 'approved'
    UPCOMING = 'upcoming'
    LIVE = 'live'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'


class RoomStatus:
    WAITING = 'waiting'
    ACTIVE = 'active'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'


class MatchStatus:
    SCHEDULED = 'scheduled'
    LIVE = 'live'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'


class ResultStatus:
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'


class Tournament(db.Model):
    __tablename__ = 'tournaments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)
    banner = db.Column(db.String(500), nullable=True)
    description = db.Column(db.Text, nullable=True)
    rules = db.Column(db.Text, nullable=True)
    entry_fee = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    prize_pool = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    max_players = db.Column(db.Integer, default=100)
    current_players = db.Column(db.Integer, default=0)
    start_datetime = db.Column(db.DateTime, nullable=True)
    registration_deadline = db.Column(db.DateTime, nullable=True)
    prize_distribution = db.Column(db.Text, nullable=True)  # JSON string
    status = db.Column(db.String(20), default=TournamentStatus.DRAFT, nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_user_hosted = db.Column(db.Boolean, default=False)  # player-created tournament
    pot_balance = db.Column(db.Numeric(12, 2), default=0)  # From Tournament (blocked)
    payment_qr = db.Column(db.String(500), nullable=True)  # host QR for entry fee
    payment_instructions = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    game = db.relationship('Game', back_populates='tournaments')
    creator = db.relationship('User', foreign_keys=[created_by])
    participants = db.relationship('TournamentParticipant', back_populates='tournament', cascade='all, delete-orphan')
    rooms = db.relationship('Room', back_populates='tournament', cascade='all, delete-orphan')
    matches = db.relationship('Match', back_populates='tournament', cascade='all, delete-orphan')
    prizes = db.relationship('PrizeDistribution', back_populates='tournament', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Tournament {self.name}>'


class TournamentParticipant(db.Model):
    __tablename__ = 'tournament_participants'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    game_id_record = db.Column(db.Integer, db.ForeignKey('game_ids.id'), nullable=True)
    entry_transaction_id = db.Column(db.Integer, db.ForeignKey('wallet_transactions.id'), nullable=True)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, joined, disqualified, winner
    payment_ss = db.Column(db.String(500), nullable=True)
    payment_verified = db.Column(db.Boolean, default=False)
    payment_note = db.Column(db.String(255), nullable=True)

    tournament = db.relationship('Tournament', back_populates='participants')
    user = db.relationship('User', back_populates='tournament_participations')
    game_id_entry = db.relationship('GameID')
    entry_transaction = db.relationship('WalletTransaction')

    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'user_id', name='uq_tournament_user'),
    )

    def __repr__(self):
        return f'<TournamentParticipant t={self.tournament_id} u={self.user_id}>'


class Room(db.Model):
    __tablename__ = 'rooms'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    opponent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    entry_fee = db.Column(db.Numeric(12, 2), default=0)
    stake_amount = db.Column(db.Numeric(12, 2), default=0)  # 1v1 wager per player
    is_public = db.Column(db.Boolean, default=True)
    is_challenge = db.Column(db.Boolean, default=False)  # 1v1 challenge room
    host_plays = db.Column(db.Boolean, default=True)  # host is also a player
    cover_image = db.Column(db.String(500), nullable=True)  # room/tournament room photo
    room_id = db.Column(db.String(100), nullable=True)
    password = db.Column(db.String(100), nullable=True)
    match_time = db.Column(db.DateTime, nullable=True)
    instructions = db.Column(db.Text, nullable=True)
    max_players = db.Column(db.Integer, default=50)
    current_players = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default=RoomStatus.WAITING)
    # Settlement (loser pays winner via OTP)
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    loser_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    host_screenshot = db.Column(db.String(500), nullable=True)
    opponent_screenshot = db.Column(db.String(500), nullable=True)
    claim_screenshot = db.Column(db.String(500), nullable=True)  # winner proof for host verify
    settlement_otp = db.Column(db.String(10), nullable=True)
    settlement_otp_expires = db.Column(db.DateTime, nullable=True)
    pending_transfer_amount = db.Column(db.Numeric(12, 2), nullable=True)
    host_hold_txn_id = db.Column(db.Integer, nullable=True)
    opponent_hold_txn_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tournament = db.relationship('Tournament', back_populates='rooms')
    game = db.relationship('Game')
    creator = db.relationship('User', foreign_keys=[created_by])
    opponent = db.relationship('User', foreign_keys=[opponent_id])
    winner = db.relationship('User', foreign_keys=[winner_id])
    loser = db.relationship('User', foreign_keys=[loser_id])

    def __repr__(self):
        return f'<Room {self.name}>'


class Match(db.Model):
    __tablename__ = 'matches'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False, index=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=True)
    name = db.Column(db.String(100), nullable=True)
    match_number = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default=MatchStatus.SCHEDULED)
    scheduled_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tournament = db.relationship('Tournament', back_populates='matches')
    room = db.relationship('Room')
    results = db.relationship('MatchResult', back_populates='match', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Match {self.id} tournament={self.tournament_id}>'


class MatchResult(db.Model):
    __tablename__ = 'match_results'

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False, index=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False, index=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    proof_screenshot = db.Column(db.String(500), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default=ResultStatus.PENDING, index=True)
    submitted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)

    match = db.relationship('Match', back_populates='results')
    tournament = db.relationship('Tournament')
    winner = db.relationship('User', foreign_keys=[winner_id])
    submitter = db.relationship('User', foreign_keys=[submitted_by])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])

    def __repr__(self):
        return f'<MatchResult {self.id} winner={self.winner_id}>'


class PrizeDistribution(db.Model):
    __tablename__ = 'prize_distributions'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False, index=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=True)
    match_result_id = db.Column(db.Integer, db.ForeignKey('match_results.id'), nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    previous_balance = db.Column(db.Numeric(12, 2), nullable=False)
    new_balance = db.Column(db.Numeric(12, 2), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey('wallet_transactions.id'), nullable=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reference = db.Column(db.String(100), nullable=True)
    approved_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tournament = db.relationship('Tournament', back_populates='prizes')
    match = db.relationship('Match')
    match_result = db.relationship('MatchResult')
    winner = db.relationship('User', foreign_keys=[winner_id])
    admin = db.relationship('User', foreign_keys=[admin_id])
    transaction = db.relationship('WalletTransaction')

    def __repr__(self):
        return f'<PrizeDistribution {self.id} amount={self.amount}>'
