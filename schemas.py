from pydantic import BaseModel, Field

class DocumentCreate(BaseModel):
    text_data: str = Field(..., description="Текстовое содержимое документа для векторизации")