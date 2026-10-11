"""SMTP 登录冒烟测试：仅验证 SMTP 账号/授权码是否有效，不发信。

用法：python scripts/smtp_login_check.py
"""
import smtplib
import sys

from app.core.config import settings


def main() -> int:
    if not settings.smtp_host or not settings.smtp_user:
        print("SMTP 未配置：请先在 .env 中设置 SMTP_HOST / SMTP_USER")
        return 1
    port = settings.smtp_port or 465
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(settings.smtp_host, port, timeout=15)
        else:
            server = smtplib.SMTP(settings.smtp_host, port, timeout=15)
            server.starttls()
        with server:
            server.login(settings.smtp_user, settings.smtp_password)
    except smtplib.SMTPAuthenticationError:
        print("SMTP 登录失败：账号或授权码无效/已过期，请重新生成授权码（QQ 邮箱：设置-账户-POP3/SMTP 服务）")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"SMTP 连接失败：{exc}")
        return 1
    print(f"SMTP 登录成功：{settings.smtp_user}@{settings.smtp_host}:{port}，授权码有效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
