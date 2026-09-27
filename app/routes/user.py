from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models.user import User
from app.models.game import Game, GameID
from app.models.tournament import TournamentParticipant, Tournament, Room
from app.models.wallet import WalletTransaction
from app.models.agent import AgentApplication
from app.models.notification import Notification
from app.services.agent_service import apply_for_agent
from app.services.tournament_service import join_tournament
from app.services.wallet_service import get_or_create_wallet, WalletServiceError
from app.services.payment_service import upload_image

user_bp = Blueprint('user', __name__)


def player_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.is_blocked:
            flash('Account blocked.', 'danger')
            return redirect(url_for('public.index'))
        return f(*args, **kwargs)
    return decorated


@user_bp.route('/dashboard')
@login_required
@player_required
def dashboard():
    if current_user.is_admin():
        return redirect(url_for('admin.dashboard'))
    if current_user.is_agent():
        return redirect(url_for('agent.dashboard'))

    wallet = get_or_create_wallet(current_user.id)
    joined = TournamentParticipant.query.filter_by(user_id=current_user.id).count()
    from app.models.leaderboard import LeaderboardEntry
    lb = LeaderboardEntry.query.filter_by(user_id=current_user.id, period='overall').first()
    recent_txns = WalletTransaction.query.filter_by(user_id=current_user.id).order_by(
        WalletTransaction.created_at.desc()
    ).limit(5).all()
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(5).all()

    stats = {
        'balance': float(wallet.balance),
        'available': wallet.available_balance,
        'joined_tournaments': joined,
        'matches_played': lb.matches_played if lb else 0,
        'wins': lb.wins if lb else 0,
        'prize_won': float(wallet.total_prize_won or 0),
        'rank': None,
        'total_deposited': float(wallet.total_deposited or 0),
        'total_withdrawn': float(wallet.total_withdrawn or 0),
    }
    return render_template('user/dashboard.html', stats=stats, recent_txns=recent_txns,
                           notifications=notifications, wallet=wallet)


@user_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@player_required
def profile():
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name', current_user.full_name)
        phone = request.form.get('phone', '').strip() or None
        if phone and phone != current_user.phone:
            if User.query.filter(User.phone == phone, User.id != current_user.id).first():
                flash('Phone already in use.', 'danger')
                return redirect(url_for('user.profile'))
            current_user.phone = phone
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('user.profile'))
    return render_template('user/profile.html')


@user_bp.route('/game-ids', methods=['GET', 'POST'])
@login_required
@player_required
def game_ids():
    games = Game.query.filter_by(is_active=True).all()
    user_gids = GameID.query.filter_by(user_id=current_user.id).all()
    if request.method == 'POST':
        game_id = request.form.get('game_id', type=int)
        game_uid = request.form.get('game_uid', '').strip()
        game_username = request.form.get('game_username', '').strip()
        server_region = request.form.get('server_region', '').strip()
        if not game_id or not game_uid:
            flash('Game and UID required.', 'danger')
        else:
            existing = GameID.query.filter_by(
                user_id=current_user.id, game_id=game_id, game_uid=game_uid
            ).first()
            if existing:
                flash('This Game ID already exists.', 'warning')
            else:
                gid = GameID(
                    user_id=current_user.id,
                    game_id=game_id,
                    game_uid=game_uid,
                    game_username=game_username,
                    server_region=server_region
                )
                db.session.add(gid)
                db.session.commit()
                flash('Game ID added.', 'success')
        return redirect(url_for('user.game_ids'))
    return render_template('user/game_ids.html', games=games, user_gids=user_gids)


@user_bp.route('/game-ids/<int:gid>/delete', methods=['POST'])
@login_required
@player_required
def delete_game_id(gid):
    record = GameID.query.filter_by(id=gid, user_id=current_user.id).first_or_404()
    db.session.delete(record)
    db.session.commit()
    flash('Game ID removed.', 'success')
    return redirect(url_for('user.game_ids'))


@user_bp.route('/transactions')
@login_required
@player_required
def transactions():
    page = request.args.get('page', 1, type=int)
    txns = WalletTransaction.query.filter_by(user_id=current_user.id).order_by(
        WalletTransaction.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    return render_template('user/transactions.html', txns=txns)


@user_bp.route('/my-rooms', methods=['GET', 'POST'])
@login_required
@player_required
def my_rooms():
    from app.models.game import Game
    from datetime import datetime
    games = Game.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Room name required.', 'danger')
            return redirect(url_for('user.my_rooms'))
        from decimal import Decimal
        from app.services.wallet_service import hold_balance
        stake = Decimal(str(request.form.get('stake_amount') or 0))
        is_challenge = bool(request.form.get('is_challenge')) or stake > 0
        room = Room(
            name=name,
            game_id=request.form.get('game_id', type=int) or None,
            tournament_id=request.form.get('tournament_id', type=int) or None,
            created_by=current_user.id,
            room_id=request.form.get('room_id') or None,
            password=request.form.get('password') or None,
            instructions=request.form.get('instructions') or None,
            max_players=2 if is_challenge else int(request.form.get('max_players') or 50),
            entry_fee=stake,
            stake_amount=stake,
            is_challenge=is_challenge,
            host_plays=bool(request.form.get('host_plays', '1')),
            is_public=bool(request.form.get('is_public')),
            status='waiting',
            current_players=1 if bool(request.form.get('host_plays', '1')) else 0
        )
        if 'cover_image' in request.files:
            f = request.files['cover_image']
            if f and f.filename:
                room.cover_image = upload_image(f, 'rooms')
        mt = request.form.get('match_time')
        if mt:
            try:
                room.match_time = datetime.fromisoformat(mt)
            except ValueError:
                pass
        if is_challenge and stake > 0:
            try:
                txn, _ = hold_balance(
                    user_id=current_user.id, amount=stake, actor_id=current_user.id,
                    reason=f'Challenge stake: {name}', related_type='room_stake')
                room.host_hold_txn_id = txn.id
            except WalletServiceError as e:
                flash(str(e), 'danger')
                return redirect(url_for('user.my_rooms'))
        db.session.add(room)
        db.session.commit()
        flash('Room created!' + (' Stake held.' if stake > 0 else ''), 'success')
        return redirect(url_for('user.room_detail', room_id=room.id))

    # Rooms user created + rooms from joined tournaments
    my_created = Room.query.filter_by(created_by=current_user.id).order_by(Room.created_at.desc()).all()
    tournament_ids = [p.tournament_id for p in TournamentParticipant.query.filter_by(user_id=current_user.id).all()]
    joined_rooms = Room.query.filter(Room.tournament_id.in_(tournament_ids)).all() if tournament_ids else []
    return render_template('user/rooms.html', rooms=my_created, joined_rooms=joined_rooms, games=games)

@user_bp.route('/apply-agent', methods=['GET', 'POST'])
@login_required
@player_required
def apply_agent():
    if current_user.is_agent():
        flash('You are already an agent.', 'info')
        return redirect(url_for('agent.dashboard'))
    existing = AgentApplication.query.filter_by(user_id=current_user.id).first()
    if request.method == 'POST':
        try:
            doc_url = None
            if 'verification_document' in request.files:
                f = request.files['verification_document']
                if f and f.filename:
                    doc_url = upload_image(f, 'agent_docs')
            data = {
                'full_name': request.form.get('full_name'),
                'phone': request.form.get('phone'),
                'email': request.form.get('email') or current_user.email,
                'address': request.form.get('address'),
                'payment_details': request.form.get('payment_details'),
                'experience': request.form.get('experience'),
                'social_links': request.form.get('social_links'),
                'verification_document': doc_url,
                'message': request.form.get('message'),
            }
            apply_for_agent(current_user.id, data)
            db.session.commit()
            flash('Agent application submitted. Await admin review.', 'success')
            return redirect(url_for('user.dashboard'))
        except WalletServiceError as e:
            flash(str(e), 'danger')
            db.session.rollback()
    return render_template('user/apply_agent.html', existing=existing)




@user_bp.route('/tournaments/<int:t_id>/join', methods=['POST'])
@login_required
@player_required
def join_tournament_route(t_id):
    use_wallet = request.form.get('pay_method', 'wallet') == 'wallet'
    payment_ss = None
    if 'payment_ss' in request.files:
        f = request.files['payment_ss']
        if f and f.filename:
            payment_ss = upload_image(f, 'tournament_join')
    try:
        join_tournament(
            current_user.id, t_id,
            payment_ss=payment_ss,
            payment_note=request.form.get('payment_note'),
            use_wallet=use_wallet
        )
        db.session.commit()
        flash('Joined tournament!' if use_wallet else 'Join request sent — host will verify your payment.', 'success')
    except WalletServiceError as e:
        db.session.rollback()
        flash(str(e), 'danger')
    tournament = Tournament.query.get(t_id)
    return redirect(url_for('public.tournament_detail', slug=tournament.slug if tournament else ''))

@user_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@player_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'password':
            current_pw = request.form.get('current_password')
            new_pw = request.form.get('new_password')
            confirm = request.form.get('confirm_password')
            if not current_user.check_password(current_pw):
                flash('Current password incorrect.', 'danger')
            elif len(new_pw or '') < 6:
                flash('New password must be at least 6 characters.', 'danger')
            elif new_pw != confirm:
                flash('Passwords do not match.', 'danger')
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                flash('Password updated.', 'success')
        return redirect(url_for('user.settings'))
    return render_template('user/settings.html')


@user_bp.route('/notifications')
@login_required
def notifications():
    page = request.args.get('page', 1, type=int)
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    # Mark as read
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('user/notifications.html', notifications=notifs)


# ---- Challenge rooms, OTP settlement, tournament result SS ----
from app.models.wallet import TransactionType
from app.services.wallet_service import debit_wallet, credit_wallet, hold_balance, release_hold
from app.services.notification_service import notify
from decimal import Decimal
from datetime import datetime, timedelta
import random


@user_bp.route('/rooms/<int:room_id>')
@login_required
@player_required
def room_detail(room_id):
    room = Room.query.get_or_404(room_id)
    return render_template('user/room_detail.html', room=room)


@user_bp.route('/rooms/<int:room_id>/join', methods=['POST'])
@login_required
@player_required
def join_room(room_id):
    room = Room.query.get_or_404(room_id)
    if room.created_by == current_user.id:
        flash('You are the host.', 'warning')
        return redirect(url_for('user.room_detail', room_id=room_id))
    if room.is_challenge and room.opponent_id:
        flash('Room already has an opponent.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    if not room.is_challenge and (room.current_players or 0) >= (room.max_players or 50):
        flash('Room is full.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    if room.status not in ('waiting', 'joined', None, 'WAITING'):
        flash('Room is not open to join.', 'danger')
        return redirect(url_for('public.rooms'))
    if room.password and request.form.get('password') != room.password:
        flash('Wrong room password.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    stake = Decimal(str(room.stake_amount or room.entry_fee or 0))
    try:
        if (room.is_challenge or stake > 0) and stake > 0:
            txn, _ = hold_balance(
                user_id=current_user.id, amount=stake, actor_id=current_user.id,
                reason=f'Challenge stake join: {room.name}', related_type='room_stake')
            room.opponent_hold_txn_id = txn.id
        if room.is_challenge or (room.stake_amount and float(room.stake_amount or 0) > 0):
            room.opponent_id = current_user.id
            room.current_players = 2 if room.host_plays is not False else 1
            room.status = 'joined'
            msg = 'Joined room! Play, then settle with OTP.'
        else:
            room.current_players = (room.current_players or 0) + 1
            if not room.opponent_id:
                room.opponent_id = current_user.id
            msg = 'Joined room!'
        db.session.commit()
        if room.created_by:
            notify(room.created_by, 'Player Joined',
                   f'{current_user.username} joined your room {room.name}.', 'room', f'/rooms/{room.id}')
        flash(msg, 'success')
    except WalletServiceError as e:
        db.session.rollback()
        flash(str(e), 'danger')
    return redirect(url_for('user.room_detail', room_id=room_id))


@user_bp.route('/rooms/<int:room_id>/start', methods=['POST'])
@login_required
@player_required
def start_room(room_id):
    room = Room.query.get_or_404(room_id)
    if current_user.id not in (room.created_by, room.opponent_id):
        flash('Not your room.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    if room.status != 'joined':
        flash('Need both players first.', 'warning')
        return redirect(url_for('user.room_detail', room_id=room_id))
    room.status = 'playing'
    db.session.commit()
    flash('Match started.', 'success')
    return redirect(url_for('user.room_detail', room_id=room_id))


@user_bp.route('/rooms/<int:room_id>/upload-ss', methods=['POST'])
@login_required
@player_required
def room_upload_ss(room_id):
    room = Room.query.get_or_404(room_id)
    if current_user.id not in (room.created_by, room.opponent_id):
        flash('Not your room.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    f = request.files.get('screenshot')
    if not f or not f.filename:
        flash('Select a screenshot.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    url = upload_image(f, 'room_results')
    if current_user.id == room.created_by:
        room.host_screenshot = url
    else:
        room.opponent_screenshot = url
    db.session.commit()
    flash('Screenshot uploaded.', 'success')
    return redirect(url_for('user.room_detail', room_id=room_id))


@user_bp.route('/rooms/<int:room_id>/declare-result', methods=['POST'])
@login_required
@player_required
def room_declare_result(room_id):
    room = Room.query.get_or_404(room_id)
    if current_user.id not in (room.created_by, room.opponent_id):
        flash('Not your room.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    if room.status not in ('playing', 'joined', 'settling'):
        flash('Cannot declare result now.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    winner_id = request.form.get('winner_id', type=int)
    if winner_id not in (room.created_by, room.opponent_id):
        flash('Invalid winner.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    loser_id = room.opponent_id if winner_id == room.created_by else room.created_by
    stake = Decimal(str(room.stake_amount or room.entry_fee or 0))
    transfer_amt = stake if stake > 0 else Decimal(str(request.form.get('amount') or 0))
    if transfer_amt <= 0:
        flash('Stake/amount required.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    otp = f'{random.randint(100000, 999999)}'
    room.winner_id = winner_id
    room.loser_id = loser_id
    room.pending_transfer_amount = transfer_amt
    room.settlement_otp = otp
    room.settlement_otp_expires = datetime.utcnow() + timedelta(minutes=15)
    room.status = 'settling'
    db.session.commit()
    notify(loser_id, 'Confirm Transfer OTP',
           f'Lost room {room.name}. Pay Rs.{transfer_amt}. OTP: {otp} (15 min).',
           'room', f'/rooms/{room.id}')
    notify(winner_id, 'Waiting for OTP',
           f'Loser must confirm OTP transfer of Rs.{transfer_amt}.', 'room', f'/rooms/{room.id}')
    flash('Result declared. Loser must enter OTP to transfer.', 'info')
    if current_user.id == loser_id:
        flash(f'Your OTP: {otp}', 'warning')
    return redirect(url_for('user.room_detail', room_id=room_id))


@user_bp.route('/rooms/<int:room_id>/confirm-otp', methods=['POST'])
@login_required
@player_required
def room_confirm_otp(room_id):
    room = Room.query.get_or_404(room_id)
    if current_user.id != room.loser_id:
        flash('Only the loser confirms OTP transfer.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    if room.status != 'settling':
        flash('No pending settlement.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    otp = (request.form.get('otp') or '').strip()
    if not room.settlement_otp or otp != room.settlement_otp:
        flash('Invalid OTP.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    if room.settlement_otp_expires and datetime.utcnow() > room.settlement_otp_expires:
        flash('OTP expired.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    amount = Decimal(str(room.pending_transfer_amount or 0))
    stake = Decimal(str(room.stake_amount or 0))
    try:
        if room.host_hold_txn_id and room.opponent_hold_txn_id and stake > 0:
            release_hold(room.created_by, stake, actor_id=current_user.id, reason='Room stake release host')
            release_hold(room.opponent_id, stake, actor_id=current_user.id, reason='Room stake release opponent')
            debit_wallet(room.loser_id, stake, TransactionType.ROOM_TRANSFER, actor_id=current_user.id,
                         reason=f'Lost challenge #{room.id}', related_id=room.id, related_type='room')
            credit_wallet(room.winner_id, stake * 2, TransactionType.ROOM_TRANSFER, actor_id=current_user.id,
                          reason=f'Won challenge #{room.id}', related_id=room.id, related_type='room')
            paid = stake * 2
        else:
            debit_wallet(room.loser_id, amount, TransactionType.ROOM_TRANSFER, actor_id=current_user.id,
                         reason=f'Lost room #{room.id}', related_id=room.id, related_type='room')
            credit_wallet(room.winner_id, amount, TransactionType.ROOM_TRANSFER, actor_id=current_user.id,
                          reason=f'Won room #{room.id}', related_id=room.id, related_type='room')
            paid = amount
        room.status = 'completed'
        room.settlement_otp = None
        db.session.commit()
        notify(room.winner_id, 'You Won!', f'Rs.{paid} credited from room {room.name}.', 'room', '/wallet/')
        flash('Transfer confirmed. Room completed.', 'success')
    except WalletServiceError as e:
        db.session.rollback()
        flash(str(e), 'danger')
    return redirect(url_for('user.room_detail', room_id=room_id))


@user_bp.route('/tournaments/<int:t_id>/submit-result', methods=['GET', 'POST'])
@login_required
@player_required
def submit_tournament_result(t_id):
    tournament = Tournament.query.get_or_404(t_id)
    part = TournamentParticipant.query.filter_by(tournament_id=t_id, user_id=current_user.id).first()
    if not part:
        flash('Join the tournament first.', 'danger')
        return redirect(url_for('public.tournament_detail', slug=tournament.slug))
    if request.method == 'POST':
        from app.models.tournament import MatchResult, ResultStatus, Match
        notes = request.form.get('notes', '')
        f = request.files.get('screenshot')
        proof = upload_image(f, 'tournament_results') if f and f.filename else None
        match = Match.query.filter_by(tournament_id=t_id).first()
        if not match:
            match = Match(tournament_id=t_id, name='Player result', status='completed')
            db.session.add(match)
            db.session.flush()
        result = MatchResult(
            match_id=match.id, tournament_id=t_id, winner_id=current_user.id,
            notes=notes, proof_screenshot=proof, submitted_by=current_user.id,
            status=ResultStatus.PENDING)
        db.session.add(result)
        db.session.commit()
        flash('Screenshot submitted. Admin will review.', 'success')
        return redirect(url_for('public.tournament_detail', slug=tournament.slug))
    return render_template('user/submit_result.html', tournament=tournament)


def _settle_room_payout(room):
    """Debit loser / credit winner (or release holds and pay pot)."""
    from app.models.wallet import TransactionType
    stake = Decimal(str(room.stake_amount or 0))
    amount = Decimal(str(room.pending_transfer_amount or stake or 0))
    if amount <= 0 and stake <= 0:
        raise WalletServiceError('No stake/amount to transfer')
    if room.host_hold_txn_id and room.opponent_hold_txn_id and stake > 0:
        release_hold(room.created_by, stake, actor_id=room.created_by, reason='Room stake release host')
        release_hold(room.opponent_id, stake, actor_id=room.created_by, reason='Room stake release opponent')
        debit_wallet(room.loser_id, stake, TransactionType.ROOM_TRANSFER, actor_id=room.created_by,
                     reason=f'Lost room #{room.id}', related_id=room.id, related_type='room')
        credit_wallet(room.winner_id, stake * 2, TransactionType.ROOM_TRANSFER, actor_id=room.created_by,
                      reason=f'Won room #{room.id}', related_id=room.id, related_type='room')
        return stake * 2
    debit_wallet(room.loser_id, amount, TransactionType.ROOM_TRANSFER, actor_id=room.created_by,
                 reason=f'Lost room #{room.id}', related_id=room.id, related_type='room')
    credit_wallet(room.winner_id, amount, TransactionType.ROOM_TRANSFER, actor_id=room.created_by,
                  reason=f'Won room #{room.id}', related_id=room.id, related_type='room')
    return amount


@user_bp.route('/rooms/<int:room_id>/claim-win', methods=['POST'])
@login_required
@player_required
def room_claim_win(room_id):
    """Winner uploads SS and claims win → host must verify → auto payout."""
    room = Room.query.get_or_404(room_id)
    players = [room.created_by, room.opponent_id]
    if room.host_plays is False:
        players = [room.opponent_id]  # host not a player
    if current_user.id not in [p for p in players if p]:
        # host who doesn't play can still open claim for a player
        if current_user.id != room.created_by:
            flash('Only match players can claim win.', 'danger')
            return redirect(url_for('user.room_detail', room_id=room_id))
    if room.status not in ('playing', 'joined'):
        flash('Match not in progress.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))

    # Winner is the claimant (or host selects winner_id)
    winner_id = request.form.get('winner_id', type=int) or current_user.id
    if winner_id not in (room.created_by, room.opponent_id):
        flash('Invalid winner.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    loser_id = room.opponent_id if winner_id == room.created_by else room.created_by
    if room.host_plays is False and room.opponent_id:
        # multi or host-spectator: need explicit loser — for 1v1 opponent is the other player
        pass

    f = request.files.get('screenshot')
    if not f or not f.filename:
        flash('Winner must upload result screenshot.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    proof = upload_image(f, 'room_results')

    stake = Decimal(str(room.stake_amount or room.entry_fee or 0))
    room.winner_id = winner_id
    room.loser_id = loser_id
    room.claim_screenshot = proof
    room.pending_transfer_amount = stake if stake > 0 else Decimal(str(request.form.get('amount') or 0))
    room.status = 'pending_verify'
    if current_user.id == room.created_by:
        room.host_screenshot = proof
    else:
        room.opponent_screenshot = proof
    db.session.commit()

    try:
        from app.services.notification_service import notify_admin
        notify_admin('Room result claim', f'Room #{room.id} {room.name}: win claimed. Verify in Admin → Room Claims.', f'/admin/room-claims')
    except Exception:
        pass
    notify(room.created_by, 'Result Claimed',
           f'{current_user.username} claimed win on room {room.name}. SS uploaded. Admin must verify to auto-pay winner.',
           'room', f'/rooms/{room.id}')
    if room.opponent_id:
        notify(room.opponent_id, 'Win Claimed',
               f'A win was claimed on room {room.name}. Waiting for admin verification.',
               'room', f'/rooms/{room.id}')
    flash('Win claimed with screenshot. Waiting for admin verification.', 'info')
    return redirect(url_for('user.room_detail', room_id=room_id))


@user_bp.route('/rooms/<int:room_id>/host-verify', methods=['POST'])
@login_required
@player_required
def room_host_verify(room_id):
    """Host verifies winner SS → auto deduct loser, credit winner."""
    room = Room.query.get_or_404(room_id)
    if current_user.id != room.created_by:
        flash('Only the host can verify the result.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    if room.status != 'pending_verify':
        flash('No pending claim to verify.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    if not room.winner_id or not room.loser_id:
        flash('Winner/loser not set.', 'danger')
        return redirect(url_for('user.room_detail', room_id=room_id))
    action = request.form.get('action', 'approve')
    if action == 'reject':
        room.status = 'playing'
        room.winner_id = None
        room.loser_id = None
        room.claim_screenshot = None
        room.pending_transfer_amount = None
        db.session.commit()
        flash('Claim rejected. Match continues.', 'warning')
        notify(room.winner_id or room.opponent_id, 'Claim Rejected',
               f'Host rejected win claim on {room.name}.', 'room', f'/rooms/{room.id}')
        return redirect(url_for('user.room_detail', room_id=room_id))
    try:
        paid = _settle_room_payout(room)
        room.status = 'completed'
        room.settlement_otp = None
        db.session.commit()
        notify(room.winner_id, 'You Won!',
               f'Host verified. Rs.{paid} credited from room {room.name}.', 'room', '/wallet/')
        notify(room.loser_id, 'Match Lost',
               f'Host verified result. Rs deducted for room {room.name}.', 'room', '/wallet/')
        flash(f'Verified! Rs.{paid} sent to winner automatically.', 'success')
    except WalletServiceError as e:
        db.session.rollback()
        flash(str(e), 'danger')
    return redirect(url_for('user.room_detail', room_id=room_id))


@user_bp.route('/create-tournament', methods=['GET', 'POST'])
@login_required
@player_required
def create_tournament():
    from app.models.game import Game
    import re
    def slugify(text):
        s = re.sub(r'[^a-zA-Z0-9\s-]', '', (text or '').lower())
        return re.sub(r'[\s-]+', '-', s).strip('-') or 'tournament'
    games = Game.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Name required.', 'danger')
            return redirect(url_for('user.create_tournament'))
        try:
            entry = Decimal(str(request.form.get('entry_fee') or 0))
            prize = Decimal(str(request.form.get('prize_pool') or 0))
        except Exception:
            flash('Invalid fee/prize.', 'danger')
            return redirect(url_for('user.create_tournament'))
        base = slugify(name)
        slug = base
        n = 1
        while Tournament.query.filter_by(slug=slug).first():
            slug = f'{base}-{n}'
            n += 1
        t = Tournament(
            name=name,
            slug=slug,
            game_id=request.form.get('game_id', type=int),
            description=request.form.get('description'),
            rules=request.form.get('rules'),
            entry_fee=entry,
            prize_pool=prize,
            max_players=int(request.form.get('max_players') or 50),
            prize_distribution=request.form.get('prize_distribution'),
            status='upcoming',
            created_by=current_user.id,
            is_user_hosted=True,
            payment_instructions=request.form.get('payment_instructions'),
            pot_balance=0
        )
        if 'payment_qr' in request.files:
            f = request.files['payment_qr']
            if f and f.filename:
                t.payment_qr = upload_image(f, 'tournament_qr')
        if 'banner' in request.files:
            f = request.files['banner']
            if f and f.filename:
                t.banner = upload_image(f, 'tournaments')
        db.session.add(t)
        db.session.commit()
        flash('Tournament created! Players can join after paying entry fee.', 'success')
        return redirect(url_for('public.tournament_detail', slug=t.slug))
    return render_template('user/create_tournament.html', games=games)


@user_bp.route('/my-tournaments')
@login_required
@player_required
def my_tournaments():
    joined = TournamentParticipant.query.filter_by(user_id=current_user.id).order_by(
        TournamentParticipant.joined_at.desc()
    ).all()
    hosted = Tournament.query.filter_by(created_by=current_user.id).order_by(Tournament.created_at.desc()).all()
    pending_joins = []
    for t in hosted:
        pending_joins.extend(
            TournamentParticipant.query.filter_by(tournament_id=t.id, status='pending').all()
        )
    pending_results = []
    from app.models.tournament import MatchResult, ResultStatus
    for t in hosted:
        pending_results.extend(
            MatchResult.query.filter_by(tournament_id=t.id, status=ResultStatus.PENDING).all()
        )
    return render_template('user/tournaments.html', joined=joined, hosted=hosted,
                           pending_joins=pending_joins, pending_results=pending_results)


@user_bp.route('/tournaments/<int:t_id>/verify-join/<int:part_id>', methods=['POST'])
@login_required
@player_required
def verify_join(t_id, part_id):
    from app.services.tournament_service import host_verify_join
    approve = request.form.get('action') != 'reject'
    try:
        host_verify_join(t_id, part_id, current_user.id, approve=approve)
        db.session.commit()
        flash('Join verified.' if approve else 'Join rejected.', 'success' if approve else 'warning')
    except WalletServiceError as e:
        db.session.rollback()
        flash(str(e), 'danger')
    return redirect(url_for('user.my_tournaments'))


@user_bp.route('/tournaments/results/<int:res_id>/host-verify', methods=['POST'])
@login_required
@player_required
def host_verify_result(res_id):
    from app.services.tournament_service import host_verify_tournament_result
    prize = request.form.get('prize_amount')
    try:
        host_verify_tournament_result(res_id, current_user.id, prize)
        db.session.commit()
        flash('Result verified. Prize paid from tournament pot.', 'success')
    except WalletServiceError as e:
        db.session.rollback()
        flash(str(e), 'danger')
    return redirect(url_for('user.my_tournaments'))

