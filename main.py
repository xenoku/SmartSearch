"""
Главный модуль инициализации и запуска микросервиса (Application Entrypoint).

Отвечает за сборку FastAPI приложения, монтирование статических каталогов, 
маршрутизацию запросов, а также управляет жизненным циклом (Lifespan) системы: 
динамически разворачивает векторные расширения, триггеры и FTS-индексы в СУБД при старте.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from database import engine, Base
from routers import client, admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Асинхронный контекстный менеджер жизненного цикла микросервиса (Lifespan).
    
    Заменяет устаревшие события startup/shutdown. Выполняет миграции СУБД, 
    активирует расширение pgvector и компилирует PL/pgSQL функции полнотекстового поиска 
    строго до того, как веб-сервер uvicorn начнет принимать внешние HTTP-запросы.
    """
    # Гарантированное создание локальной папки изолированного хранилища файлов
    os.makedirs("storage", exist_ok=True)
    
    with engine.connect() as conn:
        # Подключение векторного расширения.
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
        
        # Генерация реляционной структуры таблиц на основе декларативных ORM моделей
        Base.metadata.create_all(bind=engine)
        
        # Компиляция иммутабельной функции для поддержки мультиязычного лексического поиска
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION immutable_tsvector(lang text, txt text)
            RETURNS tsvector AS $$
            BEGIN
                IF lang IN ('russian', 'english', 'german', 'french') THEN
                    RETURN to_tsvector(lang::regconfig, txt);
                ELSE
                    RETURN to_tsvector('simple', txt);
                END IF;
            END;
            $$ LANGUAGE plpgsql IMMUTABLE;
        """))
        
        # Автоматическое развертывание инвертированного GIN-индекса для ускорения FTS-контура
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS documents_dynamic_search_idx 
            ON documents USING gin (immutable_tsvector(language, text));
        """))
        conn.commit()
        
    yield
    # Блок для логики shutdown (закрытие пулов, деактивация сессий) при остановке контейнера
    pass

# Инициализация ядра FastAPI с подключением Lifespan-менеджера
app = FastAPI(
    title="Smart Search Distributed Microservice",
    version="1.0.0",
    lifespan=lifespan
)

# Монтирование статических директорий для отдачи медиа-файлов, стилей и скриптов интерфейса
app.mount("/files", StaticFiles(directory="storage"), name="storage")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Регистрация изолированных модулей маршрутизации API контуров
app.include_router(client.router)
app.include_router(admin.router)

@app.get("/")
async def render_user_interface():
    """Отдача статического HTML-шаблона клиентского поискового интерфейса."""
    return FileResponse("templates/index.html")

@app.get("/admin")
async def render_admin_interface():
    """Отдача статического HTML-шаблона административной панели управления."""
    return FileResponse("templates/admin.html")
