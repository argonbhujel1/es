from datetime import datetime
from decimal import Decimal
from app import db
from app.models.payment import WithdrawalRequest, WithdrawalStatus
from app.models.audit import AuditLog
from app.services.wallet_service import (
    hold_balance, release_hold, complete_withdrawal_paid, WalletServiceError
)
from app.services.notification_service import notify


def create_withdrawal(user_id, amount, account_name, account_number,
                      payment_method_id=None, payment_details=None,
                      user_qr=None, note=None):
    amount = Decimal(str(amount)).quantize(Decimal('0.01'))
    if amount <= 0:
        raise WalletServiceError('Invalid amount')

    req = WithdrawalRequest(
        user_id=user_id,
        payment_method_id=payment_method_id,
        amount=amount,
        account_name=account_name,
        account_number=account_number,
        payment_details=payment_details,
        user_qr=user_qr,
        note=note,
        status=WithdrawalStatus.PENDING
    )
    db.session.add(req)
    db.session.flush()

    # Hold balance
    hold_txn, _ = hold_balance(
        user_id=user_id,
        amount=amount,
        actor_id=user_id,
        reference=f'WD-{req.id}',
        reason=f'Withdrawal request #{req.id}',
        related_id=req.id,
        related_type='withdrawal_request'
    )
    req.hold_transaction_id = hold_txn.id

    notify(
        user_id,
        'Withdrawal Submitted',
        f'Your withdrawal request of Rs.{amount} has been submitted. Amount is held until processed.',
        'withdrawal',
        '/wallet'
    )
    return req


def set_withdrawal_status(request_id, admin_id, status, reason=None, admin_note=None, ip=None):
    req = WithdrawalRequest.query.get(request_id)
    if not req:
        raise WalletServiceError('Withdrawal not found')

    old_status = req.status
    req.status = status
    req.reviewed_by = admin_id
    req.reviewed_at = datetime.utcnow()
    if reason:
        req.rejection_reason = reason
    if admin_note:
        req.admin_note = admin_note

    if status == WithdrawalStatus.REJECTED or status == WithdrawalStatus.CANCELLED:
        release_hold(
            user_id=req.user_id,
            amount=req.amount,
            actor_id=admin_id,
            reference=f'WD-{req.id}',
            reason=reason or f'Withdrawal {status}',
            related_id=req.id,
            related_type='withdrawal_request'
        )
        notify(
            req.user_id,
            f'Withdrawal {status.title()}',
            f'Your withdrawal of Rs.{req.amount} was {status}. ' + (f'Reason: {reason}' if reason else ''),
            'withdrawal',
            '/wallet'
        )
    elif status == WithdrawalStatus.PROCESSING:
        notify(req.user_id, 'Withdrawal Processing', f'Your withdrawal of Rs.{req.amount} is being processed.', 'withdrawal', '/wallet')
    elif status == WithdrawalStatus.APPROVED:
        notify(req.user_id, 'Withdrawal Approved', f'Your withdrawal of Rs.{req.amount} has been approved.', 'withdrawal', '/wallet')

    audit = AuditLog(
        actor_id=admin_id,
        action=f'WITHDRAWAL_{status.upper()}',
        target_type='withdrawal_request',
        target_id=req.id,
        amount=req.amount,
        old_value=old_status,
        new_value=status,
        reason=reason or admin_note,
        ip_address=ip
    )
    db.session.add(audit)
    return req


def mark_withdrawal_paid(request_id, admin_id, ip=None):
    req = WithdrawalRequest.query.get(request_id)
    if not req:
        raise WalletServiceError('Withdrawal not found')
    if req.status not in (WithdrawalStatus.APPROVED, WithdrawalStatus.PROCESSING, WithdrawalStatus.PENDING):
        raise WalletServiceError(f'Cannot mark paid from status {req.status}')

    paid_txn, _ = complete_withdrawal_paid(
        user_id=req.user_id,
        amount=req.amount,
        actor_id=admin_id,
        reference=f'WD-{req.id}',
        reason=f'Withdrawal #{req.id} paid',
        related_id=req.id,
        related_type='withdrawal_request'
    )

    req.status = WithdrawalStatus.PAID
    req.reviewed_by = admin_id
    req.reviewed_at = datetime.utcnow()
    req.paid_transaction_id = paid_txn.id

    audit = AuditLog(
        actor_id=admin_id,
        action='WITHDRAWAL_PAID',
        target_type='withdrawal_request',
        target_id=req.id,
        amount=req.amount,
        ip_address=ip
    )
    db.session.add(audit)

    notify(
        req.user_id,
        'Withdrawal Paid',
        f'Your withdrawal of Rs.{req.amount} has been paid successfully.',
        'withdrawal',
        '/wallet'
    )
    return req, paid_txn
