from datetime import datetime
from app import db


class TransactionType:
    ADMIN_DEPOSIT = 'ADMIN_DEPOSIT'
    AGENT_DEPOSIT = 'AGENT_DEPOSIT'
    AGENT_LOAD = 'AGENT_LOAD'
    ADMIN_DIRECT_LOAD = 'ADMIN_DIRECT_LOAD'
    ADMIN_DIRECT_DEDUCT = 'ADMIN_DIRECT_DEDUCT'
    ADMIN_ADJUSTMENT = 'ADMIN_ADJUSTMENT'
    TOURNAMENT_ENTRY = 'TOURNAMENT_ENTRY'
    PRIZE_REWARD = 'PRIZE_REWARD'
    WITHDRAWAL_HOLD = 'WITHDRAWAL_HOLD'
    WITHDRAWAL_RELEASE = 'WITHDRAWAL_RELEASE'
    WITHDRAWAL_PAID = 'WITHDRAWAL_PAID'
    REFUND = 'REFUND'
    COMMISSION = 'COMMISSION'
    AGENT_FLOAT_LOAD = 'AGENT_FLOAT_LOAD'  # admin loads agent float
    AGENT_FLOAT_SPEND = 'AGENT_FLOAT_SPEND'
    ROOM_TRANSFER = 'ROOM_TRANSFER'  # loser pays winner in challenge room
    ROOM_STAKE_HOLD = 'ROOM_STAKE_HOLD'
    ROOM_STAKE_RELEASE = 'ROOM_STAKE_RELEASE'
    TOURNAMENT_POT = 'TOURNAMENT_POT'  # entry into tournament pot
    TOURNAMENT_POT_PRIZE = 'TOURNAMENT_POT_PRIZE'
    TOURNAMENT_POT_CLEAR = 'TOURNAMENT_POT_CLEAR'


class TransactionStatus:
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    HELD = 'held'
    RELEASED = 'released'


class Wallet(db.Model):
    __tablename__ = 'wallets'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False, index=True)
    balance = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    held_balance = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    total_deposited = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    total_withdrawn = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    total_tournament_spent = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    total_prize_won = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', back_populates='wallet')
    transactions = db.relationship('WalletTransaction', back_populates='wallet', cascade='all, delete-orphan')

    @property
    def available_balance(self):
        return float(self.balance) - float(self.held_balance)

    def __repr__(self):
        return f'<Wallet user_id={self.user_id} balance={self.balance}>'


class WalletTransaction(db.Model):
    __tablename__ = 'wallet_transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    wallet_id = db.Column(db.Integer, db.ForeignKey('wallets.id'), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    type = db.Column(db.String(50), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    previous_balance = db.Column(db.Numeric(12, 2), nullable=False)
    new_balance = db.Column(db.Numeric(12, 2), nullable=False)
    reference = db.Column(db.String(100), nullable=True, index=True)
    reason = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), default=TransactionStatus.COMPLETED, nullable=False, index=True)
    related_id = db.Column(db.Integer, nullable=True)  # deposit_id, withdrawal_id, tournament_id etc
    related_type = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', foreign_keys=[user_id], back_populates='transactions')
    actor = db.relationship('User', foreign_keys=[actor_id])
    wallet = db.relationship('Wallet', back_populates='transactions')

    def __repr__(self):
        return f'<WalletTransaction {self.id} {self.type} {self.amount}>'
