import os
from datetime import datetime
from html import escape

import resend

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
# pip install resend
# Add RESEND_API_KEY to your .env (get it from https://resend.com/api-keys)

resend.api_key = os.environ["RESEND_API_KEY"]  # fail fast if not set

EMAIL_FROM = os.environ.get("EMAIL_FROM", "Acme <onboarding@yourdomain.com>")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


# ---------------------------------------------------------------------------
# Shared layout
# ---------------------------------------------------------------------------

def _base_layout(title: str, preview: str, body_html: str) -> str:
    year = datetime.now().year
    return f"""
<!DOCTYPE html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
  </head>
  <body style="margin:0;padding:0;background-color:#f4f4f7;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
    <span style="display:none;font-size:1px;color:#f4f4f7;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">
      {preview}
    </span>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f7;padding:32px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
            <tr>
              <td style="background-color:#111827;padding:24px 32px;">
                <span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:-0.02em;">Ваш сервис</span>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                {body_html}
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 32px;">
                <p style="margin:0;color:#9ca3af;font-size:12px;line-height:18px;">
                  Если вы не запрашивали это письмо, просто игнорируйте его — никаких действий не потребуется.
                </p>
              </td>
            </tr>
          </table>
          <table role="presentation" width="480" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:16px 32px;text-align:center;">
                <span style="color:#9ca3af;font-size:12px;">© {year} Ваш сервис. Все права защищены.</span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _button_html(url: str, label: str) -> str:
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;">
      <tr>
        <td style="border-radius:8px;background-color:#111827;">
          <a href="{url}" target="_blank" style="display:inline-block;padding:12px 28px;color:#ffffff;font-size:14px;font-weight:600;text-decoration:none;border-radius:8px;">
            {label}
          </a>
        </td>
      </tr>
    </table>"""


# ---------------------------------------------------------------------------
# Verification email
# ---------------------------------------------------------------------------

def send_verification_email(to: str, name: str, raw_token: str) -> None:
    verify_url = f"{FRONTEND_URL}/verify-email?token={raw_token}"
    safe_name = escape(name)

    body_html = f"""
    <h1 style="margin:0 0 16px;color:#111827;font-size:20px;font-weight:700;">Подтвердите свой email, {safe_name}</h1>
    <p style="margin:0 0 8px;color:#4b5563;font-size:14px;line-height:22px;">
      Спасибо за регистрацию! Осталось подтвердить адрес электронной почты, чтобы активировать учётную запись.
    </p>
    {_button_html(verify_url, "Подтвердить email")}
    <p style="margin:16px 0 0;color:#9ca3af;font-size:12px;line-height:18px;">
      Ссылка действительна 24 часа. Если кнопка не работает, скопируйте адрес ниже в браузер:<br/>
      <a href="{verify_url}" style="color:#2563eb;word-break:break-all;">{verify_url}</a>
    </p>
    """

    html = _base_layout(
        title="Подтверждение email",
        preview="Подтвердите свой email, чтобы активировать учётную запись",
        body_html=body_html,
    )

    try:
        resend.Emails.send(
            {
                "from": EMAIL_FROM,
                "to": to,
                "subject": "Подтвердите ваш email",
                "html": html,
            }
        )
    except Exception as exc:  # resend raises its own exception types
        raise RuntimeError(f"Не удалось отправить письмо подтверждения: {exc}") from exc


# ---------------------------------------------------------------------------
# Password reset email
# ---------------------------------------------------------------------------

def send_password_reset_email(to: str, name: str, raw_token: str) -> None:
    reset_url = f"{FRONTEND_URL}/reset-password?token={raw_token}"
    safe_name = escape(name)

    body_html = f"""
    <h1 style="margin:0 0 16px;color:#111827;font-size:20px;font-weight:700;">Сброс пароля</h1>
    <p style="margin:0 0 8px;color:#4b5563;font-size:14px;line-height:22px;">
      Здравствуйте, {safe_name}! Мы получили запрос на сброс пароля для вашей учётной записи.
    </p>
    {_button_html(reset_url, "Придумать новый пароль")}
    <p style="margin:16px 0 0;color:#9ca3af;font-size:12px;line-height:18px;">
      Ссылка действительна 1 час. Если кнопка не работает, скопируйте адрес ниже в браузер:<br/>
      <a href="{reset_url}" style="color:#2563eb;word-break:break-all;">{reset_url}</a>
    </p>
    """

    html = _base_layout(
        title="Сброс пароля",
        preview="Запрос на сброс пароля для вашей учётной записи",
        body_html=body_html,
    )

    try:
        resend.Emails.send(
            {
                "from": EMAIL_FROM,
                "to": to,
                "subject": "Сброс пароля",
                "html": html,
            }
        )
    except Exception as exc:
        raise RuntimeError(f"Не удалось отправить письмо сброса пароля: {exc}") from exc
