from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable, Protocol, Sequence


class SmtpLike(Protocol):
    def __enter__(self) -> "SmtpLike": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
    def starttls(self) -> None: ...
    def login(self, user: str, password: str) -> None: ...
    def send_message(self, message: EmailMessage) -> None: ...


@dataclass(frozen=True, slots=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    mail_to: str
    mail_from: str
    use_ssl: bool = True


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    filename: str
    content: bytes
    maintype: str
    subtype: str


def send_daily_email(
    *,
    config: SmtpConfig,
    subject: str,
    html_body: str,
    attachments: Sequence[EmailAttachment] | None = None,
    smtp_factory: Callable[[str, int, int], SmtpLike] | None = None,
) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.mail_from
    message["To"] = config.mail_to
    message.set_content("Your Bilibili daily report is available in the HTML version of this email.")
    message.add_alternative(html_body, subtype="html")
    for attachment in attachments or ():
        message.add_attachment(
            attachment.content,
            maintype=attachment.maintype,
            subtype=attachment.subtype,
            filename=attachment.filename,
        )

    factory = smtp_factory or (smtplib.SMTP_SSL if config.use_ssl else smtplib.SMTP)
    with factory(config.host, config.port, 30) as smtp:
        if not config.use_ssl:
            smtp.starttls()
        smtp.login(config.user, config.password)
        smtp.send_message(message)
