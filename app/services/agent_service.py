from datetime import datetime
from app import db
from app.models.user import User, Role
from app.models.agent import AgentApplication, AgentApplicationStatus, AgentProfile
from app.models.audit import AuditLog
from app.services.notification_service import notify
from app.services.wallet_service import WalletServiceError


def apply_for_agent(user_id, data):
    existing = AgentApplication.query.filter_by(user_id=user_id).first()
    if existing and existing.status == AgentApplicationStatus.PENDING:
        raise WalletServiceError('You already have a pending application')
    if existing and existing.status == AgentApplicationStatus.APPROVED:
        raise WalletServiceError('You are already an agent')

    app = AgentApplication(
        user_id=user_id,
        full_name=data.get('full_name'),
        phone=data.get('phone'),
        email=data.get('email'),
        address=data.get('address'),
        payment_details=data.get('payment_details'),
        experience=data.get('experience'),
        social_links=data.get('social_links'),
        verification_document=data.get('verification_document'),
        message=data.get('message'),
        status=AgentApplicationStatus.PENDING
    )
    db.session.add(app)
    return app


def approve_agent(application_id, admin_id, commission_rate=2.0, ip=None):
    app = AgentApplication.query.get(application_id)
    if not app:
        raise WalletServiceError('Application not found')
    if app.status != AgentApplicationStatus.PENDING:
        raise WalletServiceError(f'Application is already {app.status}')

    user = User.query.get(app.user_id)
    if not user:
        raise WalletServiceError('User not found')

    app.status = AgentApplicationStatus.APPROVED
    app.reviewed_by = admin_id
    app.reviewed_at = datetime.utcnow()

    user.role = Role.AGENT

    profile = AgentProfile.query.filter_by(user_id=user.id).first()
    if not profile:
        profile = AgentProfile(
            user_id=user.id,
            display_name=app.full_name,
            contact=app.phone,
            commission_rate=commission_rate
        )
        db.session.add(profile)
    else:
        profile.is_active = True
        profile.commission_rate = commission_rate

    audit = AuditLog(
        actor_id=admin_id,
        action='AGENT_APPROVED',
        target_type='user',
        target_id=user.id,
        reason=f'Agent application #{app.id} approved',
        ip_address=ip
    )
    db.session.add(audit)

    notify(user.id, 'Agent Application Approved', 'Congratulations! You are now a Wallet Agent.', 'agent', '/agent')
    return app


def reject_agent(application_id, admin_id, reason, ip=None):
    app = AgentApplication.query.get(application_id)
    if not app:
        raise WalletServiceError('Application not found')
    if app.status != AgentApplicationStatus.PENDING:
        raise WalletServiceError(f'Application is already {app.status}')

    app.status = AgentApplicationStatus.REJECTED
    app.reviewed_by = admin_id
    app.reviewed_at = datetime.utcnow()
    app.rejection_reason = reason

    audit = AuditLog(
        actor_id=admin_id,
        action='AGENT_REJECTED',
        target_type='agent_application',
        target_id=app.id,
        reason=reason,
        ip_address=ip
    )
    db.session.add(audit)

    notify(app.user_id, 'Agent Application Rejected', f'Your agent application was rejected. Reason: {reason}', 'agent')
    return app
