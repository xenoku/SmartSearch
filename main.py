import os
import time
import random
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import engine, Base, get_db
from models import Document
from services import get_embedding
from schemas import DocumentCreate

with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    conn.commit()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Smart Search System v2.5")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/api/add")
async def add_document(payload: DocumentCreate, db: Session = Depends(get_db)):
    vector = await get_embedding(payload.text_data)
    db_doc = Document(text=payload.text_data, embedding=vector)
    db.add(db_doc)
    db.commit()
    return {"status": "success", "message": "Документ успешно добавлен"}

@app.get("/api/search")
async def search_documents(query: str, limit: int = 3, db: Session = Depends(get_db)):
    query_vector = await get_embedding(query)
    
    start_time = time.time()
    results = db.query(Document).order_by(
        Document.embedding.cosine_distance(query_vector).asc()
    ).limit(limit).all()
    execution_time = (time.time() - start_time) * 1000
    
    return {
        "execution_time_ms": round(execution_time, 2),
        "results": [{"id": doc.id, "text": doc.text} for doc in results]
    }

@app.post("/api/system/clear")
def clear_database(db: Session = Depends(get_db)):
    db.execute(text("DROP INDEX IF EXISTS documents_hnsw_idx;"))
    db.execute(text("TRUNCATE TABLE documents RESTART IDENTITY;"))
    db.commit()
    return {"status": "success", "message": "База данных очищена, индекс удален"}

@app.post("/api/system/seed")
async def seed_database(db: Session = Depends(get_db)):
    base_phrases = [
        "У меня дома живет пушистый кот, который любит ловить мышей",
        "Вчера автосервис заменил мне тормозные колодки на машине",
        "Разработка на Python и FastAPI требует понимания асинхронности"
    ]
    for phrase in base_phrases:
        vector = await get_embedding(phrase)
        db.add(Document(text=phrase, embedding=vector))
    
    for i in range(10000):
        fake_vector = [random.uniform(-1, 1) for _ in range(768)]
        db.add(Document(text=f"Системный архив данных, запись №{i}", embedding=fake_vector))
        
    db.commit()
    return {"status": "success", "message": "База успешно инициализирована тестовыми данными (10 003 записи)"}

@app.post("/api/system/index")
def manage_index(action: str, db: Session = Depends(get_db)):
    if action == "create":
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS documents_hnsw_idx ON documents 
            USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
        """))
        db.commit()
        return {"status": "success", "message": "HNSW индекс успешно создан"}
    elif action == "drop":
        db.execute(text("DROP INDEX IF EXISTS documents_hnsw_idx;"))
        db.commit()
        return {"status": "success", "message": "HNSW индекс удален"}
    else:
        raise HTTPException(status_code=400, detail="Неверное действие")

@app.get("/", response_class=FileResponse)
def get_ui():
    return FileResponse(os.path.join("templates", "index.html"))