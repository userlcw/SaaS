"""SMTP 邮件发送封装。

- 支持 SSL / STARTTLS
- 支持文本 + HTML 双部分
- 发件人使用 formataddr(name, addr)，兼容中文品牌名
- 失败抛 MailerError；调用方可映射为 HTTP 5xx / 用户可读提示
"""
from __future__ import annotations

import smtplib
import ssl
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid

from backend.app.core.logger import get_logger
from backend.config import settings

logger = get_logger(__name__)


class MailerError(RuntimeError):
    """邮件发送失败。"""


def _build_message(to_addr: str, subject: str, text_body: str, html_body: str | None) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    from_name = settings.smtp_from_name or ""
    from_addr = settings.smtp_from
    # 使用 utf-8 编码显示中文发件人名
    msg["From"] = formataddr((str(Header(from_name, "utf-8")), from_addr))
    msg["To"] = to_addr
    msg["Subject"] = Header(subject, "utf-8")
    msg["Message-ID"] = make_msgid()

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def send_email(to_addr: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    """发送一封邮件；SMTP 未配置或发送失败抛 MailerError。"""
    if not settings.smtp_enabled:
        raise MailerError("SMTP 未配置，无法发送邮件")

    to_addr = (to_addr or "").strip()
    if not to_addr or "@" not in to_addr:
        raise MailerError("收件人地址无效")

    msg = _build_message(to_addr, subject, text_body, html_body)
    host, port = settings.smtp_host, int(settings.smtp_port)
    user, pwd = settings.smtp_user, settings.smtp_password

    try:
        if settings.smtp_use_ssl:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as srv:
                srv.login(user, pwd)
                srv.sendmail(settings.smtp_from, [to_addr], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as srv:
                srv.ehlo()
                if settings.smtp_use_tls:
                    srv.starttls(context=ssl.create_default_context())
                    srv.ehlo()
                srv.login(user, pwd)
                srv.sendmail(settings.smtp_from, [to_addr], msg.as_string())
    except smtplib.SMTPAuthenticationError as e:
        logger.exception("SMTP 授权失败：%s", e)
        raise MailerError("邮件服务授权失败，请联系管理员") from e
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        logger.exception("SMTP 发送失败 to=%s err=%s", to_addr, e)
        raise MailerError("邮件发送失败，请稍后再试") from e

    logger.info("邮件发送成功 to=%s subject=%s", to_addr, subject)


def send_verification_code(to_addr: str, code: str, ttl_minutes: int) -> None:
    """发送注册验证码邮件。"""
    subject = f"【{settings.smtp_from_name}】您的注册验证码"
    text_body = (
        f"您好，\n\n"
        f"您正在注册 {settings.smtp_from_name} 账号，验证码为：{code}\n"
        f"有效期 {ttl_minutes} 分钟，请勿泄露给他人。\n\n"
        f"如果这不是您本人的操作，请忽略本邮件。"
    )
    html_body = f"""
    <div style="font-family:-apple-system,Segoe UI,PingFang SC,Microsoft YaHei,Arial,sans-serif;
                max-width:520px;margin:0 auto;padding:24px;background:#0b1220;color:#eef2f8;
                border-radius:12px;border:1px solid rgba(148,197,255,0.16);">
      <h2 style="margin:0 0 12px;font-size:18px;color:#eef2f8;">您的注册验证码</h2>
      <p style="margin:0 0 16px;color:#a3adbe;font-size:14px;line-height:1.6;">
        您好，您正在注册 <b>{settings.smtp_from_name}</b> 账号，请在页面输入以下验证码：
      </p>
      <div style="font-size:30px;letter-spacing:6px;font-weight:700;
                  padding:14px 20px;border-radius:10px;text-align:center;
                  background:linear-gradient(135deg,#5eb8f0,#3fd0d4);color:#fff;">
        {code}
      </div>
      <p style="margin:16px 0 0;color:#a3adbe;font-size:13px;line-height:1.6;">
        验证码有效期 <b>{ttl_minutes} 分钟</b>，请勿泄露给他人。<br/>
        如果这不是您本人的操作，请忽略本邮件。
      </p>
    </div>
    """
    send_email(to_addr, subject, text_body, html_body)


__all__ = ["send_email", "send_verification_code", "MailerError"]
