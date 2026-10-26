"""Updater capability policy; no role elevation and no financial store access."""
import hashlib
import hmac
import json

from app.services.user_identity import validate_user_id


def valid_identity(user):
    try:
        return bool(user and validate_user_id(user.get('id')))
    except (ValueError, TypeError):
        return False


def active_account(user):
    return bool(user and not user.get('must_change_password') and user.get('disabled') is not True
                and user.get('is_active') is not False and user.get('active') is not False)


def stored_permission(user):
    permissions = user.get('permissions') if user else None
    return isinstance(permissions, dict) and permissions.get('system_update') is True


def can_system_update(user):
    return bool(valid_identity(user) and active_account(user) and
                (user.get('role') == 'admin' or user.get('role') == 'user' and stored_permission(user)))


def session_stamp(user, secret):
    value = json.dumps([user.get('id'), user.get('salt'), user.get('password_hash')], separators=(',', ':')).encode()
    return hmac.new(secret.encode(), value, hashlib.sha256).hexdigest()
