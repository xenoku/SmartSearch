"""
Модуль вспомогательных сервисов и интеграции с ИИ (Business Logic & ETL Layer).

Отвечает за парсинг структурированных текстовых слоев из бинарных файлов (PDF, Docx, TXT),
автоматическое распознавание языковых локалей и генерацию эмбеддингов через API Ollama.
"""

import io
import os
import httpx
import json
import re
from fastapi import HTTPException
from pypdf import PdfReader
from docx import Document as DocxDocument
from langdetect import detect, LangDetectException
from config import settings

async def get_embedding(text: str) -> list[float]:
    """
    Генерация плотного векторного представления (эмбеддинга) для входного текста.
    
    Выполняет очистку текста от шумов, разбивает длинный контент на смысловые 
    чанги, вызывает API локальной нейросети Ollama и агрегирует векторы 
    методом Mean Pooling (усреднение признаков).
    
    Args:
        text (str): Сырой входной текст документа или поискового запроса.
        
    Returns:
        list[float]: Массив вещественных чисел размерностью 768 (вектор признаков).
        
    Raises:
        HTTPException: 500 при сетевых сбоях локального ИИ-сервера Ollama [1].
    """
    # Предотвращение сбоев на пустых или пробельных строках
    if not text or not text.strip():
        return [0.0] * 768
        
    # Очистка текста от артефактов веб-верстки (стили, hover, экранирование)
    cleaned_text = re.sub(r'\{.*?\}', '', text, flags=re.DOTALL)
    cleaned_text = re.sub(r'\.mw-chart[-_\w]*', '', cleaned_text)
    cleaned_text = re.sub(r'[:_\w\-\.\d]*:hover', '', cleaned_text)
    cleaned_text = cleaned_text.replace("\xad", "").replace("\xa0", " ")
    cleaned_text = cleaned_text.replace("—", " - ").replace("–", " - ")
    cleaned_text = cleaned_text.replace("<", "").replace(">", "").replace("=", "")
    cleaned_text = " ".join(cleaned_text.split())
    
    # Стратегия разбиения текста на чанки (Chunking) под контекстное окно модели
    chunk_size = 500
    chunks = [cleaned_text[i:i+chunk_size].strip() for i in range(0, len(cleaned_text), chunk_size)]
    chunks = [c for c in chunks if c][:10]  # Ограничение пула первыми 10 чанками для оптимизации скорости
    
    chunk_vectors = []
    
    embeddings_endpoint = f"{settings.ollama_url.rstrip('/')}/api/embeddings"
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for chunk in chunks:
                payload = {
                    "model": settings.model_name,
                    "prompt": chunk
                }
                binary_json = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                
                response = await client.post(
                    embeddings_endpoint, 
                    content=binary_json, 
                    headers={"Content-Type": "application/json; charset=utf-8"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    vector = data.get("embedding") or data.get("embeddings")
                    if vector and isinstance(vector, list) and len(vector) > 0:
                        chunk_vectors.append(vector)
                        
            if not chunk_vectors:
                return [0.0] * 768
                
            # Математический алгоритм Mean Pooling (усреднение матриц векторов чанков)
            num_vectors = len(chunk_vectors)
            vector_dim = len(chunk_vectors[0]) if num_vectors > 0 else 768
            
            final_vector = [0.0] * vector_dim
            for v in chunk_vectors:
                for idx in range(vector_dim):
                    final_vector[idx] += v[idx]
                    
            for idx in range(vector_dim):
                final_vector[idx] /= num_vectors
                
            return final_vector
            
    except httpx.HTTPError as he:
        raise HTTPException(status_code=500, detail=f"Сбой сети при обращении к Ollama: {str(he)}")

def extract_text_from_file(file_bytes: bytes, file_name: str) -> str:
    """
    Извлечение сырого текстового контента из бинарных массивов данных (ETL Конвейер).
    
    Поддерживает автоматическое декодирование текстовых файлов (.txt) в 
    кодировках UTF-8/CP1251, а также разбор структур документов .pdf и .docx.
    
    Args:
        file_bytes (bytes): Массив байтов загруженного файла.
        file_name (str): Имя файла с расширением для определения парсера.
        
    Returns:
        str: Извлеченный и очищенный текстовый слой документа.
        
    Raises:
        ValueError: При обнаружении пустого контента или неподдерживаемого формата.
    """
    ext = os.path.splitext(file_name)[1].lower()
    text_content = ""
    
    if ext == ".txt":
        try:
            text_content = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text_content = file_bytes.decode("cp1251")
            
    elif ext == ".pdf":
        pdf_stream = io.BytesIO(file_bytes)
        reader = PdfReader(pdf_stream)
        pages_text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages_text.append(page_text)
        text_content = "\n".join(pages_text)
        
    elif ext == ".docx":
        docx_stream = io.BytesIO(file_bytes)
        doc = DocxDocument(docx_stream)
        paragraphs = [p.text for p in doc.paragraphs if p.text]
        text_content = "\n".join(paragraphs)
        
    else:
        raise ValueError(f"Неподдерживаемый формат файла: {ext}")
        
    if not text_content.strip():
        raise ValueError("Не удалось извлечь текст из файла или файл пуст")
        
    return text_content.strip()

def detect_text_language(text: str) -> str:
    """
    Автоматическое определение языковой локали текста на основе статистического анализа.
    
    Используется для подбора релевантных словарей полнотекстового поиска (FTS) PostgreSQL.
    
    Args:
        text (str): Текстовый фрагмент для анализа.
        
    Returns:
        str: Полное имя конфигурации поиска СУБД ('russian', 'english', 'german', 'french', 'simple').
    """
    if not text or not text.strip():
        return "simple"
        
    try:
        # Анализ репрезентативной выборки первых 500 символов для ускорения работы конвейера
        sample = text[:500]
        iso_code = detect(sample)
        
        # Маппинг двухбуквенных ISO кодов на встроенные конфигурации полнотекстовых словарей СУБД
        lang_mapping = {
            "ru": "russian",
            "en": "english",
            "de": "german",
            "fr": "french"
        }
        
        return lang_mapping.get(iso_code, "simple")
        
    except LangDetectException:
        return "simple"