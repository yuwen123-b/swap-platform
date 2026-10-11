import html
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_message(recipient: str, code: str) -> MIMEMultipart:
    subject = "【绿换社区】您的验证码"
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;padding:32px;color:#1B4332;background:#F4FBF6">
      <h2 style="color:#2E7D32">绿换社区</h2>
      <p>您好，您的验证码是：</p>
      <p style="font-size:36px;letter-spacing:8px;font-weight:700;color:#2E7D32">{html.escape(code)}</p>
      <p>验证码 5 分钟内有效，请勿泄露给他人。</p>
    </div>
    """
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = recipient
    message.attach(MIMEText(body, "html", "utf-8"))
    return message


def _mock_send(recipient: str, code: str) -> None:
    line = f"[邮箱验证码] 发送至 {recipient}: {code}"
    logger.warning(line)
    print(f"\n{'=' * 48}\n{line}\n{'=' * 48}\n", flush=True)


def send_email(recipient: str, code: str) -> None:
    """发送验证码邮件。

    email_provider=mock 或 SMTP 未配置时，仅输出到控制台；
    否则通过真实 SMTP 发送，失败时抛出异常交由上层处理。
    """
    if settings.email_provider.lower() == "mock" or not settings.smtp_host or not settings.smtp_user:
        _mock_send(recipient, code)
        return

    message = _build_message(recipient, code)
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(message["From"], [recipient], message.as_string())
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(message["From"], [recipient], message.as_string())
