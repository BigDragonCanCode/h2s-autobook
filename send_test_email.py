from __future__ import annotations

from dotenv import load_dotenv

from config import ENV_PATH
from notifier_email import ResendEmailNotifier


def main() -> int:
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    notifier = ResendEmailNotifier.from_env()
    if notifier is None:
        print("Email notifier is not configured. Check RESEND_API_KEY, RESEND_FROM, and NOTIFY_EMAIL_TO.")
        return 1
    try:
        ok = notifier.send_text("FlatRadar test email\n\nThis is a test message to verify email delivery is still working.")
        print("Email send ok." if ok else "Email send failed.")
        return 0 if ok else 1
    finally:
        notifier.close()


if __name__ == "__main__":
    raise SystemExit(main())
