from decimal import Decimal
from app import db
from app.models.wallet import Wallet, WalletTransaction, TransactionType, TransactionStatus
from app.models.audit import AuditLog
from sqlalchemy import select



class WalletServiceError(Exception):
    pass


class InsufficientBalanceError(WalletServiceError):
    pass


class InvalidAmountError(WalletServiceError):
    pass


def get_or_create_wallet(user_id):
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=Decimal('0'), held_balance=Decimal('0'))
        db.session.add(wallet)
        db.session.flush()
    return wallet


def _to_decimal(amount):
    if amount is None:
        raise InvalidAmountError('Amount is required')
    try:
        d = Decimal(str(amount))
    except Exception:
        raise InvalidAmountError('Invalid amount')
    if d <= 0:
        raise InvalidAmountError('Amount must be greater than zero')
    return d.quantize(Decimal('0.01'))


def credit_wallet(user_id, amount, transaction_type, actor_id=None, reference=None,
                  reason=None, related_id=None, related_type=None, update_totals=None):
    """
    Atomically credit wallet. Creates WalletTransaction.
    update_totals: dict with keys like 'total_deposited', 'total_prize_won' etc.
    """
    amount = _to_decimal(amount)
    wallet = db.session.execute(
        select(Wallet).where(Wallet.user_id == user_id).with_for_update()
    ).scalar_one_or_none()

    if not wallet:
        wallet = Wallet(user_id=user_id, balance=Decimal('0'), held_balance=Decimal('0'))
        db.session.add(wallet)
        db.session.flush()
        wallet = db.session.execute(
            select(Wallet).where(Wallet.user_id == user_id).with_for_update()
        ).scalar_one()

    previous = Decimal(str(wallet.balance))
    new_balance = previous + amount

    txn = WalletTransaction(
        user_id=user_id,
        wallet_id=wallet.id,
        actor_id=actor_id,
        type=transaction_type,
        amount=amount,
        previous_balance=previous,
        new_balance=new_balance,
        reference=reference,
        reason=reason,
        status=TransactionStatus.COMPLETED,
        related_id=related_id,
        related_type=related_type
    )
    wallet.balance = new_balance

    if update_totals:
        for key, val in update_totals.items():
            if hasattr(wallet, key):
                current = Decimal(str(getattr(wallet, key) or 0))
                setattr(wallet, key, current + Decimal(str(val)))

    db.session.add(txn)
    db.session.flush()
    return txn, wallet


def debit_wallet(user_id, amount, transaction_type, actor_id=None, reference=None,
                 reason=None, related_id=None, related_type=None, update_totals=None,
                 allow_held=False):
    """
    Atomically debit available balance.
    """
    amount = _to_decimal(amount)
    wallet = db.session.execute(
        select(Wallet).where(Wallet.user_id == user_id).with_for_update()
    ).scalar_one_or_none()

    if not wallet:
        raise InsufficientBalanceError('Wallet not found')

    previous = Decimal(str(wallet.balance))
    held = Decimal(str(wallet.held_balance or 0))
    available = previous - held if not allow_held else previous

    if available < amount:
        raise InsufficientBalanceError(
            f'Insufficient balance. Available: {available}, Required: {amount}'
        )

    new_balance = previous - amount

    txn = WalletTransaction(
        user_id=user_id,
        wallet_id=wallet.id,
        actor_id=actor_id,
        type=transaction_type,
        amount=amount,
        previous_balance=previous,
        new_balance=new_balance,
        reference=reference,
        reason=reason,
        status=TransactionStatus.COMPLETED,
        related_id=related_id,
        related_type=related_type
    )
    wallet.balance = new_balance

    if update_totals:
        for key, val in update_totals.items():
            if hasattr(wallet, key):
                current = Decimal(str(getattr(wallet, key) or 0))
                setattr(wallet, key, current + Decimal(str(val)))

    db.session.add(txn)
    db.session.flush()
    return txn, wallet


def hold_balance(user_id, amount, actor_id=None, reference=None, reason=None,
                 related_id=None, related_type=None):
    """
    Hold amount from available balance (for withdrawals).
    Does not change total balance, only held_balance.
    Creates WITHDRAWAL_HOLD transaction for audit.
    """
    amount = _to_decimal(amount)
    wallet = db.session.execute(
        select(Wallet).where(Wallet.user_id == user_id).with_for_update()
    ).scalar_one_or_none()

    if not wallet:
        raise InsufficientBalanceError('Wallet not found')

    previous = Decimal(str(wallet.balance))
    held = Decimal(str(wallet.held_balance or 0))
    available = previous - held

    if available < amount:
        raise InsufficientBalanceError(
            f'Insufficient available balance. Available: {available}, Required: {amount}'
        )

    wallet.held_balance = held + amount

    txn = WalletTransaction(
        user_id=user_id,
        wallet_id=wallet.id,
        actor_id=actor_id,
        type=TransactionType.WITHDRAWAL_HOLD,
        amount=amount,
        previous_balance=previous,
        new_balance=previous,  # balance unchanged
        reference=reference,
        reason=reason or 'Withdrawal hold',
        status=TransactionStatus.HELD,
        related_id=related_id,
        related_type=related_type
    )
    db.session.add(txn)
    db.session.flush()
    return txn, wallet


def release_hold(user_id, amount, actor_id=None, reference=None, reason=None,
                 related_id=None, related_type=None):
    """
    Release held amount back to available.
    """
    amount = _to_decimal(amount)
    wallet = db.session.execute(
        select(Wallet).where(Wallet.user_id == user_id).with_for_update()
    ).scalar_one_or_none()

    if not wallet:
        raise WalletServiceError('Wallet not found')

    previous = Decimal(str(wallet.balance))
    held = Decimal(str(wallet.held_balance or 0))

    if held < amount:
        amount = held  # release what's held

    wallet.held_balance = held - amount

    txn = WalletTransaction(
        user_id=user_id,
        wallet_id=wallet.id,
        actor_id=actor_id,
        type=TransactionType.WITHDRAWAL_RELEASE,
        amount=amount,
        previous_balance=previous,
        new_balance=previous,
        reference=reference,
        reason=reason or 'Withdrawal hold released',
        status=TransactionStatus.RELEASED,
        related_id=related_id,
        related_type=related_type
    )
    db.session.add(txn)
    db.session.flush()
    return txn, wallet


def complete_withdrawal_paid(user_id, amount, actor_id=None, reference=None, reason=None,
                             related_id=None, related_type=None):
    """
    Finalize withdrawal: reduce held and reduce balance.
    """
    amount = _to_decimal(amount)
    wallet = db.session.execute(
        select(Wallet).where(Wallet.user_id == user_id).with_for_update()
    ).scalar_one_or_none()

    if not wallet:
        raise WalletServiceError('Wallet not found')

    previous = Decimal(str(wallet.balance))
    held = Decimal(str(wallet.held_balance or 0))

    if held < amount:
        raise WalletServiceError(f'Held balance ({held}) less than withdrawal amount ({amount})')

    new_balance = previous - amount
    if new_balance < 0:
        raise InsufficientBalanceError('Would result in negative balance')

    wallet.balance = new_balance
    wallet.held_balance = held - amount
    wallet.total_withdrawn = Decimal(str(wallet.total_withdrawn or 0)) + amount

    txn = WalletTransaction(
        user_id=user_id,
        wallet_id=wallet.id,
        actor_id=actor_id,
        type=TransactionType.WITHDRAWAL_PAID,
        amount=amount,
        previous_balance=previous,
        new_balance=new_balance,
        reference=reference,
        reason=reason or 'Withdrawal paid',
        status=TransactionStatus.COMPLETED,
        related_id=related_id,
        related_type=related_type
    )
    db.session.add(txn)
    db.session.flush()
    return txn, wallet


def admin_direct_load(user_id, amount, admin_id, reason, reference=None, ip=None):
    """Admin direct load - no deposit request needed."""
    amount = _to_decimal(amount)
    if not reason:
        raise WalletServiceError('Reason is required for admin direct load')

    txn, wallet = credit_wallet(
        user_id=user_id,
        amount=amount,
        transaction_type=TransactionType.ADMIN_DIRECT_LOAD,
        actor_id=admin_id,
        reference=reference,
        reason=reason,
        update_totals={'total_deposited': amount}
    )

    audit = AuditLog(
        actor_id=admin_id,
        action='ADMIN_DIRECT_LOAD',
        target_type='user',
        target_id=user_id,
        amount=amount,
        old_value=str(txn.previous_balance),
        new_value=str(txn.new_balance),
        reason=reason,
        ip_address=ip
    )
    db.session.add(audit)
    return txn, wallet


def admin_direct_deduct(user_id, amount, admin_id, reason, reference=None, ip=None):
    """Admin direct deduct."""
    amount = _to_decimal(amount)
    if not reason:
        raise WalletServiceError('Reason is required for admin direct deduct')

    txn, wallet = debit_wallet(
        user_id=user_id,
        amount=amount,
        transaction_type=TransactionType.ADMIN_DIRECT_DEDUCT,
        actor_id=admin_id,
        reference=reference,
        reason=reason
    )

    audit = AuditLog(
        actor_id=admin_id,
        action='ADMIN_DIRECT_DEDUCT',
        target_type='user',
        target_id=user_id,
        amount=amount,
        old_value=str(txn.previous_balance),
        new_value=str(txn.new_balance),
        reason=reason,
        ip_address=ip
    )
    db.session.add(audit)
    return txn, wallet


def admin_adjustment(user_id, amount, admin_id, reason, reference=None, ip=None):
    """Can be positive or negative adjustment. amount can be negative for deduct."""
    from decimal import Decimal as D
    try:
        amt = D(str(amount)).quantize(D('0.01'))
    except Exception:
        raise InvalidAmountError('Invalid amount')

    if amt == 0:
        raise InvalidAmountError('Amount cannot be zero')

    if not reason:
        raise WalletServiceError('Reason is required')

    if amt > 0:
        txn, wallet = credit_wallet(
            user_id=user_id,
            amount=amt,
            transaction_type=TransactionType.ADMIN_ADJUSTMENT,
            actor_id=admin_id,
            reference=reference,
            reason=reason
        )
    else:
        txn, wallet = debit_wallet(
            user_id=user_id,
            amount=abs(amt),
            transaction_type=TransactionType.ADMIN_ADJUSTMENT,
            actor_id=admin_id,
            reference=reference,
            reason=reason
        )

    audit = AuditLog(
        actor_id=admin_id,
        action='ADMIN_ADJUSTMENT',
        target_type='user',
        target_id=user_id,
        amount=amt,
        old_value=str(txn.previous_balance),
        new_value=str(txn.new_balance),
        reason=reason,
        ip_address=ip
    )
    db.session.add(audit)
    return txn, wallet
