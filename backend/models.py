from sqlalchemy import Column, Integer, String, DateTime, Text, Enum as SQLEnum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from enum import Enum
import hashlib
import secrets


class UserRole(str, Enum):
    ADMIN = "admin"
    WORKER = "worker"


class LogTag(str, Enum):
    FAT = "fat"
    POOR = "poor"
    MEDIUM = "medium"
    HAS_SALARY = "salary"


class User(Base):
    """Пользователь системы"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.WORKER)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True)  # Для воркеров
    bot_key = Column(String(50), unique=True, nullable=True)  # Ключ для бота
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    worker = relationship("Worker", back_populates="user")

    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def check_password(self, password: str) -> bool:
        return self.password_hash == self.hash_password(password)

    @staticmethod
    def generate_bot_key() -> str:
        return secrets.token_hex(8)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role.value,
            "worker_id": self.worker_id,
            "worker_name": self.worker.name if self.worker else None,
            "bot_key": self.bot_key,
            "is_active": self.is_active
        }


class Worker(Base):
    """Воркер - член команды"""
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    telegram_id = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    logs = relationship("Log", back_populates="worker", cascade="all, delete-orphan")
    user = relationship("User", back_populates="worker", uselist=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "telegram_id": self.telegram_id,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "logs_count": len(self.logs) if self.logs else 0
        }


class Log(Base):
    """Лог"""
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    worker = relationship("Worker", back_populates="logs")

    log_number = Column(String(50), nullable=False)
    pin = Column(String(100), nullable=True)  # Deprecated, kept for compatibility
    balance = Column(String(50), default="0")
    owner = Column(String(100), nullable=True)  # Принадлежащий (текстовый тег)
    comment = Column(Text, nullable=True)
    install_date = Column(String(20), nullable=False)
    check_date = Column(String(20), nullable=True)
    tag = Column(SQLEnum(LogTag), default=LogTag.MEDIUM)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def to_dict(self):
        # tag может быть enum или строкой
        tag_value = None
        if self.tag:
            tag_value = self.tag.value if hasattr(self.tag, 'value') else str(self.tag)
        
        return {
            "id": self.id,
            "worker_id": self.worker_id,
            "worker_name": self.worker.name if self.worker else None,
            "worker": {"name": self.worker.name} if self.worker else None,
            "log_number": self.log_number,
            "pin": self.pin,
            "balance": self.balance,
            "owner": self.owner,
            "comment": self.comment,
            "install_date": self.install_date,
            "check_date": self.check_date,
            "tag": tag_value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
