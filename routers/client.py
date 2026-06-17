"""
Модуль клиентских эндпоинтов API (Client Interface Routing).

Реализует высокопроизводительный движок гибридного поиска документов. 
Объединяет результаты векторного (семантического) и полнотекстового (лексического) 
контуров СУБД PostgreSQL с использованием алгоритма слияния рангов RRF (Reciprocal Rank Fusion).
"""

import os
import time
import random
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models import Document
from schemas import SearchFiltersPayload, DocumentUploadMetadata
from security import verify_admin_access
from services import extract_text_from_file, get_embedding, detect_text_language


# Инициализация логгера uvicorn для фиксации поисковых метрик и ошибок SQL
logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api", tags=["Client Interface"])

# Словарь маппинга локалей для защиты строгой типизации regconfig в PostgreSQL
LANG_CONFIG_MAPPING = {
    "ru": "russian",
    "en": "english",
    "ru-ru": "russian",
    "en-us": "english",
    "russian": "russian",
    "english": "english",
    "german": "german",
    "french": "french"
}

@router.get("/search")
async def search_documents(
    filters: SearchFiltersPayload = Depends(),
    db: Session = Depends(get_db)
):
    """
    Выполнение интеллектуального гибридного поиска документов с мета-фильтрацией.
    
    Анализирует текст запроса, извлекает семантический вектор, формирует 
    параллельные SQL-запросы к инвертированному (GIN) и граф-ориентированному (HNSW) 
    индексам, после чего ранжирует кандидатов по формуле RRF.
    """

    try:
        query_str = filters.query
        limit_val = filters.limit

        # Динамическое определение языкового контекста поискового запроса
        detected_query_lang = detect_text_language(query_str)
        
        # Получение плотного вектора признаков из локального ИИ-сервера Ollama
        query_vector = await get_embedding(query_str)
        
        start_time = time.time()
        
        db_regconfig = LANG_CONFIG_MAPPING.get(detected_query_lang.lower(), "simple")
        
        sql_params = {
            "vector": str(query_vector),
            "query": query_str,
            "lang": db_regconfig
        }
        
        # Динамическая сборка условий фильтрации (Meta-Attributes Filtering)
        meta_clauses = []
        is_hard_filter_active = False
        
        if filters.filter_lang and filters.filter_lang.strip():
            # Приведение языкового фильтра пользователя к стандарту словарей БД
            clean_lang = LANG_CONFIG_MAPPING.get(filters.filter_lang.strip().lower(), "simple")
            meta_clauses.append("language = :filter_lang")
            sql_params["filter_lang"] = clean_lang
            
        if filters.filter_author and filters.filter_author.strip():
            meta_clauses.append("author ILIKE :filter_author")
            sql_params["filter_author"] = f"%{filters.filter_author.strip()}%"
            is_hard_filter_active = True
            
        if filters.filter_file_name and filters.filter_file_name.strip():
            meta_clauses.append("file_name ILIKE :filter_file_name")
            sql_params["filter_file_name"] = f"%{filters.filter_file_name.strip()}%"
            is_hard_filter_active = True
            
        if filters.created_after:
            meta_clauses.append("created_at >= :created_after")
            sql_params["created_after"] = filters.created_after
            is_hard_filter_active = True
        if filters.created_before:
            meta_clauses.append("created_at <= :created_before")
            sql_params["created_before"] = filters.created_before
            is_hard_filter_active = True
            
        if filters.added_after:
            meta_clauses.append("added_at >= :added_after")
            sql_params["added_after"] = filters.added_after
            is_hard_filter_active = True
        if filters.added_before:
            meta_clauses.append("added_at <= :added_before")
            sql_params["added_before"] = filters.added_before
            is_hard_filter_active = True

        where_meta = "WHERE " + " AND ".join(meta_clauses) if meta_clauses else ""
        
        # Сборка условий полнотекстового поиска с использованием кастомной функции immutable_tsvector
        fts_clause = "immutable_tsvector(language, text) @@ plainto_tsquery(CAST(:lang AS regconfig), :query)"
        if meta_clauses:
            where_keyword = "WHERE " + fts_clause + " AND " + " AND ".join(meta_clauses)
        else:
            where_keyword = "WHERE " + fts_clause

        # --- АРХИТЕКТУРНЫЙ ШЛЮЗ ПЕРЕКЛЮЧЕНИЯ КОНТУРОВ ПЛАНИРОВЩКА ---
        if is_hard_filter_active:
            db.execute(text("SET LOCAL enable_seqscan = on;"))
        else:
            db.execute(text("SET LOCAL enable_seqscan = off;"))

        # КОНТУР 1: Семантический поиск (Cosine Distance по HNSW-графу)
        sem_query = text(f"SELECT id FROM documents {where_meta} ORDER BY embedding <=> :vector ASC LIMIT 50;")
        sem_ids = [r.id for r in db.execute(sem_query, sql_params).fetchall()]

        # КОНТУР 2: Лексический поиск (Ранжирование ts_rank_cd по GIN-индексу)
        key_query = text(f"SELECT id FROM documents {where_keyword} ORDER BY ts_rank_cd(immutable_tsvector(language, text), plainto_tsquery(CAST(:lang AS regconfig), :query)) DESC LIMIT 50;")
        key_ids = [r.id for r in db.execute(key_query, sql_params).fetchall()]

        # Слияние уникальных идентификаторов кандидатов из обоих источников
        candidate_ids = list(set(sem_ids + key_ids))
        if not candidate_ids:
            return {"execution_time_ms": round((time.time() - start_time) * 1000, 2), "results": []}

        # КОНТУР 3: Пакетное извлечение метаданных для финального пула кандидатов
        meta_query = text("SELECT id, title, text, language, file_name, file_url, author, created_at, added_at FROM documents WHERE id IN :ids;")
        raw_rows = db.execute(meta_query, {"ids": tuple(candidate_ids)}).fetchall()

        # Построение хэш-карт позиций (рангов) документов для расчета RRF скоров
        semantic_ranks = dict((doc_id, idx + 1) for idx, doc_id in enumerate(sem_ids))
        keyword_ranks = dict((doc_id, idx + 1) for idx, doc_id in enumerate(key_ids))

        processed_results = []
        for row in raw_rows:
            s_rank = semantic_ranks.get(row.id, None)
            k_rank = keyword_ranks.get(row.id, None)
            
            # Математическая формула RRF (Reciprocal Rank Fusion) со сглаживающим коэффициентом k=60
            score_s = 1.0 / (60.0 + s_rank) if s_rank else 0.0
            score_k = 1.0 / (60.0 + k_rank) if k_rank else 0.0
            rrf_score = score_s + score_k
            
            processed_results.append({
                "id": row.id, 
                "title": row.title,
                "text": row.text, 
                "language": row.language,
                "file_name": row.file_name, 
                "file_url": row.file_url, 
                "author": row.author,
                "created_at": row.created_at.strftime("%Y-%m-%d") if row.created_at else None,
                "added_at": row.added_at.strftime("%Y-%m-%d") if row.added_at else None,
                "semantic_rank": s_rank, 
                "keyword_rank": k_rank,
                "rrf_score": round(rrf_score, 4)
            })

        # Финальная сортировка массива по убыванию интегрального показателя релевантности RRF
        processed_results.sort(key=lambda x: x["rrf_score"], reverse=True)
        final_slice = processed_results[:limit_val]
        
        execution_time_ms = round((time.time() - start_time) * 1000, 2)
        return {"execution_time_ms": execution_time_ms, "results": final_slice}
        
    except Exception as e:
        logger.error(f"Критический сбой поискового ядра RRF: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка поискового движка: {str(e)}")

@router.post("/upload/bulk", dependencies=[Depends(verify_admin_access)])
async def upload_documents_bulk(
    files: List[UploadFile] = File(...), 
    metadata: DocumentUploadMetadata = Depends(DocumentUploadMetadata.as_form),
    db: Session = Depends(get_db)
):
    """
    Пакетный импорт, извлечение контента и автоматическая векторизация пула файлов.
    
    Последовательно считывает бинарные массивы (.txt, .pdf, .docx), парсит 
    текстовый слой, определяет язык локали, генерирует эмбеддинги через Ollama 
    и атомарно сохраняет структурированную запись и физический файл.
    """

    try:
        success_count = 0
        failed_count = 0
        
        created_dt = metadata.created_at if metadata.created_at else None
        allowed_extensions = {".pdf", ".docx", ".txt"}
        
        for file in files:
            pure_filename = os.path.basename(file.filename)
            ext = os.path.splitext(pure_filename)[-1].lower()
            
            # Валидация расширения файла (игнорирование системного мусора папок)
            if ext not in allowed_extensions:
                failed_count += 1
                continue 
                
            try:
                # Чтение бинарного потока данных из HTTP-запроса
                fb = await file.read()
                
                # Парсинг сырого текстового слоя специализированным сервисом
                text_layer = extract_text_from_file(fb, pure_filename)
                cleaned_text = " ".join(text_layer.split())
                
                # Генерация плотного эмбеддинга признаков через локальную нейросеть
                v = await get_embedding(cleaned_text)
                
                # Формирование уникального безопасного имени файла для изоляции в хранилище storage
                safe_filename = f"{int(time.time())}_{random.randint(100,999)}_{pure_filename}"
                storage_path = os.path.join("storage", safe_filename)
                
                with open(storage_path, "wb") as f: 
                    f.write(fb)
                
                # Определение логики заголовка (Title)
                if metadata.custom_title and metadata.custom_title.strip():
                    # Если файлов много, добавляем маркер имени для уникализации в каталоге
                    document_title = f"{metadata.custom_title.strip()} ({pure_filename})" if len(files) > 1 else metadata.custom_title.strip()
                else:
                    document_title = pure_filename
                    
                # Запись структурированного объекта в реляционную таблицу СУБД
                db.add(Document(
                    title=document_title,
                    text=text_layer, 
                    embedding=v, 
                    language=detect_text_language(text_layer), 
                    file_name=pure_filename,
                    file_url=f"/files/{safe_filename}", 
                    author=metadata.author if metadata.author else None,
                    created_at=created_dt
                ))
                success_count += 1
                
            except Exception as file_error:
                logger.warning(f"Пакетный конвейер пропустил файл '{pure_filename}' из-за ошибки: {str(file_error)}")
                failed_count += 1
                continue
                
        # Атомарный сброс всех успешно обработанных документов пакета в СУБД
        db.commit()
        
        msg = f"Пакетный импорт успешно завершен. Загружено документов: {success_count}."
        if failed_count > 0:
            msg += f" Пропущено невалидных объектов: {failed_count}."
            
        return {"status": "success", "message": msg}
        
    except Exception as e:
        # Каскадный откат незавершенной транзакции при общем сбое
        db.rollback()
        logger.error(f"Критическая авария пакетного ETL конвейера: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Внутренний сбой сервера: {str(e)}")