import os
import httpx
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()
OLLAMA_URL = os.getenv("OLLAMA_URL")
MODEL_NAME = os.getenv("MODEL_NAME")

async def get_embedding(text_data: str) -> list[float]:
    payload = {"model": MODEL_NAME, "prompt": text_data}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(OLLAMA_URL, json=payload, timeout=10.0)
            response.raise_for_status()
            return response.json()["embedding"]
    except Exception as e:
        # repr(e) выведет имя класса ошибки (например, ConnectError), даже если str(e) пустой
        debug_info = f"Исключение: {repr(e)} | URL: {OLLAMA_URL} | Модель: {MODEL_NAME}"
        raise HTTPException(
            status_code=500, 
            detail=debug_info
        )
    # except Exception as e:
    #     raise HTTPException(
    #         status_code=500, 
    #         detail=f"Ошибка генерации эмбеддинга Ollama: {str(e)}"
    #     )