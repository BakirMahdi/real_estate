"""Send transactional emails (currently just the sign-up verification code).

Configured via SMTP_* env vars. When SMTP_HOST is unset, the code is logged to
the backend console instead of sent, so the sign-up flow still works in local
development before real SMTP credentials are provided.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage


def _smtp_config():
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from_addr": os.getenv("SMTP_FROM", "").strip() or os.getenv("SMTP_USER", "").strip(),
        # 465 => implicit TLS (SMTPS); anything else => STARTTLS on a plain
        # connection, which is the common 587 setup.
        "use_ssl": os.getenv("SMTP_PORT", "587") == "465",
        # Skip TLS certificate verification. Needed on networks that intercept
        # TLS with a self-signed root CA (corporate/school proxies, some
        # antivirus) which would otherwise fail verification. Off by default;
        # only enable it in a trusted dev environment.
        "skip_tls_verify": os.getenv("SMTP_SKIP_TLS_VERIFY", "false").lower() == "true",
    }


def _tls_context(skip_verify: bool) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if skip_verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def send_verification_email(to_email: str, code: str) -> None:
    """Email `code` to `to_email`. Raises on SMTP failure.

    Falls back to logging the code (no send) when SMTP_HOST is not configured.
    """
    cfg = _smtp_config()

    if not cfg["host"]:
        # Dev fallback: no SMTP configured, so surface the code in the logs
        # instead of silently dropping it. Never do this with a real SMTP setup.
        print(f"[email] SMTP not configured; verification code for {to_email} is {code}")
        return

    msg = EmailMessage()
    msg["Subject"] = "Votre code de vérification Rews"
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_email
    msg.set_content(
        f"Bienvenue sur Rews !\n\n"
        f"Votre code de vérification est : {code}\n\n"
        f"Il expire dans 10 minutes. Si vous n'êtes pas à l'origine de cette "
        f"demande, ignorez cet e-mail."
    )

    context = _tls_context(cfg["skip_tls_verify"])
    if cfg["use_ssl"]:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context) as server:
            if cfg["user"]:
                server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.starttls(context=context)
            if cfg["user"]:
                server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
