from datetime import datetime
from decimal import Decimal
from app import db
from app.models.payment import DepositRequest, DepositStatus, DepositType
from app.models.wallet import TransactionType
from app.models.agent import AgentCommission, AgentProfile
from app.models.audit import AuditLog
from app.services.wallet_service import credit_wallet, WalletServiceError
from app.services.notification_service import notify, notify_admin


def create_deposit_request(user_id, amount, deposit_type, payment_method_id=None,
                           agent_id=None, reference_number=None, screenshot=None, note=None):
    amount = Decimal(str(amount)).quantize(Decimal('0.01'))
    if amount <= 0:
        raise WalletServiceError('Invalid amount')

    req = DepositRequest(
        user_id=user_id,
        agent_id=agent_id if deposit_type == DepositType.AGENT else None,
        payment_method_id=payment_method_id,
        deposit_type=deposit_type,
        amount=amount,
        reference_number=reference_number,
        screenshot=screenshot,
        note=note,
        status=DepositStatus.PENDING
    )
    db.session.add(req)
    db.session.flush()

    notify(
        user_id,
        'Deposit Request Submitted',
        f'Your deposit request of Rs.{amount} has been submitted and is pending review.',
        'deposit',
        '/wallet'
    )
    try:
        from app.models.user import User
        u = User.query.get(user_id)
        uname = u.username if u else user_id
        notify_admin(
            f'Wallet load request from {uname}',
            f'User {uname} requested deposit of Rs.{amount} (type: {deposit_type}). Review in Admin → Deposits.',
            '/admin/deposits'
        )
    except Exception:
        pass
    return req


def approve_deposit(request_id, reviewer_id, ip=None):
    req = DepositRequest.query.get(request_id)
    if not req:
        raise WalletServiceError('Deposit request not found')
    if req.status != DepositStatus.PENDING:
        raise WalletServiceError(f'Deposit is already {req.status}')

    txn_type = TransactionType.ADMIN_DEPOSIT if req.deposit_type == DepositType.ADMIN else TransactionType.AGENT_DEPOSIT

    txn, wallet = credit_wallet(
        user_id=req.user_id,
        amount=req.amount,
        transaction_type=txn_type,
        actor_id=reviewer_id,
        reference=req.reference_number,
        reason=f'Deposit request #{req.id} approved',
        related_id=req.id,
        related_type='deposit_request',
        update_totals={'total_deposited': req.amount}
    )

    req.status = DepositStatus.APPROVED
    req.reviewed_by = reviewer_id
    req.reviewed_at = datetime.utcnow()
    req.transaction_id = txn.id

    # Agent commission
    if req.deposit_type == DepositType.AGENT and req.agent_id:
        profile = AgentProfile.query.filter_by(user_id=req.agent_id).first()
        if profile:
            rate = Decimal(str(profile.commission_rate or 2))
            commission_amt = (Decimal(str(req.amount)) * rate / Decimal('100')).quantize(Decimal('0.01'))
            commission = AgentCommission(
                agent_id=profile.id,
                transaction_id=txn.id,
                deposit_request_id=req.id,
                amount=req.amount,
                commission_rate=rate,
                commission_amount=commission_amt
            )
            db.session.add(commission)
            profile.total_loads = Decimal(str(profile.total_loads or 0)) + Decimal(str(req.amount))
            profile.total_commission = Decimal(str(profile.total_commission or 0)) + commission_amt

            notify(
                req.agent_id,
                'Deposit Approved - Commission Earned',
                f'Deposit of Rs.{req.amount} approved. Commission: Rs.{commission_amt}',
                'commission'
            )

    audit = AuditLog(
        actor_id=reviewer_id,
        action='DEPOSIT_APPROVED',
        target_type='deposit_request',
        target_id=req.id,
        amount=req.amount,
        reason=f'Approved deposit for user {req.user_id}',
        ip_address=ip
    )
    db.session.add(audit)

    notify(
        req.user_id,
        'Deposit Approved',
        f'Your deposit of Rs.{req.amount} has been approved and credited to your wallet.',
        'deposit',
        '/wallet'
    )
    return req, txn


def reject_deposit(request_id, reviewer_id, reason, ip=None):
    req = DepositRequest.query.get(request_id)
    if not req:
        raise WalletServiceError('Deposit request not found')
    if req.status != DepositStatus.PENDING:
        raise WalletServiceError(f'Deposit is already {req.status}')

    req.status = DepositStatus.REJECTED
    req.reviewed_by = reviewer_id
    req.reviewed_at = datetime.utcnow()
    req.rejection_reason = reason

    audit = AuditLog(
        actor_id=reviewer_id,
        action='DEPOSIT_REJECTED',
        target_type='deposit_request',
        target_id=req.id,
        amount=req.amount,
        reason=reason,
        ip_address=ip
    )
    db.session.add(audit)

    notify(
        req.user_id,
        'Deposit Rejected',
        f'Your deposit request of Rs.{req.amount} was rejected. Reason: {reason}',
        'deposit',
        '/wallet'
    )
    return req
