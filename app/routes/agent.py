from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from functools import wraps
from app import db
from app.models.user import User, Role
from app.models.payment import DepositRequest, DepositStatus, DepositType
from app.models.agent import AgentProfile, AgentCommission
from app.models.wallet import WalletTransaction
from app.services.deposit_service import approve_deposit, reject_deposit
from app.services.wallet_service import get_or_create_wallet, WalletServiceError, credit_wallet, debit_wallet
from app.models.wallet import TransactionType
from app.services.notification_service import notify
from decimal import Decimal

agent_bp = Blueprint('agent', __name__, url_prefix='/agent')


def agent_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_access_agent():
            abort(403)
        return f(*args, **kwargs)
    return decorated


@agent_bp.route('/')
@login_required
@agent_required
def dashboard():
    profile = AgentProfile.query.filter_by(user_id=current_user.id).first()
    pending = DepositRequest.query.filter_by(
        agent_id=current_user.id, status=DepositStatus.PENDING
    ).count()
    recent = DepositRequest.query.filter_by(agent_id=current_user.id).order_by(
        DepositRequest.created_at.desc()
    ).limit(5).all()
    agent_wallet = get_or_create_wallet(current_user.id)
    return render_template('agent/dashboard.html', profile=profile, pending=pending, recent=recent, agent_wallet=agent_wallet)


@agent_bp.route('/deposits')
@login_required
@agent_required
def deposits():
    status = request.args.get('status', 'pending')
    q = DepositRequest.query.filter_by(agent_id=current_user.id)
    if status:
        q = q.filter_by(status=status)
    deposits_list = q.order_by(DepositRequest.created_at.desc()).all()
    return render_template('agent/deposits.html', deposits=deposits_list, status=status)


@agent_bp.route('/deposits/<int:dep_id>/approve', methods=['POST'])
@login_required
@agent_required
def approve_deposit_req(dep_id):
    req = DepositRequest.query.filter_by(id=dep_id, agent_id=current_user.id).first_or_404()
    try:
        approve_deposit(dep_id, current_user.id, ip=request.remote_addr)
        db.session.commit()
        flash('Deposit approved and wallet credited.', 'success')
    except WalletServiceError as e:
        flash(str(e), 'danger')
        db.session.rollback()
    return redirect(url_for('agent.deposits'))


@agent_bp.route('/deposits/<int:dep_id>/reject', methods=['POST'])
@login_required
@agent_required
def reject_deposit_req(dep_id):
    reason = request.form.get('reason', 'Rejected by agent')
    try:
        reject_deposit(dep_id, current_user.id, reason, ip=request.remote_addr)
        db.session.commit()
        flash('Deposit rejected.', 'info')
    except WalletServiceError as e:
        flash(str(e), 'danger')
        db.session.rollback()
    return redirect(url_for('agent.deposits'))


@agent_bp.route('/load-wallet', methods=['GET', 'POST'])
@login_required
@agent_required
def load_wallet():
    """Load player wallet from agent's float. Debits agent wallet, credits player."""
    agent_wallet = get_or_create_wallet(current_user.id)
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        amount = request.form.get('amount')
        reason = request.form.get('reason', 'Agent wallet load')
        user = User.query.filter_by(username=username).first()
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('agent.load_wallet'))
        if user.id == current_user.id:
            flash('Cannot load your own wallet this way.', 'danger')
            return redirect(url_for('agent.load_wallet'))
        if user.role == Role.ADMIN:
            flash('Cannot load admin wallet.', 'danger')
            return redirect(url_for('agent.load_wallet'))
        try:
            amt = Decimal(str(amount))
            if amt <= 0:
                raise WalletServiceError('Invalid amount')
            # 1) Debit agent float
            debit_wallet(
                user_id=current_user.id,
                amount=amt,
                transaction_type=TransactionType.AGENT_FLOAT_SPEND,
                actor_id=current_user.id,
                reason=f'Load for {username}: {reason}',
                related_type='agent_load',
            )
            # 2) Credit player
            txn, _ = credit_wallet(
                user_id=user.id,
                amount=amt,
                transaction_type=TransactionType.AGENT_LOAD,
                actor_id=current_user.id,
                reason=reason,
                update_totals={'total_deposited': amt}
            )
            profile = AgentProfile.query.filter_by(user_id=current_user.id).first()
            if profile:
                rate = Decimal(str(profile.commission_rate or 2))
                commission_amt = (amt * rate / Decimal('100')).quantize(Decimal('0.01'))
                commission = AgentCommission(
                    agent_id=profile.id,
                    transaction_id=txn.id,
                    amount=amt,
                    commission_rate=rate,
                    commission_amount=commission_amt
                )
                db.session.add(commission)
                profile.total_loads = Decimal(str(profile.total_loads or 0)) + amt
                profile.total_commission = Decimal(str(profile.total_commission or 0)) + commission_amt
            notify(user.id, 'Wallet Loaded by Agent', f'Rs.{amt} has been loaded to your wallet by agent.', 'deposit', '/wallet')
            db.session.commit()
            flash(f'Rs.{amt} loaded to {username}. Your float left: Rs.{get_or_create_wallet(current_user.id).balance}', 'success')
        except WalletServiceError as e:
            flash(str(e), 'danger')
            db.session.rollback()
        except Exception as e:
            flash(str(e), 'danger')
            db.session.rollback()
        return redirect(url_for('agent.load_wallet'))
    return render_template('agent/load_wallet.html', agent_wallet=agent_wallet)


@agent_bp.route('/users')
@login_required
@agent_required
def users():
    q = request.args.get('q', '').strip()
    query = User.query.filter_by(role=Role.PLAYER, is_active=True)
    if q:
        query = query.filter(
            (User.username.ilike(f'%{q}%')) | (User.email.ilike(f'%{q}%')) | (User.phone.ilike(f'%{q}%'))
        )
    users_list = query.order_by(User.created_at.desc()).limit(50).all()
    return render_template('agent/users.html', users=users_list, q=q)


@agent_bp.route('/transactions')
@login_required
@agent_required
def transactions():
    txns = WalletTransaction.query.filter_by(actor_id=current_user.id).order_by(
        WalletTransaction.created_at.desc()
    ).limit(50).all()
    return render_template('agent/transactions.html', txns=txns)


@agent_bp.route('/commission')
@login_required
@agent_required
def commission():
    profile = AgentProfile.query.filter_by(user_id=current_user.id).first()
    commissions = []
    if profile:
        commissions = AgentCommission.query.filter_by(agent_id=profile.id).order_by(
            AgentCommission.created_at.desc()
        ).all()
    return render_template('agent/commission.html', profile=profile, commissions=commissions)

@agent_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@agent_required
def profile():
    profile = AgentProfile.query.filter_by(user_id=current_user.id).first()
    if request.method == 'POST' and profile:
        profile.display_name = request.form.get('display_name', profile.display_name)
        profile.contact = request.form.get('contact', profile.contact)
        profile.payment_instructions = request.form.get('payment_instructions', profile.payment_instructions)
        if 'payment_qr' in request.files:
            from app.services.payment_service import upload_image
            f = request.files['payment_qr']
            if f and f.filename:
                profile.payment_qr = upload_image(f, 'agent_qr')
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('agent.profile'))
    return render_template('agent/profile.html', profile=profile)


@agent_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@agent_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'password':
            current_pw = request.form.get('current_password')
            new_pw = request.form.get('new_password')
            confirm = request.form.get('confirm_password')
            if not current_user.check_password(current_pw or ''):
                flash('Current password incorrect.', 'danger')
            elif len(new_pw or '') < 6:
                flash('New password must be at least 6 characters.', 'danger')
            elif new_pw != confirm:
                flash('Passwords do not match.', 'danger')
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                flash('Password updated.', 'success')
        return redirect(url_for('agent.settings'))
    return render_template('agent/settings.html')
