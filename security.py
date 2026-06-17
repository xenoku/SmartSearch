"""
Модуль криптографической защиты, аутентификации и контроля доступа (Security Layer).

Реализует механизмы многофакторной проверки прав доступа (через HTTP Bearer 
токены или сессионные Cookie) для защиты административных эндпоинтов.
"""

from typing import Annotated, Optional
from datetime import datetime, timezone
from fastapi import Cookie, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import get_db
from models import AdminSession
from config import settings

# Инициализация схемы парсинга заголовка Authorization (Bearer токен)
bearer_scheme = HTTPBearer(auto_error=False)

async def verify_admin_access(
    admin_session: Annotated[Optional[str], Cookie()] = None,
    token_credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)] = None,
    db: Session = Depends(get_db)
) -> bool:
    """
    Универсальный инжектор (Dependency) для верификации сессии администратора.
    
    Последовательно проверяет наличие валидного токена в HTTP Headers 
    или в Cookie-файлах. Контролирует срок жизни сессии с учетом UTC-времени.
    
    Args:
        admin_session (Optional[str]): Токен авторизации, извлеченный из Cookie.
        token_credentials (Optional[HTTPAuthorizationCredentials]): Токен из заголовка Authorization.
        db (Session): Действующая транзакционная сессия базы данных.
        
    Returns:
        bool: True, если авторизация успешно пройдена.
        
    Raises:
        HTTPException: 401 при отсутствии токенов, 403 при невалидном или истекшем токене.
    """
    incoming_token = None
    
    # 1. Приоритет отдается Bearer токену (для API/M2M запросов)
    if token_credentials:
        incoming_token = token_credentials.credentials
    # 2. Если Bearer отсутствует, проверяется Cookie (для веб-интерфейса панели)
    elif admin_session:
        incoming_token = admin_session
        
    if not incoming_token:
        raise HTTPException(
            status_code=401, 
            detail="Требуется авторизация. Передайте Bearer-токен в Authorization или войдите через панель."
        )

    # Проверка статичного токена
    if incoming_token == settings.api_bearer_token:
        return True
        
    # Поиск записи о сессии в СУБД
    session_record = db.query(AdminSession).filter(AdminSession.token == incoming_token).first()
    
    if not session_record:
        raise HTTPException(status_code=403, detail="Невалидный или аннулированный токен доступа.")
        
    # Сравнение дат зон UTC
    current_utc_time = datetime.now(timezone.utc).replace(tzinfo=None)
    if session_record.expires_at < current_utc_time:
        db.delete(session_record)
        db.commit()
        raise HTTPException(status_code=403, detail="Срок действия токена истек. Авторизуйтесь заново.")
        
    return True