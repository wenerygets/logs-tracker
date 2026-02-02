from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class LogTag(str, Enum):
    FAT = "fat"
    POOR = "poor"
    MEDIUM = "medium"
    HAS_SALARY = "salary"


# ==================== WORKER ====================

class WorkerCreate(BaseModel):
    name: str
    telegram_id: Optional[str] = None
    notes: Optional[str] = None


class WorkerUpdate(BaseModel):
    name: Optional[str] = None
    telegram_id: Optional[str] = None
    notes: Optional[str] = None


class WorkerResponse(BaseModel):
    id: int
    name: str
    telegram_id: Optional[str]
    notes: Optional[str]
    created_at: datetime
    logs_count: Optional[int] = 0

    class Config:
        from_attributes = True


# ==================== LOG ====================

class LogCreate(BaseModel):
    worker_id: int
    log_number: str  # Номер лога
    pin: str
    balance: Optional[str] = "0"  # Текст: 400к, 1.5кк
    comment: Optional[str] = None
    install_date: str  # Текст: 3-5-7-25
    check_date: Optional[str] = None  # Текст: 3-5-7-25
    tag: Optional[LogTag] = LogTag.MEDIUM


class LogUpdate(BaseModel):
    worker_id: Optional[int] = None
    log_number: Optional[str] = None
    pin: Optional[str] = None
    balance: Optional[str] = None
    comment: Optional[str] = None
    install_date: Optional[str] = None
    check_date: Optional[str] = None
    tag: Optional[LogTag] = None


class LogResponse(BaseModel):
    id: int
    worker_id: int
    worker_name: Optional[str]
    log_number: str
    pin: str
    balance: str
    comment: Optional[str]
    install_date: str
    check_date: Optional[str]
    tag: LogTag
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
