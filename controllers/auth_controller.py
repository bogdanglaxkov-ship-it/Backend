import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from schemas.auth_schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    PublicUser,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from services.email_service import send_password_reset_email, send_verification_email
from utils.security import (
    generate_raw_token,
    hash_password,
    hash_token,
    is_expired,
    sign_auth_token,
    token_expiry,
    verify_password,
)

logger = logging.getLogger(__name__)


def _to_public_user(user: User) -> PublicUser:
    return PublicUser(
        id=user.id, email=user.email, name=user.name, email_verified=user.email_verified
    )


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _get_user_by_verification_hash(db: AsyncSession, token_hash: str) -> User | None:
    result = await db.execute(
        select(User).where(User.verification_token_hash == token_hash)
    )
    return result.scalar_one_or_none()


async def _get_user_by_reset_hash(db: AsyncSession, token_hash: str) -> User | None:
    result = await db.execute(select(User).where(User.reset_token_hash == token_hash))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------
async def register_user(db: AsyncSession, payload: RegisterRequest) -> tuple[int, AuthResponse]:
    normalized_email = payload.email.strip().lower()

    existing = await _get_user_by_email(db, normalized_email)
    if existing:
        return 409, AuthResponse(
            success=False, message="Пользователь с таким email уже зарегистрирован"
        )

    raw_token = generate_raw_token()

    user = User(
        email=normalized_email,
        name=payload.name,
        password=hash_password(payload.password),
        email_verified=False,
        verification_token_hash=hash_token(raw_token),
        verification_token_expires_at=token_expiry(hours=24),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    try:
        send_verification_email(user.email, user.name, raw_token)
    except Exception:
        logger.exception("Ошибка отправки письма подтверждения")
        return 201, AuthResponse(
            success=True,
            message=(
                "Аккаунт создан, но не удалось отправить письмо подтверждения. "
                "Попробуйте запросить письмо повторно."
            ),
            user=_to_public_user(user),
        )

    return 201, AuthResponse(
        success=True,
        message="Аккаунт создан. Проверьте почту, чтобы подтвердить email.",
        user=_to_public_user(user),
    )


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------
async def login_user(db: AsyncSession, payload: LoginRequest) -> tuple[int, AuthResponse]:
    normalized_email = payload.email.strip().lower()
    user = await _get_user_by_email(db, normalized_email)

    invalid_credentials = (401, AuthResponse(success=False, message="Неверный email или пароль"))

    if not user:
        return invalid_credentials

    if not verify_password(payload.password, user.password):
        return invalid_credentials

    if not user.email_verified:
        return 403, AuthResponse(
            success=False, message="Подтвердите email перед входом. Проверьте почту."
        )

    token = sign_auth_token(user.id, user.email)

    return 200, AuthResponse(
        success=True,
        message="Вход выполнен успешно",
        user=_to_public_user(user),
        token=token,
    )


# ---------------------------------------------------------------------------
# POST /auth/verify-email
# ---------------------------------------------------------------------------
async def verify_email(db: AsyncSession, payload: VerifyEmailRequest) -> tuple[int, AuthResponse]:
    token_hash = hash_token(payload.token)
    user = await _get_user_by_verification_hash(db, token_hash)

    if not user:
        return 400, AuthResponse(
            success=False,
            message="Ссылка подтверждения недействительна или уже была использована",
        )

    if is_expired(user.verification_token_expires_at):
        return 400, AuthResponse(
            success=False, message="Ссылка подтверждения устарела. Запросите новое письмо."
        )

    user.email_verified = True
    user.verification_token_hash = None
    user.verification_token_expires_at = None
    await db.commit()

    return 200, AuthResponse(
        success=True, message="Email успешно подтверждён. Теперь вы можете войти."
    )


# ---------------------------------------------------------------------------
# POST /auth/forgot-password
# ---------------------------------------------------------------------------
async def forgot_password(
    db: AsyncSession, payload: ForgotPasswordRequest
) -> tuple[int, AuthResponse]:
    normalized_email = payload.email.strip().lower()
    user = await _get_user_by_email(db, normalized_email)

    # Always the same response, whether or not the account exists, so this
    # endpoint can't be used to enumerate registered emails.
    generic_response = AuthResponse(
        success=True,
        message="Если аккаунт с таким email существует, на него отправлена ссылка для сброса пароля.",
    )

    if not user:
        return 200, generic_response

    raw_token = generate_raw_token()
    user.reset_token_hash = hash_token(raw_token)
    user.reset_token_expires_at = token_expiry(hours=1)
    await db.commit()

    try:
        send_password_reset_email(user.email, user.name, raw_token)
    except Exception:
        logger.exception("Ошибка отправки письма сброса пароля")
        # Still return the generic success response to avoid leaking info.

    return 200, generic_response


# ---------------------------------------------------------------------------
# POST /auth/reset-password
# ---------------------------------------------------------------------------
async def reset_password(
    db: AsyncSession, payload: ResetPasswordRequest
) -> tuple[int, AuthResponse]:
    token_hash = hash_token(payload.token)
    user = await _get_user_by_reset_hash(db, token_hash)

    if not user:
        return 400, AuthResponse(
            success=False,
            message="Ссылка сброса пароля недействительна или уже была использована",
        )

    if is_expired(user.reset_token_expires_at):
        return 400, AuthResponse(
            success=False, message="Ссылка сброса пароля устарела. Запросите новую."
        )

    user.password = hash_password(payload.password)
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    await db.commit()

    return 200, AuthResponse(
        success=True, message="Пароль успешно изменён. Теперь вы можете войти с новым паролем."
    )
