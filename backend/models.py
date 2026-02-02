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
    daily_goal = Column(Integer, default=3)  # Дневной план
    weekly_goal = Column(Integer, default=15)  # Недельный план
    monthly_goal = Column(Integer, default=60)  # Месячный план
    xp = Column(Integer, default=0)  # Опыт
    level = Column(Integer, default=1)  # Уровень
    streak = Column(Integer, default=0)  # Дни подряд с выполненным планом
    best_streak = Column(Integer, default=0)  # Лучший streak
    achievements = Column(Text, nullable=True)  # JSON с ачивками
    created_at = Column(DateTime, default=func.now())

    logs = relationship("Log", back_populates="worker", cascade="all, delete-orphan")
    user = relationship("User", back_populates="worker", uselist=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "telegram_id": self.telegram_id,
            "notes": self.notes,
            "daily_goal": self.daily_goal,
            "weekly_goal": self.weekly_goal,
            "monthly_goal": self.monthly_goal,
            "xp": self.xp,
            "level": self.level,
            "streak": self.streak,
            "best_streak": self.best_streak,
            "achievements": self.achievements,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "logs_count": len(self.logs) if self.logs else 0
        }


class Session(Base):
    """Сессия пользователя (для persistent login)"""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_info = Column(String(255), nullable=True)  # User-Agent
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=True)  # None = never expires

    user = relationship("User")


class CustomTag(Base):
    """Кастомные теги"""
    __tablename__ = "custom_tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    color = Column(String(20), default="#8b5cf6")  # HEX цвет
    icon = Column(String(10), default="🏷️")
    created_at = Column(DateTime, default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "icon": self.icon
        }


class LogNote(Base):
    """Заметки к логам"""
    __tablename__ = "log_notes"

    id = Column(Integer, primary_key=True, index=True)
    log_id = Column(Integer, ForeignKey("logs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())

    log = relationship("Log", back_populates="notes")
    user = relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "log_id": self.log_id,
            "user_id": self.user_id,
            "user_name": self.user.username if self.user else "Система",
            "text": self.text,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class AuditLog(Base):
    """Журнал изменений"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(50), nullable=False)  # create, update, delete
    entity_type = Column(String(50), nullable=False)  # log, worker
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)  # JSON с изменениями
    created_at = Column(DateTime, default=func.now())

    user = relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.username if self.user else None,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Log(Base):
    """Лог"""
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    worker = relationship("Worker", back_populates="logs")
    notes = relationship("LogNote", back_populates="log", cascade="all, delete-orphan")

    log_number = Column(String(50), nullable=False)
    pin = Column(String(100), nullable=True)  # Deprecated, kept for compatibility
    balance = Column(String(50), default="0")
    profit = Column(String(50), nullable=True)  # Профит/прибыль
    owner = Column(String(100), nullable=True)  # Принадлежащий (текстовый тег)
    comment = Column(Text, nullable=True)
    install_date = Column(String(20), nullable=False)
    check_date = Column(String(20), nullable=True)
    tag = Column(SQLEnum(LogTag), default=LogTag.MEDIUM)
    is_archived = Column(Boolean, default=False)  # Для архива
    is_pinned = Column(Boolean, default=False)  # Закреплённый
    deadline = Column(String(20), nullable=True)  # Дедлайн

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
            "profit": self.profit,
            "owner": self.owner,
            "comment": self.comment,
            "install_date": self.install_date,
            "check_date": self.check_date,
            "tag": tag_value,
            "is_archived": self.is_archived,
            "is_pinned": self.is_pinned,
            "deadline": self.deadline,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
