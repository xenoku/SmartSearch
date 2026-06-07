"""
Модуль конфигурации приложения.

Обеспечивает централизованный сбор, валидацию и типизацию переменных 
окружения из файла .env с использованием библиотеки Pydantic Settings v2.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Класс валидации и хранения глобальных настроек конфигурации системы.
    
    Атрибуты:
        database_url (str): Строка подключения к СУБД PostgreSQL (pgvector).
        ollama_url (str): Базовый сетевой адрес локального ИИ-сервера Ollama.
        model_name (str): Имя развернутой нейросетевой модели для эмбеддингов.
        admin_password (str): Пароль для доступа к панели администратора.
        secret_key (str): Ключ криптографической подписи сессий и кук.
        api_bearer_token (str): Статический мастер-токен для межсервисного API (M2M).
    """
    database_url: str
    ollama_url: str
    model_name: str
    
    admin_password: str = "admin123"
    secret_key: str = "super_secret_crypto_key_999"
    api_bearer_token: str = "smart_search_secret_token_2026"
    
    # Конфигурационный словарь Pydantic v2 для автоматического маппинга .env
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="allow",
        case_sensitive=False
    )

# Инициализация синглтона конфигурации для использования во всех слоях бэкенда
settings = Settings()
