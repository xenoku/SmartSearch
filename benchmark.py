import time
import random
from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://user:password@localhost:5432/vector_db"
engine = create_engine(DATABASE_URL)

def run_benchmark():
    print("=== ЗАПУСК ИЗОЛИРОВАННОГО ЭКСПЕРИМЕНТАЛЬНОГО ИССЛЕДОВАНИЯ ===")
    
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
        
        print("Создание временной тестовой таблицы 'benchmark_documents'...")
        conn.execute(text("DROP TABLE IF EXISTS benchmark_documents;"))
        conn.execute(text("""
            CREATE TABLE benchmark_documents (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                embedding VECTOR(768)
            );
        """))
        conn.commit()
        
        print("Заполнение тестовой таблицы векторами высокой размерности (10 000 записей)...")
        for i in range(10000):
            random_vector = [random.uniform(-1, 1) for _ in range(768)]
            vector_str = "[" + ",".join(map(str, random_vector)) + "]"
            conn.execute(
                text("INSERT INTO benchmark_documents (text, embedding) VALUES (:text, :embedding)"),
                {"text": f"Архивная тестовая запись №{i}", "embedding": vector_str}
            )
        conn.commit()
        print("Тестовое пространство успешно сформировано.")

        test_vector = "[" + ",".join(map(str, [random.uniform(-1, 1) for _ in range(768)])) + "]"
        
        print("\nТестирование поиска БЕЗ ИНДЕКСА (Последовательный перебор / Seq Scan)...")
        start_time = time.time()
        for _ in range(100):
            conn.execute(
                text("SELECT id FROM benchmark_documents ORDER BY embedding <=> :vector LIMIT 5"),
                {"vector": test_vector}
            )
        time_no_index = (time.time() - start_time) / 100
        print(f"Среднее время одного запроса без индекса: {time_no_index * 1000:.2f} мс")

        print("\nПостроение HNSW графа в СУБД (параметры: m=16, ef_construction=64)...")
        start_build = time.time()
        conn.execute(text("""
            CREATE INDEX benchmark_hnsw_idx ON benchmark_documents 
            USING hnsw (embedding vector_cosine_ops) 
            WITH (m = 16, ef_construction = 64);
        """))
        conn.commit()
        print(f"Индекс HNSW успешно построен за {time.time() - start_build:.2f} сек.")

        print("\nТестирование поиска С ИНДЕКСОМ HNSW (Приближенный поиск / ANN)...")
        start_time = time.time()
        for _ in range(100):
            conn.execute(
                text("SELECT id FROM benchmark_documents ORDER BY embedding <=> :vector LIMIT 5"),
                {"vector": test_vector}
            )
        time_with_index = (time.time() - start_time) / 100
        print(f"Среднее время одного запроса с HNSW индексом: {time_with_index * 1000:.2f} мс")
        
        speedup = time_no_index / time_with_index
        print(f"\nУскорение векторного поиска за счет HNSW: в {speedup:.1f} раз(а)!")
        
        print("\nУдаление тестовой таблицы и деструкция окружения бенчмарка...")
        conn.execute(text("DROP TABLE IF EXISTS benchmark_documents;"))
        conn.commit()
        print("База данных приведена в исходное состояние. Тест успешно завершен.")

if __name__ == "__main__":
    run_benchmark()