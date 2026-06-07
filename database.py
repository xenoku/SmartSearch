"""
Модуль управления сессиями и подключениями к СУБД (Data Access Layer).

Инициализирует синхронный движок SQLAlchemy, связывает его с пулом 
соединений PostgreSQL и предоставляет контекстный генератор сессий для API.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from config import settings

# Инициализация ядра СУБД на основе параметров конфигурации
engine = create_engine(settings.database_url)

# Фабрика изолированных транзакционных сессий базы данных
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс декларативного маппинга для ORM-моделей системы
Base = declarative_base()

def get_db():
    """
    Контекстный генератор (Dependency Injection) для управления жизненным циклом сессий БД.
    
    Используется в эндпоинтах FastAPI через механику Depends(). Гарантирует 
    автоматическое закрытие соединения с пулом СУБД после завершения запроса.
    
    Yields:
        SessionLocal: Активная транзакционная сессия SQLAlchemy.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()