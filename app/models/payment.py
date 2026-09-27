from datetime import datetime
from app import db


class DepositStatus:
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'


class WithdrawalStatus:
    PENDING = 'pending'
    PROCESSING = 'processing'
    APPROVED = 'approved'
    PAID = 'paid'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'


class DepositType:
    ADMIN = 'admin'
    AGENT = 'agent'


class PaymentMethod(db.Model):
    __tablename__ = 'payment_methods'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), default='qr')  # qr, bank, wallet
    qr_image = db.Column(db.String(500), nullable=True)
    account_name = db.Column(db.String(150), nullable=True)
    account_number = db.Column(db.String(100), nullable=True)
    instructions = db.Column(db.Text, nullable=True)
    min_deposit = db.Column(db.Numeric(12, 2), default=100)
    max_deposit = db.Column(db.Numeric(12, 2), default=50000)
    min_withdrawal = db.Column(db.Numeric(12, 2), default=100)
    max_withdrawal = db.Column(db.Numeric(12, 2), default=50000)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<PaymentMethod {self.name}>'


class DepositRequest(db.Model):
    __tablename__ = 'deposit_requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    payment_method_id = db.Column(db.Integer, db.ForeignKey('payment_methods.id'), nullable=True)
    deposit_type = db.Column(db.String(20), nullable=False)  # admin / agent
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    reference_number = db.Column(db.String(100), nullable=True)
    screenshot = db.Column(db.String(500), nullable=True)
    note = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default=DepositStatus.PENDING, nullable=False, index=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('wallet_transactions.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], back_populates='deposit_requests')
    agent = db.relationship('User', foreign_keys=[agent_id])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])
    payment_method = db.relationship('PaymentMethod')
    transaction = db.relationship('WalletTransaction', foreign_keys=[transaction_id])

    def __repr__(self):
        return f'<DepositRequest {self.id} {self.amount} {self.status}>'


class WithdrawalRequest(db.Model):
    __tablename__ = 'withdrawal_requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    payment_method_id = db.Column(db.Integer, db.ForeignKey('payment_methods.id'), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    account_name = db.Column(db.String(150), nullable=False)
    account_number = db.Column(db.String(100), nullable=False)
    payment_details = db.Column(db.Text, nullable=True)
    user_qr = db.Column(db.String(500), nullable=True)
    note = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default=WithdrawalStatus.PENDING, nullable=False, index=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    admin_note = db.Column(db.Text, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    hold_transaction_id = db.Column(db.Integer, db.ForeignKey('wallet_transactions.id'), nullable=True)
    paid_transaction_id = db.Column(db.Integer, db.ForeignKey('wallet_transactions.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], back_populates='withdrawal_requests')
    payment_method = db.relationship('PaymentMethod')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])
    hold_transaction = db.relationship('WalletTransaction', foreign_keys=[hold_transaction_id])
    paid_transaction = db.relationship('WalletTransaction', foreign_keys=[paid_transaction_id])

    def __repr__(self):
        return f'<WithdrawalRequest {self.id} {self.amount} {self.status}>'
