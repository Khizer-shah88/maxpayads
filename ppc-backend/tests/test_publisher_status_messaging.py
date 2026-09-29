"""
Publisher auth — status-aware login messages.

Fixes:
1. Suspended/banned/removed accounts returned the generic
   "Invalid email or password" (indistinguishable from a wrong password),
   which reads as "my correct credentials are rejected".
2. Login rate-limit + admin-on-publisher-login cases are explicit.

auth_service.login_status_message maps the account's status to the message
the login endpoint returns (401/403 keep their codes).
"""
import pytest

from app.services.publisher_status_messaging import status_login_message


def test_each_status_has_a_clear_message():
    for status in ("suspended", "banned", "removed", "pending"):
        msg = status_login_message(status)
        assert msg and msg != "Invalid email or password"
    # Active accounts keep the normal flow (no special message)
    assert status_login_message("active") is None


def test_unavailable_accounts_cannot_look_like_typos():
    # The three "unavailable" states must be clearly-worded (not the typo text)
    for status in ("suspended", "banned", "removed"):
        assert "not available" in status_login_message(status).lower() or \
            "cannot log in" in status_login_message(status).lower()