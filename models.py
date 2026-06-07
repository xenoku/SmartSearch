"""
Модуль ORM-моделей реляционной структуры базы данных (Database Schema).

Описывает физические таблицы СУБД PostgreSQL, типы данных колонок, 
индексы и расширения (включая специализированный тип Vector от pgvector).
"""

from sqlalchemy import Column, Integer, Text, DateTime, String, Boolean
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from database import Base

class Document(Base):
    """
    ORM-модель таблицы 'documents' для хранения полнотекстового и векторного контента.
    
    Атрибуты:
        id (int): Инкрементный первичный ключ записи.
        title (str): Кастомный или автоматически сгенерированный заголовок статьи.
        text (text): Извлеченный сырой текстовый слой документа (база для лексического поиска).
        embedding (Vector): Плотный вектор признаков размерностью 768 (база для семантического поиска).
        language (text): Языковая локаль документа для подбора конфигурации полнотекстовых словарей.
        file_name (str): Физическое имя файла, сохраненное на жестком диске / контейнере storage.
        file_url (str): Относительный сетевой путь для скачивания файла через веб-интерфейс.
        author (str): Метаданные об авторе или издателе документа.
        created_at (datetime): Кастомная дата создания/публикации документа автором.
        added_at (datetime): Системная дата и время автоматического импорта записи в СУБД.
    """
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=True, index=True)
    text = Column(Text, nullable=False)
    embedding = Column(Vector(768))
    language = Column(Text, nullable=False, default="russian")

    file_name = Column(String, nullable=True)
    file_url = Column(String, nullable=True)
    author = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, nullable=True, index=True)
    added_at = Column(DateTime, server_default=func.now(), index=True)

class AdminSession(Base):
    """
    ORM-модель таблицы 'admin_sessions' для контроля сессий авторизации администраторов.
    
    Атрибуты:
        id (int): Инкрементный первичный ключ сессии.
        token (str): Уникальный UUID-токен авторизации, сверяемый бэкендом.
        remember_me (bool): Флаг долгоживущей сессии (продление срока до 30 суток).
        expires_at (datetime): Метка времени, после которой сессия признается невалидной.
        created_at (datetime): Системное время генерации сессии сервером.
    """
    __tablename__ = "admin_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    remember_me = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
