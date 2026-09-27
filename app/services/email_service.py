"""Send transactional email. From: Esports.info@argan.com.np"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app

logger = logging.getLogger(__name__)


def _mail_cfg():
    return {
        'server': current_app.config.get('MAIL_SERVER') or '',
        'port': int(current_app.config.get('MAIL_PORT') or 587),
        'use_tls': current_app.config.get('MAIL_USE_TLS', True),
        'username': current_app.config.get('MAIL_USERNAME') or '',
        'password': current_app.config.get('MAIL_PASSWORD') or '',
        'sender': current_app.config.get('MAIL_DEFAULT_SENDER') or 'Esports.info@argan.com.np',
        'admin': current_app.config.get('ADMIN_EMAIL') or 'info@argan.com.np',
    }


def send_email(to_email, subject, body_text, body_html=None):
    """Send one email. Returns True on success. Skips if MAIL_PASSWORD not set."""
    if not to_email:
        return False
    cfg = _mail_cfg()
    if not cfg['server'] or not cfg['username'] or not cfg['password']:
        logger.debug('Mail not configured (set MAIL_PASSWORD) — skip: %s', subject)
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"ESPORTS ARENA <{cfg['sender']}>"
        msg['To'] = to_email
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
        if body_html:
            msg.attach(MIMEText(body_html, 'html', 'utf-8'))
        with smtplib.SMTP(cfg['server'], cfg['port'], timeout=20) as smtp:
            if cfg['use_tls']:
                smtp.starttls()
            smtp.login(cfg['username'], cfg['password'])
            smtp.sendmail(cfg['sender'], [to_email], msg.as_string())
        return True
    except Exception as e:
        logger.warning('Email failed to %s: %s', to_email, e)
        return False


def send_admin_email(subject, body_text):
    cfg = _mail_cfg()
    return send_email(cfg['admin'], subject, body_text)


def email_user(user, subject, message, link=None):
    if not user or not getattr(user, 'email', None):
        return False
    text = message
    if link:
        text += f'\n\nOpen: {link}'
    text += '\n\n— ESPORTS ARENA'
    return send_email(user.email, subject, text)
