from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User, Role
from app.models.wallet import Wallet
from app.services.wallet_service import get_or_create_wallet
from datetime import datetime
from decimal import Decimal

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('user.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()
        if user and user.check_password(password):
            if user.is_blocked:
                flash('Your account has been blocked. Contact support.', 'danger')
                return render_template('auth/login.html')
            if not user.is_active:
                flash('Account is inactive.', 'danger')
                return render_template('auth/login.html')
            login_user(user, remember=bool(request.form.get('remember')))
            user.last_login = datetime.utcnow()
            db.session.commit()
            next_page = request.args.get('next')
            if user.is_admin():
                return redirect(next_page or url_for('admin.dashboard'))
            if user.is_agent():
                return redirect(next_page or url_for('agent.dashboard'))
            return redirect(next_page or url_for('user.dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('user.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip() or None

        errors = []
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        if not email or '@' not in email:
            errors.append('Valid email required.')
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')
        if User.query.filter_by(username=username).first():
            errors.append('Username already taken.')
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered.')
        if phone and User.query.filter_by(phone=phone).first():
            errors.append('Phone already registered.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/register.html')

        user = User(
            username=username,
            email=email,
            full_name=full_name or username,
            phone=phone,
            role=Role.PLAYER
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        wallet = Wallet(user_id=user.id, balance=Decimal('0'))
        db.session.add(wallet)
        db.session.commit()

        login_user(user)
        flash('Welcome to ESPORTS ARENA! Account created successfully.', 'success')
        return redirect(url_for('user.dashboard'))
    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('public.index'))
