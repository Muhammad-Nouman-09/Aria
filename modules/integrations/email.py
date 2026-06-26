"""Email read/send over IMAP/SMTP (optional, config-gated).

Uses only the standard library (imaplib/smtplib/email). All operations are
no-ops returning a clear message unless email is fully configured in .env.
For Gmail/Outlook use an app password, not your main password.
"""

from __future__ import annotations

import imaplib
import smtplib
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import EmailMessage

from config import Settings


class EmailClient:
    def __init__(self, settings: Settings):
        self.s = settings

    def _not_configured(self) -> dict:
        return {"error": "Email is not configured. Set EMAIL_ENABLED=true and "
                         "EMAIL_ADDRESS/EMAIL_PASSWORD/IMAP_HOST/SMTP_HOST in .env."}

    # ----- read -----
    def read_email(self, folder: str = "INBOX", max_emails: int = 10,
                   unread_only: bool = True,
                   search_query: str | None = None) -> dict:
        if not self.s.has_email:
            return self._not_configured()
        try:
            conn = imaplib.IMAP4_SSL(self.s.imap_host, self.s.imap_port)
            conn.login(self.s.email_address, self.s.email_password)
            conn.select(folder)

            criteria = ["UNSEEN"] if unread_only else ["ALL"]
            if search_query:
                criteria = ["TEXT", f'"{search_query}"']
            typ, data = conn.search(None, *criteria)
            ids = data[0].split() if data and data[0] else []
            ids = ids[-max_emails:][::-1]  # newest first

            emails = []
            for mid in ids:
                typ, msg_data = conn.fetch(mid, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                msg = message_from_bytes(msg_data[0][1])
                emails.append({
                    "from": _decode(msg.get("From", "")),
                    "subject": _decode(msg.get("Subject", "")),
                    "date": msg.get("Date", ""),
                    "preview": _body_preview(msg),
                })
            conn.logout()
            return {"folder": folder, "count": len(emails), "emails": emails}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Failed to read email: {e}"}

    # ----- send -----
    def send_email(self, to: str, subject: str, body: str,
                   cc: str | None = None) -> dict:
        if not self.s.has_email:
            return self._not_configured()
        try:
            msg = EmailMessage()
            msg["From"] = self.s.email_address
            msg["To"] = to
            if cc:
                msg["Cc"] = cc
            msg["Subject"] = subject
            msg.set_content(body)

            with smtplib.SMTP_SSL(self.s.smtp_host, self.s.smtp_port) as server:
                server.login(self.s.email_address, self.s.email_password)
                server.send_message(msg)
            return {"status": "sent", "to": to, "subject": subject}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Failed to send email: {e}"}


def _decode(raw: str) -> str:
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def _body_preview(msg, limit: int = 300) -> str:
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    text = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                    break
                except Exception:
                    continue
    else:
        try:
            text = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            text = str(msg.get_payload())
    text = " ".join(text.split())
    return text[:limit]
