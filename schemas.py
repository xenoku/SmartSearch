"""
Модуль схем валидации и сериализации данных Pydantic (Data Transfer Objects).

Обеспечивает строгую типизацию входных и выходных параметров API-интерфейсов, 
автоматическую фильтрацию полей, генерацию OpenAPI схем и парсинг Form Data.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from fastapi import Form

class DocumentUploadMetadata(BaseModel):
    """
    Схема валидации метаданных при пакетной или одиночной загрузке файлов.
    
    Содержит специализированный фабричный метод для сборки полей из 
    многокомпонентных HTTP-форм (Multipart Form Data).
    """
    custom_title: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def as_form(
        cls,
        custom_title: Optional[str] = Form(None),
        author: Optional[str] = Form(None),
        created_at: Optional[datetime] = Form(None)
    ):
        """
        Фабричный метод (конструктор) класса для перехвата полей из Form Data.
        
        Используется в сигнатурах эндпоинтов как Depends(DocumentUploadMetadata.as_form).
        """
        return cls(custom_title=custom_title, author=author, created_at=created_at)

class DocumentUpdate(BaseModel):
    """Схема валидации тела запроса (Payload) при частичном обновлении (PUT) метаданных статьи."""
    title: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[datetime] = None
    added_at: Optional[datetime] = None

class SearchFiltersPayload(BaseModel):
    """Схема автоматической валидации параметров гибридного поиска (GET Query)."""
    query: str = Field(..., description="Строка лексико-семантического запроса")
    limit: int = Field(3, ge=1, le=50, description="Ограничение количества результатов (Top K)")
    filter_lang: Optional[str] = None
    filter_author: Optional[str] = None
    filter_file_name: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    added_after: Optional[datetime] = None
    added_before: Optional[datetime] = None

class LoginPayload(BaseModel):
    """Схема валидации данных аутентификации при входе в панель администратора."""
    password: str
    remember_me: bool = False