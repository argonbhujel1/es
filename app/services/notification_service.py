from app import db
from app.models.notification import Notification


def notify(user_id, title, message, notif_type=None, link=None, email=True):
    n = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=notif_type,
        link=link
    )
    db.session.add(n)
    if email:
        try:
            from app.models.user import User
            from app.services.email_service import email_user
            user = User.query.get(user_id)
            if user:
                email_user(user, f'[ESPORTS ARENA] {title}', message, link)
        except Exception:
            pass
    return n


def notify_many(user_ids, title, message, notif_type=None, link=None, email=True):
    for uid in user_ids:
        notify(uid, title, message, notif_type, link, email=email)


def notify_all_users(title, message, notif_type=None, link=None, role=None):
    from app.models.user import User, Role
    q = User.query.filter_by(is_active=True)
    if role:
        q = q.filter_by(role=role)
    users = q.all()
    for u in users:
        notify(u.id, title, message, notif_type, link, email=True)
    return len(users)


def notify_admin(title, message, link=None):
    """In-app notify all admins + email ADMIN_EMAIL."""
    from app.models.user import User, Role
    from app.services.email_service import send_admin_email
    admins = User.query.filter_by(role=Role.ADMIN, is_active=True).all()
    for a in admins:
        notify(a.id, title, message, 'admin', link, email=True)
    try:
        send_admin_email(f'[ESPORTS ARENA] {title}', message + (f'\n\n{link}' if link else ''))
    except Exception:
        pass
