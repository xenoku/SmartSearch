"""
Модуль административных эндпоинтов API (Administrative Routing Layer).

Управляет процессами аутентификации, генерации криптографически защищенных 
сессий администратора, а также каскадным уничтожением сессионных кук при выходе.
"""

import os
import uuid
import shutil
import random
import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Document, AdminSession
from security import verify_admin_access
from schemas import LoginPayload, DocumentUpdate
from services import get_embedding

# Инициализация системного логгера uvicorn для фиксации внутренних сбоев СУБД
logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/admin", tags=["Admin Management"])

@router.post("/login")
async def admin_login(payload: LoginPayload, response: Response, db: Session = Depends(get_db)):
    """
    Аутентификация администратора и инициализация сессии доступа.
    
    Проверяет пароль, генерирует случайный токен доступа (UUIDv4) и записывает 
    его в СУБД. Устанавливает авторизационную куку с явным указанием корневого пути.
    """
    if payload.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Неверный пароль администратора")
        
    session_token = str(uuid.uuid4())
    days_alive = 30 if payload.remember_me else 1
    expire_time = datetime.now() + timedelta(days=days_alive)
    
    new_session = AdminSession(
        token=session_token,
        remember_me=payload.remember_me,
        expires_at=expire_time
    )
    db.add(new_session)
    db.commit()
    
    max_age_seconds = days_alive * 24 * 60 * 60
    response.set_cookie(
        key="admin_session", 
        value=session_token, 
        max_age=max_age_seconds, 
        httponly=False, 
        samesite="lax",
        path="/"
    )
    
    return {
        "status": "success", 
        "token": session_token, 
        "expires_at": expire_time.isoformat()
    }

@router.post("/logout")
async def admin_logout(
    response: Response,
    admin_session: Annotated[Optional[str], Cookie()] = None,
    db: Session = Depends(get_db)
):
    """
    Аннулирование активной сессии администратора на сервере и клиенте.
    
    Удаляет запись из таблицы admin_sessions и принудительно затирает 
    клиентскую куку admin_session, возвращая модифицированный объект ответа.
    """
    if admin_session:
        db.query(AdminSession).filter(AdminSession.token == admin_session).delete()
        db.commit()
        
    response.delete_cookie("admin_session", path="/")
    return response

@router.get("/documents", dependencies=[Depends(verify_admin_access)])
async def get_admin_documents(
    page: int = 1,
    size: int = 10,
    search_mask: Optional[str] = None,
    sort_by: str = "id",
    sort_order: str = "desc",
    db: Session = Depends(get_db)
):
    """
    Получение пагинированного, отсортированного и отфильтрованного списка документов.
    
    Поддерживает поиск по маске (ID, имя файла, кастомный заголовок или автор).
    """
    query = db.query(Document)
    
    if search_mask and search_mask.strip():
        mask_text = search_mask.strip()
        if mask_text.isdigit():
            query = query.filter(
                (Document.id == int(mask_text)) | 
                (Document.file_name.ilike(f"%{mask_text}%")) | 
                (Document.title.ilike(f"%{mask_text}%")) | 
                (Document.author.ilike(f"%{mask_text}%"))
            )
        else:
            query = query.filter(
                (Document.file_name.ilike(f"%{mask_text}%")) | 
                (Document.title.ilike(f"%{mask_text}%")) | 
                (Document.author.ilike(f"%{mask_text}%"))
            )
            
    total = query.count()
    offset = (page - 1) * size
    
    allowed_columns = {
        "id": Document.id,
        "file_name": Document.file_name,
        "title": Document.title,
        "author": Document.author,
        "created_at": Document.created_at,
        "added_at": Document.added_at
    }
    
    sort_column = allowed_columns.get(sort_by, Document.id)
    order_expression = sort_column.asc() if sort_order.lower() == "asc" else sort_column.desc()
    
    documents = query.order_by(order_expression).offset(offset).limit(size).all()
    
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {
                "id": doc.id,
                "file_name": doc.file_name,
                "title": doc.title,
                "file_url": doc.file_url,
                "author": doc.author,
                "created_at": doc.created_at.strftime("%Y-%m-%d") if doc.created_at else None,
                "added_at": doc.added_at.strftime("%Y-%m-%d") if doc.added_at else None,
                "language": doc.language
            } for doc in documents
        ]
    }

@router.delete("/documents/{doc_id}", dependencies=[Depends(verify_admin_access)])
async def delete_admin_document(doc_id: int, db: Session = Depends(get_db)):
    """
    Каскадное удаление документа из СУБД и связанного физического файла с диска.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")
        
    if doc.file_url:
        filename = doc.file_url.split("/")[-1]
        file_path = os.path.join("storage", filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Не удалось удалить физический файл {file_path}: {e}")
                
    db.delete(doc)
    db.commit()
    return {"status": "success", "message": "Документ и связанный файл успешно удалены"}

@router.put("/documents/{doc_id}", dependencies=[Depends(verify_admin_access)])
async def update_admin_document(
    doc_id: int, 
    payload: DocumentUpdate,
    db: Session = Depends(get_db)
):
    """
    Частичное изменение метаданных существующего документа в базе данных.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc: 
        raise HTTPException(status_code=404, detail="Документ не найден")
    
    if payload.title is not None: 
        doc.title = payload.title
        
    if payload.author is not None: 
        doc.author = payload.author if payload.author.strip() else None
        
    if payload.created_at is not None: 
        doc.created_at = payload.created_at
        
    if payload.added_at is not None: 
        doc.added_at = payload.added_at
        
    db.commit()
    return {"status": "success", "message": "Метаданные документа успешно обновлены в СУБД"}

@router.delete("/clear", dependencies=[Depends(verify_admin_access)])
async def clear_database_and_storage(db: Session = Depends(get_db)):
    """
    Каскадная очистка СУБД и полное уничтожение физических файлов в каталоге storage.
    """
    try:
        db.execute(text("TRUNCATE TABLE documents RESTART IDENTITY CASCADE;"))
        db.commit()
        
        storage_dir = "storage"
        if os.path.exists(storage_dir):
            for filename in os.listdir(storage_dir):
                file_path = os.path.join(storage_dir, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    logger.error(f"Не удалось удалить элемент {file_path} при очистке: {e}")
                    
        return {"status": "success", "message": "База данных и физическое хранилище файлов полностью очищены."}
    except Exception as e:
        logger.error(f"Ошибка при полной очистке: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка сервера при очистке: {str(e)}")

@router.post("/seed", dependencies=[Depends(verify_admin_access)])
async def seed_database(db: Session = Depends(get_db)):
    """
    Наполнение репозитория стресс-тест датасетом (10 005 записей) для замера скорости HNSW.
    
    Реализует пакетное сохранение транзакций (батчинг) для защиты оперативной 
    памяти контейнера от переполнения и исключает избыточный ввод-вывод на диск.
    """
    try:
        db.execute(text("TRUNCATE TABLE documents RESTART IDENTITY CASCADE;"))
        db.commit()
        
        if os.path.exists("storage"):
            for f in os.listdir("storage"):
                try:
                    os.remove(os.path.join("storage", f))
                except Exception:
                    pass
        else:
            os.makedirs("storage", exist_ok=True)

        fake_authors = ["Иванов И.И.", "Петров В.С.", "John Doe", "Alice Smith", "Сидоров А.М."]
        
        base_phrases = [
            {"title": "Инструкция по уходу за питомцами", "file": "pets_care.txt", "text": "У меня дома живет пушистый кот, который любит ловить мышей", "lang": "russian", "author": "Иванов И.И."},
            {"title": "Акт выполненных работ автосервиса", "file": "car_service_act.docx", "text": "Вчера автосервис заменил мне тормозные колодки на машине", "lang": "russian", "author": "Петров В.С."},
            {"title": "Учебное пособие по FastAPI", "file": "fastapi_async.txt", "text": "Разработка на Python и FastAPI требует понимания асинхронности", "lang": "russian", "author": "Сидоров А.М."},
            {"title": "Nature and wildlife report", "file": "wildlife_report.docx", "text": "The quick brown fox jumps over the lazy dog for no reason", "lang": "english", "author": "John Doe"},
            {"title": "DevOps infrastructure guidelines", "file": "devops_guide.txt", "text": "Python applications can be easily containerized using Docker compose manifests", "lang": "english", "author": "Alice Smith"}
        ]
        
        one_year_ago = datetime.now() - timedelta(days=365)

        for item in base_phrases:
            vector = await get_embedding(item['text'])
            db.add(Document(
                title=item['title'],
                text=item['text'],
                embedding=vector,
                language=item['lang'],
                file_name=item['file'],
                file_url=f"/files/{item['file']}",
                author=item['author'],
                created_at=one_year_ago
            ))

        now = datetime.now()
        
        for i in range(10000):
            fake_vector = [random.uniform(-1, 1) for _ in range(768)]
            lang = "english" if i % 2 == 0 else "russian"
            author = random.choice(fake_authors)
            
            random_days_ago = random.randint(0, 1800)
            random_created_date = now - timedelta(days=random_days_ago)
            
            clean_title = f"Архивный системный отчет №{i}"
            fake_filename = f"financial_report_archive_v{i}.txt"
            
            db.add(Document(
                title=clean_title,
                text=f"Системный архив данных / System data archive №{i}",
                embedding=fake_vector,
                language=lang,
                file_name=fake_filename,
                file_url=f"/files/{fake_filename}",
                author=author,
                created_at=random_created_date
            ))
            
            if i % 1000 == 0:
                db.commit()
                db.expunge_all()
            
        db.commit()
        return {
            "status": "success", 
            "message": "База данных пересоздана. Репозиторий наполнен структурированными объектами (10,005 записей)."
        }
    except Exception as e:
        logger.error(f"Ошибка сидирования: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка генератора данных: {str(e)}")

@router.post("/index/hnsw", dependencies=[Depends(verify_admin_access)])
async def create_hnsw_index(db: Session = Depends(get_db)):
    """
    Динамическое развертывание и активация векторного HNSW-индекса в СУБД.
    """
    try:
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS documents_vector_hnsw_idx 
            ON documents USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        """))
        db.commit()
        return {"status": "success", "message": "Векторный HNSW-индекс успешно построен и активирован."}
    except Exception as e:
        logger.error(f"Ошибка создания индекса: {str(e)}", exist_ok=True)
        raise HTTPException(status_code=500, detail=f"Ошибка СУБД: {str(e)}")

@router.delete("/index/hnsw", dependencies=[Depends(verify_admin_access)])
async def drop_hnsw_index(db: Session = Depends(get_db)):
    """
    Деактивация и каскадное удаление HNSW-графа из оперативной памяти PostgreSQL.
    """
    try:
        db.execute(text("DROP INDEX IF EXISTS documents_vector_hnsw_idx;"))
        db.commit()
        return {"status": "success", "message": "Векторный HNSW-индекс успешно удален."}
    except Exception as e:
        logger.error(f"Ошибка удаления индекса: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка СУБД: {str(e)}")