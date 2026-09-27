from datetime import datetime
from decimal import Decimal
from app import db
from app.models.tournament import (
    Tournament, TournamentParticipant, TournamentStatus,
    MatchResult, ResultStatus, PrizeDistribution, Match
)
from app.models.wallet import TransactionType
from app.models.leaderboard import LeaderboardEntry
from app.models.audit import AuditLog
from app.services.wallet_service import debit_wallet, credit_wallet, WalletServiceError, InsufficientBalanceError
from app.services.notification_service import notify, notify_admin


def join_tournament(user_id, tournament_id, game_id_record=None, payment_ss=None, payment_note=None, use_wallet=True):
    """
    Admin tournament: immediate join, entry fee deducted (platform).
    User-hosted: entry fee → tournament pot; if offline QR, status=pending until host verifies.
    """
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        raise WalletServiceError('Tournament not found')

    if tournament.status not in (TournamentStatus.UPCOMING, TournamentStatus.APPROVED, TournamentStatus.LIVE):
        raise WalletServiceError('Tournament is not open for registration')

    if tournament.registration_deadline and datetime.utcnow() > tournament.registration_deadline:
        raise WalletServiceError('Registration deadline has passed')

    if (tournament.current_players or 0) >= (tournament.max_players or 100):
        raise WalletServiceError('Tournament is full')

    existing = TournamentParticipant.query.filter_by(
        tournament_id=tournament_id, user_id=user_id
    ).first()
    if existing:
        raise WalletServiceError('You have already joined this tournament')

    entry_fee = Decimal(str(tournament.entry_fee or 0))
    user_hosted = bool(tournament.is_user_hosted)
    txn = None

    # Offline QR path for user-hosted: pending until host verifies payment
    if user_hosted and not use_wallet:
        participant = TournamentParticipant(
            tournament_id=tournament_id,
            user_id=user_id,
            game_id_record=game_id_record,
            status='pending',
            payment_ss=payment_ss,
            payment_verified=False,
            payment_note=payment_note
        )
        db.session.add(participant)
        notify(tournament.created_by, 'Join request',
               f'User requested to join {tournament.name}. Verify payment to confirm.',
               'tournament', f'/my-tournaments')
        notify(user_id, 'Join pending',
               f'Waiting for host to verify your entry payment for {tournament.name}.',
               'tournament', f'/tournaments/{tournament.slug}')
        return participant

    if entry_fee > 0:
        try:
            txn, _ = debit_wallet(
                user_id=user_id,
                amount=entry_fee,
                transaction_type=TransactionType.TOURNAMENT_ENTRY,
                actor_id=user_id,
                reference=f'TOURNAMENT-{tournament_id}',
                reason=f'Entry fee for {tournament.name}',
                related_id=tournament_id,
                related_type='tournament',
                update_totals={'total_tournament_spent': entry_fee}
            )
        except InsufficientBalanceError:
            raise WalletServiceError(
                'Insufficient wallet balance. Add money via Admin or Agent, or pay host QR and wait for verify.'
            )

    # Credit pot for user-hosted tournaments
    if user_hosted and entry_fee > 0:
        tournament.pot_balance = Decimal(str(tournament.pot_balance or 0)) + entry_fee

    participant = TournamentParticipant(
        tournament_id=tournament_id,
        user_id=user_id,
        game_id_record=game_id_record,
        entry_transaction_id=txn.id if txn else None,
        status='joined',
        payment_verified=True
    )
    db.session.add(participant)
    tournament.current_players = (tournament.current_players or 0) + 1

    notify(user_id, 'Tournament Joined',
           f'You joined {tournament.name}. Entry Rs.{entry_fee}.',
           'tournament', f'/tournaments/{tournament.slug}')
    if tournament.created_by:
        notify(tournament.created_by, 'New participant',
               f'A player joined {tournament.name}.',
               'tournament', f'/my-tournaments')
    return participant


def host_verify_join(tournament_id, participant_id, host_id, approve=True):
    """Host verifies offline entry payment → confirm join and add to pot."""
    tournament = Tournament.query.get(tournament_id)
    if not tournament or tournament.created_by != host_id:
        raise WalletServiceError('Not your tournament')
    part = TournamentParticipant.query.filter_by(id=participant_id, tournament_id=tournament_id).first()
    if not part or part.status != 'pending':
        raise WalletServiceError('No pending join request')
    if not approve:
        db.session.delete(part)
        notify(part.user_id, 'Join rejected',
               f'Host rejected your join request for {tournament.name}.',
               'tournament')
        return
    entry_fee = Decimal(str(tournament.entry_fee or 0))
    # Offline payment already received by host via QR — track in pot accounting
    if entry_fee > 0:
        tournament.pot_balance = Decimal(str(tournament.pot_balance or 0)) + entry_fee
    part.status = 'joined'
    part.payment_verified = True
    tournament.current_players = (tournament.current_players or 0) + 1
    notify(part.user_id, 'Join confirmed',
           f'Host verified your payment. You are in {tournament.name}!',
           'tournament', f'/tournaments/{tournament.slug}')


def approve_result_and_distribute_prize(result_id, admin_id, prize_amount=None, ip=None):
    result = MatchResult.query.get(result_id)
    if not result:
        raise WalletServiceError('Result not found')
    if result.status != ResultStatus.PENDING:
        raise WalletServiceError('Result already processed')

    amount = Decimal(str(prize_amount or 0))
    tournament = Tournament.query.get(result.tournament_id)

    if amount <= 0 and tournament:
        amount = Decimal(str(tournament.prize_pool or 0))

    result.status = ResultStatus.APPROVED
    result.reviewed_by = admin_id
    result.reviewed_at = datetime.utcnow()

    if amount > 0 and result.winner_id:
        # User-hosted: pay from pot
        if tournament and tournament.is_user_hosted:
            pot = Decimal(str(tournament.pot_balance or 0))
            pay = min(amount, pot) if pot > 0 else amount
            if pot > 0:
                tournament.pot_balance = pot - pay
                # remaining cleared — host already got via QR
                remaining = Decimal(str(tournament.pot_balance or 0))
                if remaining > 0:
                    tournament.pot_balance = Decimal('0')
                    notify(tournament.created_by, 'Tournament pot cleared',
                           f'Remaining Rs.{remaining} cleared. You had already received entry fees in your QR.',
                           'tournament')
            amount = pay if pot > 0 else amount
        else:
            # Admin tournament — platform pays prize
            pass

        txn, wallet = credit_wallet(
            user_id=result.winner_id,
            amount=amount,
            transaction_type=TransactionType.PRIZE_REWARD,
            actor_id=admin_id,
            reason=f'Prize for tournament result #{result.id}',
            related_id=result.tournament_id,
            related_type='tournament',
            update_totals={'total_prize_won': amount}
        )
        prize = PrizeDistribution(
            tournament_id=result.tournament_id,
            match_id=result.match_id,
            match_result_id=result.id,
            winner_id=result.winner_id,
            amount=amount,
            previous_balance=txn.previous_balance,
            new_balance=txn.new_balance,
            transaction_id=txn.id,
            admin_id=admin_id,
            approved_at=datetime.utcnow()
        )
        db.session.add(prize)
        notify(result.winner_id, 'Prize Won!',
               f'You won Rs.{amount}!',
               'prize', '/wallet/')

        entry = LeaderboardEntry.query.filter_by(user_id=result.winner_id, period='overall').first()
        if not entry:
            entry = LeaderboardEntry(user_id=result.winner_id, period='overall')
            db.session.add(entry)
        entry.wins = (entry.wins or 0) + 1
        entry.points = (entry.points or 0) + 10
        entry.prize_earned = Decimal(str(entry.prize_earned or 0)) + amount

    if tournament:
        tournament.status = TournamentStatus.COMPLETED

    db.session.add(AuditLog(
        actor_id=admin_id, action='RESULT_APPROVED',
        target_type='match_result', target_id=result_id,
        amount=amount, ip_address=ip
    ))
    return result


def host_verify_tournament_result(result_id, host_id, prize_amount=None):
    """User tournament host verifies winner SS → pay from pot."""
    result = MatchResult.query.get(result_id)
    if not result:
        raise WalletServiceError('Result not found')
    tournament = Tournament.query.get(result.tournament_id)
    if not tournament or not tournament.is_user_hosted or tournament.created_by != host_id:
        raise WalletServiceError('Only tournament host can verify')
    if result.status != ResultStatus.PENDING:
        raise WalletServiceError('Already processed')
    return approve_result_and_distribute_prize(result_id, host_id, prize_amount)
