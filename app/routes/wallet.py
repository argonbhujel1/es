from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models.payment import PaymentMethod, DepositRequest, WithdrawalRequest, DepositType
from app.models.agent import AgentProfile
from app.models.user import User, Role
from app.services.wallet_service import get_or_create_wallet, WalletServiceError
from app.services.deposit_service import create_deposit_request
from app.services.withdrawal_service import create_withdrawal
from app.services.payment_service import upload_image
from decimal import Decimal

wallet_bp = Blueprint('wallet', __name__, url_prefix='/wallet')


@wallet_bp.route('/')
@login_required
def index():
    wallet = get_or_create_wallet(current_user.id)
    from app.models.wallet import WalletTransaction
    txns = WalletTransaction.query.filter_by(user_id=current_user.id).order_by(
        WalletTransaction.created_at.desc()
    ).limit(10).all()
    return render_template('wallet/index.html', wallet=wallet, txns=txns)


@wallet_bp.route('/add-money')
@login_required
def add_money():
    return render_template('wallet/add_money.html')


@wallet_bp.route('/deposit/admin', methods=['GET', 'POST'])
@login_required
def deposit_admin():
    methods = PaymentMethod.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        try:
            amount = Decimal(str(request.form.get('amount', 0)))
            payment_method_id = request.form.get('payment_method_id', type=int)
            reference = request.form.get('reference_number', '').strip()
            note = request.form.get('note', '').strip()
            screenshot = None
            if 'screenshot' in request.files:
                f = request.files['screenshot']
                if f and f.filename:
                    screenshot = upload_image(f, 'deposits')

            method = PaymentMethod.query.get(payment_method_id) if payment_method_id else None
            if method:
                if amount < float(method.min_deposit or 100):
                    raise WalletServiceError(f'Minimum deposit is Rs.{method.min_deposit}')
                if amount > float(method.max_deposit or 50000):
                    raise WalletServiceError(f'Maximum deposit is Rs.{method.max_deposit}')

            create_deposit_request(
                user_id=current_user.id,
                amount=amount,
                deposit_type=DepositType.ADMIN,
                payment_method_id=payment_method_id,
                reference_number=reference,
                screenshot=screenshot,
                note=note
            )
            db.session.commit()
            flash('Deposit request submitted. Await admin verification.', 'success')
            return redirect(url_for('wallet.index'))
        except (WalletServiceError, ValueError) as e:
            flash(str(e), 'danger')
            db.session.rollback()
    return render_template('wallet/deposit_admin.html', methods=methods)


@wallet_bp.route('/deposit/agent', methods=['GET', 'POST'])
@login_required
def deposit_agent():
    agents = AgentProfile.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        try:
            amount = Decimal(str(request.form.get('amount', 0)))
            agent_id = request.form.get('agent_id', type=int)
            reference = request.form.get('reference_number', '').strip()
            note = request.form.get('note', '').strip()
            screenshot = None
            if 'screenshot' in request.files:
                f = request.files['screenshot']
                if f and f.filename:
                    screenshot = upload_image(f, 'deposits')

            if not agent_id:
                raise WalletServiceError('Select an agent')
            agent_profile = AgentProfile.query.filter_by(user_id=agent_id, is_active=True).first()
            if not agent_profile:
                raise WalletServiceError('Invalid agent')

            create_deposit_request(
                user_id=current_user.id,
                amount=amount,
                deposit_type=DepositType.AGENT,
                agent_id=agent_id,
                reference_number=reference,
                screenshot=screenshot,
                note=note
            )
            db.session.commit()
            flash('Deposit request submitted to agent. Await verification.', 'success')
            return redirect(url_for('wallet.index'))
        except (WalletServiceError, ValueError) as e:
            flash(str(e), 'danger')
            db.session.rollback()
    return render_template('wallet/deposit_agent.html', agents=agents)


@wallet_bp.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    wallet = get_or_create_wallet(current_user.id)
    methods = PaymentMethod.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        try:
            amount = Decimal(str(request.form.get('amount', 0)))
            payment_method_id = request.form.get('payment_method_id', type=int)
            account_name = request.form.get('account_name', '').strip()
            account_number = request.form.get('account_number', '').strip()
            payment_details = request.form.get('payment_details', '').strip()
            note = request.form.get('note', '').strip()
            user_qr = None
            if 'user_qr' in request.files:
                f = request.files['user_qr']
                if f and f.filename:
                    user_qr = upload_image(f, 'withdrawal_qr')

            if not account_name or not account_number:
                raise WalletServiceError('Account name and number required')
            if amount > wallet.available_balance:
                raise WalletServiceError(f'Insufficient available balance. Available: Rs.{wallet.available_balance}')

            method = PaymentMethod.query.get(payment_method_id) if payment_method_id else None
            if method:
                min_w = float(method.min_withdrawal or 100)
                max_w = float(method.max_withdrawal or 50000)
                if amount < min_w:
                    raise WalletServiceError(f'Minimum withdrawal is Rs.{min_w}')
                if amount > max_w:
                    raise WalletServiceError(f'Maximum withdrawal is Rs.{max_w}')

            create_withdrawal(
                user_id=current_user.id,
                amount=amount,
                account_name=account_name,
                account_number=account_number,
                payment_method_id=payment_method_id,
                payment_details=payment_details,
                user_qr=user_qr,
                note=note
            )
            db.session.commit()
            flash('Withdrawal request submitted. Amount held until processed.', 'success')
            return redirect(url_for('wallet.index'))
        except (WalletServiceError, ValueError) as e:
            flash(str(e), 'danger')
            db.session.rollback()
    return render_template('wallet/withdraw.html', wallet=wallet, methods=methods)
