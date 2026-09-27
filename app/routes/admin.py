from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
from decimal import Decimal
from app import db
from app.models.user import User, Role
from app.models.wallet import Wallet, WalletTransaction
from app.models.payment import PaymentMethod, DepositRequest, WithdrawalRequest, DepositStatus, WithdrawalStatus
from app.models.agent import AgentApplication, AgentApplicationStatus, AgentProfile
from app.models.game import Game
from app.models.tournament import (
    Tournament, TournamentStatus, Room, Match, MatchResult, ResultStatus, PrizeDistribution
)
from app.models.news import News
from app.models.notification import Notification
from app.models.audit import AuditLog
from app.services.wallet_service import (
    get_or_create_wallet, admin_direct_load, admin_direct_deduct,
    admin_adjustment, WalletServiceError, debit_wallet, credit_wallet, release_hold
)
from app.models.wallet import TransactionType
from app.services.deposit_service import approve_deposit, reject_deposit
from app.services.withdrawal_service import set_withdrawal_status, mark_withdrawal_paid
from app.services.agent_service import approve_agent, reject_agent
from app.services.tournament_service import approve_result_and_distribute_prize, join_tournament
from app.services.payment_service import upload_image
from app.services.notification_service import notify, notify_all_users, notify_admin
import re

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_access_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s_-]+', '-', text)


@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    stats = {
        'total_users': User.query.count(),
        'active_users': User.query.filter_by(is_active=True, is_blocked=False).count(),
        'total_agents': User.query.filter_by(role=Role.AGENT).count(),
        'active_agents': AgentProfile.query.filter_by(is_active=True).count(),
        'total_wallet_balance': db.session.query(db.func.coalesce(db.func.sum(Wallet.balance), 0)).scalar(),
        'pending_deposits': DepositRequest.query.filter_by(status=DepositStatus.PENDING).count(),
        'pending_withdrawals': WithdrawalRequest.query.filter_by(status=WithdrawalStatus.PENDING).count(),
        'pending_agents': AgentApplication.query.filter_by(status=AgentApplicationStatus.PENDING).count(),
        'active_tournaments': Tournament.query.filter(
            Tournament.status.in_([TournamentStatus.UPCOMING, TournamentStatus.LIVE])
        ).count(),
        'active_rooms': Room.query.filter(Room.status.in_(['waiting', 'active'])).count(),
    }
    return render_template('admin/dashboard.html', stats=stats)


# ========== USERS ==========
@admin_bp.route('/users')
@login_required
@admin_required
def users():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    query = User.query
    if q:
        query = query.filter(
            db.or_(
                User.username.ilike(f'%{q}%'),
                User.email.ilike(f'%{q}%'),
                User.full_name.ilike(f'%{q}%'),
                User.phone.ilike(f'%{q}%'),
                User.id == int(q) if q.isdigit() else False
            )
        )
    users_list = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/users.html', users=users_list, q=q)


@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    user = User.query.get_or_404(user_id)
    wallet = get_or_create_wallet(user_id)
    return render_template('admin/user_detail.html', user=user, wallet=wallet)


@admin_bp.route('/users/<int:user_id>/block', methods=['POST'])
@login_required
@admin_required
def block_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin():
        flash('Cannot block admin.', 'danger')
    else:
        user.is_blocked = not user.is_blocked
        action = 'USER_BLOCKED' if user.is_blocked else 'USER_UNBLOCKED'
        db.session.add(AuditLog(actor_id=current_user.id, action=action, target_type='user', target_id=user_id, ip_address=request.remote_addr))
        db.session.commit()
    try:
        status = 'blocked' if user.is_blocked else 'unblocked'
        notify(user.id, f'Account {status.title()}',
               f'Your account has been {status} by admin.', 'system', '/')
        db.session.commit()
    except Exception:
        pass
        flash(f'User {"blocked" if user.is_blocked else "unblocked"}.', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))


@admin_bp.route('/users/<int:user_id>/wallet')
@login_required
@admin_required
def user_wallet(user_id):
    user = User.query.get_or_404(user_id)
    wallet = get_or_create_wallet(user_id)
    txns = WalletTransaction.query.filter_by(user_id=user_id).order_by(WalletTransaction.created_at.desc()).limit(20).all()
    return render_template('admin/user_wallet.html', user=user, wallet=wallet, txns=txns)


@admin_bp.route('/users/<int:user_id>/add-money', methods=['POST'])
@login_required
@admin_required
def user_add_money(user_id):
    amount = request.form.get('amount')
    reason = request.form.get('reason', '').strip()
    reference = request.form.get('reference', '').strip() or None
    try:
        admin_direct_load(user_id, amount, current_user.id, reason, reference, request.remote_addr)
        db.session.commit()
        notify(user_id, 'Wallet Credited', f'Rs.{amount} has been added to your wallet by admin. Reason: {reason}', 'deposit', '/wallet')
        flash(f'Rs.{amount} added successfully to user wallet.', 'success')
    except WalletServiceError as e:
        flash(str(e), 'danger')
        db.session.rollback()
    return redirect(url_for('admin.user_wallet', user_id=user_id))


@admin_bp.route('/users/<int:user_id>/deduct-money', methods=['POST'])
@login_required
@admin_required
def user_deduct_money(user_id):
    amount = request.form.get('amount')
    reason = request.form.get('reason', '').strip()
    reference = request.form.get('reference', '').strip() or None
    try:
        admin_direct_deduct(user_id, amount, current_user.id, reason, reference, request.remote_addr)
        db.session.commit()
        notify(user_id, 'Wallet Deducted', f'Rs.{amount} has been deducted from your wallet. Reason: {reason}', 'system', '/wallet')
        flash(f'Rs.{amount} deducted successfully.', 'success')
    except WalletServiceError as e:
        flash(str(e), 'danger')
        db.session.rollback()
    return redirect(url_for('admin.user_wallet', user_id=user_id))


# ========== WALLET ==========
@admin_bp.route('/wallet')
@login_required
@admin_required
def wallet_mgmt():
    q = request.args.get('q', '').strip()
    user = None
    wallet = None
    if q:
        user = User.query.filter(
            db.or_(User.username == q, User.email == q, User.phone == q,
                   User.id == int(q) if q.isdigit() else False)
        ).first()
        if user:
            wallet = get_or_create_wallet(user.id)
    return render_template('admin/wallet.html', user=user, wallet=wallet, q=q)


# ========== DEPOSITS ==========
@admin_bp.route('/deposits')
@login_required
@admin_required
def deposits():
    status = request.args.get('status', '')
    dtype = request.args.get('type', '')
    q = DepositRequest.query
    if status:
        q = q.filter_by(status=status)
    if dtype:
        q = q.filter_by(deposit_type=dtype)
    deposits_list = q.order_by(DepositRequest.created_at.desc()).limit(100).all()
    return render_template('admin/deposits.html', deposits=deposits_list, status=status, dtype=dtype)


@admin_bp.route('/deposits/<int:dep_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_dep(dep_id):
    try:
        approve_deposit(dep_id, current_user.id, request.remote_addr)
        db.session.commit()
        flash('Deposit approved.', 'success')
    except WalletServiceError as e:
        flash(str(e), 'danger')
        db.session.rollback()
    return redirect(url_for('admin.deposits'))


@admin_bp.route('/deposits/<int:dep_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_dep(dep_id):
    reason = request.form.get('reason', 'Rejected by admin')
    try:
        reject_deposit(dep_id, current_user.id, reason, request.remote_addr)
        db.session.commit()
        flash('Deposit rejected.', 'info')
    except WalletServiceError as e:
        flash(str(e), 'danger')
        db.session.rollback()
    return redirect(url_for('admin.deposits'))


# ========== WITHDRAWALS ==========
@admin_bp.route('/withdrawals')
@login_required
@admin_required
def withdrawals():
    status = request.args.get('status', '')
    q = WithdrawalRequest.query
    if status:
        q = q.filter_by(status=status)
    withdrawals_list = q.order_by(WithdrawalRequest.created_at.desc()).limit(100).all()
    return render_template('admin/withdrawals.html', withdrawals=withdrawals_list, status=status)


@admin_bp.route('/withdrawals/<int:wd_id>/<action>', methods=['POST'])
@login_required
@admin_required
def withdrawal_action(wd_id, action):
    reason = request.form.get('reason')
    note = request.form.get('admin_note')
    try:
        if action == 'paid':
            mark_withdrawal_paid(wd_id, current_user.id, request.remote_addr)
            flash('Withdrawal marked as paid.', 'success')
        elif action in ('approve', 'reject', 'processing', 'cancel'):
            status_map = {
                'approve': WithdrawalStatus.APPROVED,
                'reject': WithdrawalStatus.REJECTED,
                'processing': WithdrawalStatus.PROCESSING,
                'cancel': WithdrawalStatus.CANCELLED,
            }
            set_withdrawal_status(wd_id, current_user.id, status_map[action], reason, note, request.remote_addr)
            flash(f'Withdrawal {action}d.', 'success')
        else:
            flash('Invalid action.', 'danger')
        db.session.commit()
    except WalletServiceError as e:
        flash(str(e), 'danger')
        db.session.rollback()
    return redirect(url_for('admin.withdrawals'))


# ========== PAYMENT METHODS ==========
@admin_bp.route('/payment-methods', methods=['GET', 'POST'])
@login_required
@admin_required
def payment_methods():
    if request.method == 'POST':
        name = request.form.get('name')
        pm = PaymentMethod(
            name=name,
            type=request.form.get('type', 'qr'),
            account_name=request.form.get('account_name'),
            account_number=request.form.get('account_number'),
            instructions=request.form.get('instructions'),
            min_deposit=Decimal(request.form.get('min_deposit') or 100),
            max_deposit=Decimal(request.form.get('max_deposit') or 50000),
            min_withdrawal=Decimal(request.form.get('min_withdrawal') or 100),
            max_withdrawal=Decimal(request.form.get('max_withdrawal') or 50000),
            is_active=True
        )
        if 'qr_image' in request.files:
            f = request.files['qr_image']
            if f and f.filename:
                pm.qr_image = upload_image(f, 'payment_qr')
        db.session.add(pm)
        db.session.add(AuditLog(actor_id=current_user.id, action='PAYMENT_METHOD_CREATED', target_type='payment_method', reason=name, ip_address=request.remote_addr))
        db.session.commit()
        flash('Payment method added.', 'success')
        return redirect(url_for('admin.payment_methods'))
    methods = PaymentMethod.query.order_by(PaymentMethod.created_at.desc()).all()
    return render_template('admin/payment_methods.html', methods=methods)


@admin_bp.route('/payment-methods/<int:pm_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_payment_method(pm_id):
    pm = PaymentMethod.query.get_or_404(pm_id)
    pm.is_active = not pm.is_active
    db.session.commit()
    flash(f'Payment method {"enabled" if pm.is_active else "disabled"}.', 'success')
    return redirect(url_for('admin.payment_methods'))


@admin_bp.route('/payment-methods/<int:pm_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_payment_method(pm_id):
    pm = PaymentMethod.query.get_or_404(pm_id)
    db.session.delete(pm)
    db.session.commit()
    flash('Payment method deleted.', 'success')
    return redirect(url_for('admin.payment_methods'))



@admin_bp.route('/payment-methods/<int:pm_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_payment_method(pm_id):
    pm = PaymentMethod.query.get_or_404(pm_id)
    if request.method == 'POST':
        pm.name = request.form.get('name') or pm.name
        pm.account_name = request.form.get('account_name') or pm.account_name
        pm.account_number = request.form.get('account_number') or pm.account_number
        pm.instructions = request.form.get('instructions') or pm.instructions
        pm.min_deposit = Decimal(request.form.get('min_deposit') or pm.min_deposit or 100)
        pm.max_deposit = Decimal(request.form.get('max_deposit') or pm.max_deposit or 50000)
        pm.min_withdrawal = Decimal(request.form.get('min_withdrawal') or pm.min_withdrawal or 100)
        pm.max_withdrawal = Decimal(request.form.get('max_withdrawal') or pm.max_withdrawal or 50000)
        if 'qr_image' in request.files:
            f = request.files['qr_image']
            if f and f.filename:
                from app.services.payment_service import upload_image
                pm.qr_image = upload_image(f, 'payment_qr')
        db.session.commit()
        flash('Payment method updated.', 'success')
        return redirect(url_for('admin.payment_methods'))
    return render_template('admin/payment_method_edit.html', method=pm)


@admin_bp.route('/deposit-qr')
@login_required
@admin_required
def deposit_qr():
    methods = PaymentMethod.query.filter_by(is_active=True).all()
    return render_template('admin/deposit_qr.html', methods=methods)


# ========== AGENTS ==========
@admin_bp.route('/agents')
@login_required
@admin_required
def agents():
    applications = AgentApplication.query.order_by(AgentApplication.created_at.desc()).all()
    profiles = AgentProfile.query.all()
    return render_template('admin/agents.html', applications=applications, profiles=profiles)


@admin_bp.route('/agents/<int:app_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_agent_app(app_id):
    rate = float(request.form.get('commission_rate', 2))
    try:
        approve_agent(app_id, current_user.id, rate, request.remote_addr)
        db.session.commit()
        flash('Agent approved.', 'success')
    except WalletServiceError as e:
        flash(str(e), 'danger')
        db.session.rollback()
    return redirect(url_for('admin.agents'))


@admin_bp.route('/agents/<int:app_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_agent_app(app_id):
    reason = request.form.get('reason', 'Rejected')
    try:
        reject_agent(app_id, current_user.id, reason, request.remote_addr)
        db.session.commit()
        flash('Agent application rejected.', 'info')
    except WalletServiceError as e:
        flash(str(e), 'danger')
        db.session.rollback()
    return redirect(url_for('admin.agents'))


# ========== TRANSACTIONS ==========
@admin_bp.route('/transactions')
@login_required
@admin_required
def transactions():
    page = request.args.get('page', 1, type=int)
    type_filter = request.args.get('type', '')
    q = WalletTransaction.query
    if type_filter:
        q = q.filter_by(type=type_filter)
    txns = q.order_by(WalletTransaction.created_at.desc()).paginate(page=page, per_page=30, error_out=False)
    return render_template('admin/transactions.html', txns=txns, type_filter=type_filter)


# ========== GAMES ==========
@admin_bp.route('/games', methods=['GET', 'POST'])
@login_required
@admin_required
def games():
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        if action == 'edit':
            game = Game.query.get_or_404(request.form.get('game_id', type=int))
            game.name = request.form.get('name') or game.name
            game.description = request.form.get('description') or game.description
            if 'icon' in request.files:
                f = request.files['icon']
                if f and f.filename:
                    game.icon = upload_image(f, 'games')
            if 'banner' in request.files:
                f = request.files['banner']
                if f and f.filename:
                    game.banner = upload_image(f, 'games')
            db.session.commit()
            flash('Game updated.', 'success')
        else:
            name = request.form.get('name')
            game = Game(name=name, slug=slugify(name), description=request.form.get('description'))
            if 'icon' in request.files:
                f = request.files['icon']
                if f and f.filename:
                    game.icon = upload_image(f, 'games')
            if 'banner' in request.files:
                f = request.files['banner']
                if f and f.filename:
                    game.banner = upload_image(f, 'games')
            db.session.add(game)
            db.session.commit()
            flash('Game added.', 'success')
        return redirect(url_for('admin.games'))
    games_list = Game.query.all()
    return render_template('admin/games.html', games=games_list)


# ========== TOURNAMENTS ==========
@admin_bp.route('/tournaments', methods=['GET', 'POST'])
@login_required
@admin_required
def tournaments():
    if request.method == 'POST':
        name = request.form.get('name')
        tournament = Tournament(
            name=name,
            slug=slugify(name) + '-' + str(int(datetime.utcnow().timestamp())),
            game_id=request.form.get('game_id', type=int),
            description=request.form.get('description'),
            rules=request.form.get('rules'),
            entry_fee=Decimal(request.form.get('entry_fee') or 0),
            prize_pool=Decimal(request.form.get('prize_pool') or 0),
            max_players=int(request.form.get('max_players') or 100),
            status=request.form.get('status', TournamentStatus.DRAFT),
            prize_distribution=request.form.get('prize_distribution'),
            created_by=current_user.id
        )
        start = request.form.get('start_datetime')
        deadline = request.form.get('registration_deadline')
        if start:
            tournament.start_datetime = datetime.fromisoformat(start)
        if deadline:
            tournament.registration_deadline = datetime.fromisoformat(deadline)
        if 'banner' in request.files:
            f = request.files['banner']
            if f and f.filename:
                tournament.banner = upload_image(f, 'tournaments')
        db.session.add(tournament)
        db.session.commit()
        flash('Tournament created.', 'success')
        try:
            notify_all_users(
                f'New Tournament: {tournament.name}',
                f'{tournament.name} is live! Prize pool Rs.{tournament.prize_pool}. Entry Rs.{tournament.entry_fee}. Join now!',
                'tournament',
                f'/tournaments/{tournament.slug}'
            )
            db.session.commit()
        except Exception:
            pass
        return redirect(url_for('admin.tournaments'))
    tournaments_list = Tournament.query.order_by(Tournament.created_at.desc()).all()
    games_list = Game.query.filter_by(is_active=True).all()
    return render_template('admin/tournaments.html', tournaments=tournaments_list, games=games_list)


@admin_bp.route('/tournaments/<int:t_id>/status', methods=['POST'])
@login_required
@admin_required
def tournament_status(t_id):
    t = Tournament.query.get_or_404(t_id)
    t.status = request.form.get('status', t.status)
    db.session.commit()
    flash('Tournament status updated.', 'success')
    return redirect(url_for('admin.tournaments'))


# ========== ROOMS ==========
@admin_bp.route('/rooms', methods=['GET', 'POST'])
@login_required
@admin_required
def rooms():
    if request.method == 'POST':
        room = Room(
            tournament_id=request.form.get('tournament_id', type=int) or None,
            game_id=request.form.get('game_id', type=int) or None,
            name=request.form.get('name'),
            room_id=request.form.get('room_id'),
            password=request.form.get('password'),
            instructions=request.form.get('instructions'),
            max_players=int(request.form.get('max_players') or 50),
            status=request.form.get('status', 'waiting'),
            created_by=current_user.id,
            is_public=True
        )
        if 'cover_image' in request.files:
            f = request.files['cover_image']
            if f and f.filename:
                room.cover_image = upload_image(f, 'rooms')
        mt = request.form.get('match_time')
        if mt:
            room.match_time = datetime.fromisoformat(mt)
        db.session.add(room)
        db.session.commit()
        flash('Room created.', 'success')
        return redirect(url_for('admin.rooms'))
    rooms_list = Room.query.order_by(Room.created_at.desc()).all()
    tournaments_list = Tournament.query.filter(
        Tournament.status.in_([TournamentStatus.UPCOMING, TournamentStatus.LIVE, TournamentStatus.APPROVED])
    ).all()
    return render_template('admin/rooms.html', rooms=rooms_list, tournaments=tournaments_list)


# ========== MATCHES & RESULTS ==========
@admin_bp.route('/matches', methods=['GET', 'POST'])
@login_required
@admin_required
def matches():
    if request.method == 'POST':
        match = Match(
            tournament_id=request.form.get('tournament_id', type=int),
            room_id=request.form.get('room_id', type=int) or None,
            name=request.form.get('name'),
            match_number=int(request.form.get('match_number') or 1),
            status=request.form.get('status', 'scheduled')
        )
        db.session.add(match)
        db.session.commit()
        flash('Match created.', 'success')
        return redirect(url_for('admin.matches'))
    matches_list = Match.query.order_by(Match.created_at.desc()).all()
    tournaments_list = Tournament.query.all()
    return render_template('admin/matches.html', matches=matches_list, tournaments=tournaments_list)


@admin_bp.route('/results', methods=['GET', 'POST'])
@login_required
@admin_required
def results():
    if request.method == 'POST':
        result = MatchResult(
            match_id=request.form.get('match_id', type=int),
            tournament_id=request.form.get('tournament_id', type=int),
            winner_id=request.form.get('winner_id', type=int),
            notes=request.form.get('notes'),
            submitted_by=current_user.id,
            status=ResultStatus.PENDING
        )
        if 'proof_screenshot' in request.files:
            f = request.files['proof_screenshot']
            if f and f.filename:
                result.proof_screenshot = upload_image(f, 'results')
        db.session.add(result)
        db.session.commit()
        flash('Result submitted for verification.', 'success')
        return redirect(url_for('admin.results'))
    results_list = MatchResult.query.order_by(MatchResult.submitted_at.desc()).all()
    matches_list = Match.query.all()
    tournaments_list = Tournament.query.all()
    users_list = User.query.filter_by(role=Role.PLAYER).limit(100).all()
    return render_template('admin/results.html', results=results_list, matches=matches_list,
                           tournaments=tournaments_list, users=users_list)


@admin_bp.route('/results/<int:res_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_result(res_id):
    prize_amount = request.form.get('prize_amount')
    try:
        approve_result_and_distribute_prize(res_id, current_user.id, prize_amount, request.remote_addr)
        db.session.commit()
        flash('Result approved and prize distributed.', 'success')
    except WalletServiceError as e:
        flash(str(e), 'danger')
        db.session.rollback()
    return redirect(url_for('admin.results'))


@admin_bp.route('/results/<int:res_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_result(res_id):
    result = MatchResult.query.get_or_404(res_id)
    result.status = ResultStatus.REJECTED
    result.reviewed_by = current_user.id
    result.reviewed_at = datetime.utcnow()
    result.rejection_reason = request.form.get('reason', 'Rejected')
    db.session.commit()
    flash('Result rejected.', 'info')
    return redirect(url_for('admin.results'))


# ========== PRIZES ==========
@admin_bp.route('/prizes')
@login_required
@admin_required
def prizes():
    prizes_list = PrizeDistribution.query.order_by(PrizeDistribution.created_at.desc()).all()
    return render_template('admin/prizes.html', prizes=prizes_list)


# ========== LEADERBOARD ==========
@admin_bp.route('/leaderboard')
@login_required
@admin_required
def leaderboard():
    from app.services.leaderboard_service import get_leaderboard
    entries = get_leaderboard(limit=100)
    return render_template('admin/leaderboard.html', entries=entries)


# ========== NEWS ==========
@admin_bp.route('/news', methods=['GET', 'POST'])
@login_required
@admin_required
def news():
    if request.method == 'POST':
        title = request.form.get('title')
        item = News(
            title=title,
            slug=slugify(title) + '-' + str(int(datetime.utcnow().timestamp())),
            content=request.form.get('content'),
            author_id=current_user.id,
            status=request.form.get('status', 'draft'),
            is_featured=bool(request.form.get('is_featured'))
        )
        if item.status == 'published':
            item.published_at = datetime.utcnow()
        if 'cover_image' in request.files:
            f = request.files['cover_image']
            if f and f.filename:
                item.cover_image = upload_image(f, 'news')
        db.session.add(item)
        db.session.commit()
        flash('News created.', 'success')
        return redirect(url_for('admin.news'))
    news_list = News.query.order_by(News.created_at.desc()).all()
    return render_template('admin/news.html', news_list=news_list)


# ========== NOTIFICATIONS ==========
@admin_bp.route('/notifications', methods=['GET', 'POST'])
@login_required
@admin_required
def notifications():
    if request.method == 'POST':
        title = request.form.get('title')
        message = request.form.get('message')
        target = request.form.get('target', 'all')
        users = []
        if target == 'all':
            users = User.query.filter_by(is_active=True).all()
        elif target == 'players':
            users = User.query.filter_by(role=Role.PLAYER, is_active=True).all()
        elif target == 'agents':
            users = User.query.filter_by(role=Role.AGENT, is_active=True).all()
        elif target == 'user':
            uid = request.form.get('user_id', type=int)
            u = User.query.get(uid) if uid else None
            if not u:
                flash('User not found.', 'danger')
                return redirect(url_for('admin.notifications'))
            users = [u]
        for u in users:
            notify(u.id, title, message, 'announcement')
        db.session.commit()
        flash(f'Notification sent to {len(users)} user(s).', 'success')
        return redirect(url_for('admin.notifications'))
    return render_template('admin/notifications.html')


# ========== REPORTS ==========
@admin_bp.route('/reports')
@login_required
@admin_required
def reports():
    total_users = User.query.count()
    total_tournaments = Tournament.query.count()
    total_deposits = db.session.query(db.func.coalesce(db.func.sum(DepositRequest.amount), 0)).filter_by(status=DepositStatus.APPROVED).scalar()
    total_withdrawals = db.session.query(db.func.coalesce(db.func.sum(WithdrawalRequest.amount), 0)).filter_by(status=WithdrawalStatus.PAID).scalar()
    total_prizes = db.session.query(db.func.coalesce(db.func.sum(PrizeDistribution.amount), 0)).scalar()
    return render_template('admin/reports.html',
                           total_users=total_users,
                           total_tournaments=total_tournaments,
                           total_deposits=total_deposits,
                           total_withdrawals=total_withdrawals,
                           total_prizes=total_prizes)


# ========== SETTINGS ==========
@admin_bp.route('/settings')
@login_required
@admin_required
def settings():
    return render_template('admin/settings.html')


# ========== AUDIT LOGS ==========
@admin_bp.route('/audit-logs')
@login_required
@admin_required
def audit_logs():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    return render_template('admin/audit_logs.html', logs=logs)


# Join tournament from user side - also accessible




@admin_bp.route('/tournament-claims')
@login_required
@admin_required
def tournament_claims():
    """Admin-hosted tournament result SS claims."""
    pending = MatchResult.query.filter_by(status=ResultStatus.PENDING).order_by(
        MatchResult.submitted_at.desc()
    ).all()
    return render_template('admin/tournament_claims.html', pending=pending)


@admin_bp.route('/tournament-claims/<int:res_id>/verify', methods=['POST'])
@login_required
@admin_required
def tournament_claim_verify(res_id):
    action = request.form.get('action', 'approve')
    if action == 'reject':
        result = MatchResult.query.get_or_404(res_id)
        result.status = ResultStatus.REJECTED
        result.reviewed_by = current_user.id
        result.reviewed_at = datetime.utcnow()
        result.rejection_reason = request.form.get('reason', 'Rejected by admin')
        db.session.commit()
        flash('Claim rejected.', 'warning')
        return redirect(url_for('admin.tournament_claims'))
    prize = request.form.get('prize_amount')
    try:
        approve_result_and_distribute_prize(res_id, current_user.id, prize, request.remote_addr)
        db.session.commit()
        flash('Verified. Prize paid.', 'success')
    except WalletServiceError as e:
        db.session.rollback()
        flash(str(e), 'danger')
    return redirect(url_for('admin.tournament_claims'))


# ========== ROOM CLAIMS (admin verify → auto pay) ==========
@admin_bp.route('/room-claims')
@login_required
@admin_required
def room_claims():
    pending = Room.query.filter_by(status='pending_verify').order_by(Room.created_at.desc()).all()
    recent = Room.query.filter(Room.status.in_(['completed', 'cancelled'])).order_by(Room.created_at.desc()).limit(20).all()
    return render_template('admin/room_claims.html', pending=pending, recent=recent)


@admin_bp.route('/room-claims/<int:room_id>/verify', methods=['POST'])
@login_required
@admin_required
def room_claim_verify(room_id):
    room = Room.query.get_or_404(room_id)
    if room.status != 'pending_verify':
        flash('Not pending verification.', 'danger')
        return redirect(url_for('admin.room_claims'))
    action = request.form.get('action', 'approve')
    if action == 'reject':
        room.status = 'playing'
        room.winner_id = None
        room.loser_id = None
        room.claim_screenshot = None
        room.pending_transfer_amount = None
        db.session.commit()
        flash('Claim rejected.', 'warning')
        if room.created_by:
            notify(room.created_by, 'Claim Rejected', f'Admin rejected result claim on room {room.name}.', 'room', f'/rooms/{room.id}')
        return redirect(url_for('admin.room_claims'))
    if not room.winner_id or not room.loser_id:
        flash('Winner/loser missing.', 'danger')
        return redirect(url_for('admin.room_claims'))
    try:
        stake = Decimal(str(room.stake_amount or 0))
        amount = Decimal(str(room.pending_transfer_amount or stake or 0))
        if room.host_hold_txn_id and room.opponent_hold_txn_id and stake > 0:
            release_hold(room.created_by, stake, actor_id=current_user.id, reason='Admin room stake release host')
            release_hold(room.opponent_id, stake, actor_id=current_user.id, reason='Admin room stake release opponent')
            debit_wallet(room.loser_id, stake, TransactionType.ROOM_TRANSFER, actor_id=current_user.id,
                         reason=f'Lost room #{room.id} (admin verified)', related_id=room.id, related_type='room')
            credit_wallet(room.winner_id, stake * 2, TransactionType.ROOM_TRANSFER, actor_id=current_user.id,
                          reason=f'Won room #{room.id} (admin verified)', related_id=room.id, related_type='room')
            paid = stake * 2
        else:
            if amount <= 0:
                raise WalletServiceError('No amount to transfer')
            debit_wallet(room.loser_id, amount, TransactionType.ROOM_TRANSFER, actor_id=current_user.id,
                         reason=f'Lost room #{room.id} (admin verified)', related_id=room.id, related_type='room')
            credit_wallet(room.winner_id, amount, TransactionType.ROOM_TRANSFER, actor_id=current_user.id,
                          reason=f'Won room #{room.id} (admin verified)', related_id=room.id, related_type='room')
            paid = amount
        room.status = 'completed'
        room.settlement_otp = None
        db.session.commit()
        notify(room.winner_id, 'You Won!', f'Admin verified. Rs.{paid} credited — room {room.name}.', 'room', '/wallet/')
        notify(room.loser_id, 'Match Lost', f'Admin verified. Amount deducted — room {room.name}.', 'room', '/wallet/')
        flash(f'Verified. Rs.{paid} paid to winner.', 'success')
    except WalletServiceError as e:
        db.session.rollback()
        flash(str(e), 'danger')
    return redirect(url_for('admin.room_claims'))


@admin_bp.route('/join-tournament/<int:t_id>', methods=['POST'])
@login_required
def join_tournament_route(t_id):
    # This is for users - redirect properly
    from flask import abort
    abort(404)
