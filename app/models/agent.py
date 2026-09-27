from datetime import datetime
from app import db


class AgentApplicationStatus:
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'


class AgentApplication(db.Model):
    __tablename__ = 'agent_applications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    address = db.Column(db.Text, nullable=True)
    payment_details = db.Column(db.Text, nullable=True)
    experience = db.Column(db.Text, nullable=True)
    social_links = db.Column(db.Text, nullable=True)
    verification_document = db.Column(db.String(500), nullable=True)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default=AgentApplicationStatus.PENDING, nullable=False, index=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], back_populates='agent_application')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])

    def __repr__(self):
        return f'<AgentApplication {self.id} {self.status}>'


class AgentProfile(db.Model):
    __tablename__ = 'agent_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    display_name = db.Column(db.String(120), nullable=True)
    contact = db.Column(db.String(50), nullable=True)
    payment_qr = db.Column(db.String(500), nullable=True)
    payment_instructions = db.Column(db.Text, nullable=True)
    commission_rate = db.Column(db.Numeric(5, 2), default=2.0)
    is_active = db.Column(db.Boolean, default=True)
    total_loads = db.Column(db.Numeric(12, 2), default=0)
    total_commission = db.Column(db.Numeric(12, 2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', back_populates='agent_profile')
    commissions = db.relationship('AgentCommission', back_populates='agent', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<AgentProfile user_id={self.user_id}>'


class AgentCommission(db.Model):
    __tablename__ = 'agent_commissions'

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agent_profiles.id'), nullable=False, index=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('wallet_transactions.id'), nullable=False)
    deposit_request_id = db.Column(db.Integer, db.ForeignKey('deposit_requests.id'), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)  # load amount
    commission_rate = db.Column(db.Numeric(5, 2), nullable=False)
    commission_amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(20), default='completed')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    agent = db.relationship('AgentProfile', back_populates='commissions')
    transaction = db.relationship('WalletTransaction')
    deposit_request = db.relationship('DepositRequest')

    def __repr__(self):
        return f'<AgentCommission {self.id} {self.commission_amount}>'
