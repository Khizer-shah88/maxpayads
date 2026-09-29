"""Publisher auth — status-aware login responses (see test file for behavior)."""


def status_login_message(status: str):
    """Error message for a non-available account status; None when normal.

    Returned by the login endpoints so banned/suspended/pending users get a
    clear reason instead of the generic 'Invalid email or password' typo text.
    """
    if not status:
        return None
    if status == "banned" or status == "removed":
        return "This account is no longer available. Contact your account manager."
    if status == "suspended":
        return "This account is suspended. Contact your account manager."
    if status == "pending":
        return "Your account is awaiting approval. You'll be notified once approved."
    return None