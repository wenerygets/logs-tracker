from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.sql import func
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timedelta
import os
import secrets

from database import get_db, init_db
from models import Log, Worker, LogTag, User, UserRole, Session, AuditLog, LogNote, CustomTag, GeelarkSettings, GeelarkGroupMapping, GeelarkSyncedPhone
import json
import aiohttp
import uuid
import hashlib
import re

app = FastAPI(title="Logs Tracker", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

@app.on_event("startup")
async def startup():
    await init_db()


# ==================== XP & LEVELS ====================

def calculate_level(xp: int) -> int:
    """Рассчитать уровень по XP"""
    # 100 XP = 1 уровень, потом +50 за каждый уровень
    level = 1
    required = 100
    while xp >= required:
        level += 1
        xp -= required
        required += 50
    return level


async def add_xp(db, worker_id: int, amount: int = 10):
    """Добавить XP воркеру"""
    result = await db.execute(select(Worker).where(Worker.id == worker_id))
    worker = result.scalar_one_or_none()
    if worker:
        worker.xp = (worker.xp or 0) + amount
        worker.level = calculate_level(worker.xp)
        await db.commit()


async def log_action(db, user_id: int, action: str, entity_type: str, entity_id: int, details: dict = None):
    """Записать действие в журнал"""
    audit = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=json.dumps(details, ensure_ascii=False) if details else None
    )
    db.add(audit)
    await db.commit()


# ==================== AUTH (Persistent Sessions) ====================

def generate_token():
    return secrets.token_hex(32)


async def get_current_user(authorization: Optional[str] = Header(None), db: AsyncSession = Depends(get_db)):
    """Получить текущего пользователя по токену (из БД)"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    
    token = authorization.replace("Bearer ", "")
    
    # Ищем сессию в БД
    result = await db.execute(
        select(Session).options(selectinload(Session.user)).where(Session.token == token)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=401, detail="Недействительный токен")
    
    # Проверяем срок действия
    if session.expires_at and session.expires_at < datetime.now():
        await db.delete(session)
        await db.commit()
        raise HTTPException(status_code=401, detail="Сессия истекла")
    
    user = session.user
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    
    return user


async def get_optional_user(authorization: Optional[str] = Header(None), db: AsyncSession = Depends(get_db)):
    """Получить пользователя если есть токен"""
    if not authorization:
        return None
    try:
        return await get_current_user(authorization, db)
    except:
        return None


@app.post("/api/auth/login")
async def login(data: dict, user_agent: Optional[str] = Header(None), db: AsyncSession = Depends(get_db)):
    """Вход в систему с сохранением сессии в БД"""
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    remember = data.get("remember", True)  # Запомнить устройство
    
    result = await db.execute(select(User).options(selectinload(User.worker)).where(User.username == username))
    user = result.scalar_one_or_none()
    
    if not user or not user.check_password(password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Аккаунт отключен")
    
    token = generate_token()
    
    # Создаём сессию в БД
    expires = None if remember else datetime.now() + timedelta(hours=24)
    session = Session(
        token=token,
        user_id=user.id,
        device_info=user_agent[:255] if user_agent else None,
        expires_at=expires
    )
    db.add(session)
    await db.commit()
    
    return {
        "token": token,
        "user": user.to_dict()
    }


@app.post("/api/auth/logout")
async def logout(authorization: Optional[str] = Header(None), db: AsyncSession = Depends(get_db)):
    """Выход - удаляем сессию из БД"""
    if authorization:
        token = authorization.replace("Bearer ", "")
        result = await db.execute(select(Session).where(Session.token == token))
        session = result.scalar_one_or_none()
        if session:
            await db.delete(session)
            await db.commit()
    return {"ok": True}


@app.get("/api/auth/me")
async def get_me(user: User = Depends(get_current_user)):
    """Текущий пользователь"""
    return user.to_dict()


# ==================== STATIC ====================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open(os.path.join(FRONTEND_DIR, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/style.css")
async def serve_css():
    return FileResponse(os.path.join(FRONTEND_DIR, "style.css"), media_type="text/css")


@app.get("/script.js")
async def serve_js():
    return FileResponse(os.path.join(FRONTEND_DIR, "script.js"), media_type="application/javascript")


# ==================== WORKERS ====================

@app.get("/api/workers")
async def get_workers(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(Worker).options(selectinload(Worker.logs)).order_by(Worker.name)
    
    # Воркер видит только себя
    if user.role == UserRole.WORKER and user.worker_id:
        query = query.where(Worker.id == user.worker_id)
    
    result = await db.execute(query)
    return [w.to_dict() for w in result.scalars().all()]


@app.get("/api/workers/{worker_id}")
async def get_worker(worker_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Воркер может видеть только себя
    if user.role == UserRole.WORKER and user.worker_id != worker_id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    result = await db.execute(select(Worker).options(selectinload(Worker.logs)).where(Worker.id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail="Воркер не найден")
    return worker.to_dict()


@app.post("/api/workers")
async def create_worker(data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    worker = Worker(name=data["name"], notes=data.get("notes"))
    db.add(worker)
    await db.commit()
    await db.refresh(worker)
    return worker.to_dict()


@app.put("/api/workers/{worker_id}")
async def update_worker(worker_id: int, data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    result = await db.execute(select(Worker).where(Worker.id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail="Воркер не найден")
    
    for key in ["name", "notes", "telegram_id"]:
        if key in data:
            setattr(worker, key, data[key])
    
    await db.commit()
    return worker.to_dict()


@app.delete("/api/workers/{worker_id}")
async def delete_worker(worker_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    result = await db.execute(select(Worker).where(Worker.id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail="Воркер не найден")
    
    await db.delete(worker)
    await db.commit()
    return {"message": "Удалено"}


# ==================== LOGS ====================

@app.get("/api/logs")
async def get_logs(
    worker_id: Optional[int] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    date_filter: Optional[str] = None,  # today, week, month, all
    date_from: Optional[str] = None,  # YYYY-MM-DD
    date_to: Optional[str] = None,  # YYYY-MM-DD
    archived: bool = False,  # Показать архивные
    limit: int = Query(100, le=1000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Log).options(selectinload(Log.worker))
    
    # Фильтр по архиву
    query = query.where(Log.is_archived == archived)
    
    # Воркер видит только свои логи
    if user.role == UserRole.WORKER and user.worker_id:
        query = query.where(Log.worker_id == user.worker_id)
    elif worker_id:
        query = query.where(Log.worker_id == worker_id)
    
    if tag:
        query = query.where(Log.tag == tag)
    if search:
        query = query.where(or_(
            Log.log_number.ilike(f"%{search}%"),
            Log.owner.ilike(f"%{search}%"),
            Log.comment.ilike(f"%{search}%")
        ))
    
    # Фильтры по датам
    today = datetime.now().date()
    if date_filter == "today":
        query = query.where(func.date(Log.created_at) == today)
    elif date_filter == "week":
        week_ago = today - timedelta(days=7)
        query = query.where(func.date(Log.created_at) >= week_ago)
    elif date_filter == "month":
        month_ago = today - timedelta(days=30)
        query = query.where(func.date(Log.created_at) >= month_ago)
    
    # Кастомный диапазон дат
    if date_from:
        try:
            from_date = datetime.strptime(date_from, "%Y-%m-%d").date()
            query = query.where(func.date(Log.created_at) >= from_date)
        except:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, "%Y-%m-%d").date()
            query = query.where(func.date(Log.created_at) <= to_date)
        except:
            pass
    
    query = query.order_by(Log.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return [log.to_dict() for log in result.scalars().all()]


@app.get("/api/logs/{log_id}")
async def get_log(log_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Log).options(selectinload(Log.worker)).where(Log.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Лог не найден")
    
    # Воркер может видеть только свои логи
    if user.role == UserRole.WORKER and user.worker_id != log.worker_id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    return log.to_dict()


@app.post("/api/logs")
async def create_log(data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Воркер может создавать только свои логи
    worker_id = data.get("worker_id")
    if user.role == UserRole.WORKER:
        if user.worker_id:
            worker_id = user.worker_id
        else:
            raise HTTPException(status_code=403, detail="Воркер не привязан")
    
    log = Log(
        worker_id=worker_id,
        log_number=data["log_number"],
        balance=data.get("balance", "0"),
        profit=data.get("profit"),
        owner=data.get("owner"),
        install_date=data["install_date"],
        check_date=data.get("check_date"),
        tag=data.get("tag", "medium"),
        comment=data.get("comment")
    )
    db.add(log)
    await db.commit()
    
    # Добавляем XP воркеру
    await add_xp(db, worker_id, 10)
    
    # Записываем в журнал
    await log_action(db, user.id, "create", "log", log.id, {"log_number": data["log_number"]})
    
    result = await db.execute(select(Log).options(selectinload(Log.worker)).where(Log.id == log.id))
    return result.scalar_one().to_dict()


@app.put("/api/logs/{log_id}")
async def update_log(log_id: int, data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Log).where(Log.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Лог не найден")
    
    # Воркер может редактировать только свои логи
    if user.role == UserRole.WORKER and user.worker_id != log.worker_id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    for key in ["log_number", "balance", "profit", "owner", "install_date", "check_date", "tag", "comment"]:
        if key in data:
            setattr(log, key, data[key])
    
    await db.commit()
    
    result = await db.execute(select(Log).options(selectinload(Log.worker)).where(Log.id == log_id))
    return result.scalar_one().to_dict()


# ==================== ARCHIVE ====================

@app.post("/api/logs/{log_id}/archive")
async def archive_log(log_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Архивировать лог"""
    result = await db.execute(select(Log).where(Log.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Лог не найден")
    
    if user.role == UserRole.WORKER and user.worker_id != log.worker_id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    log.is_archived = True
    await db.commit()
    return {"ok": True, "message": "Лог архивирован"}


@app.post("/api/logs/{log_id}/unarchive")
async def unarchive_log(log_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Восстановить из архива"""
    result = await db.execute(select(Log).where(Log.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Лог не найден")
    
    if user.role == UserRole.WORKER and user.worker_id != log.worker_id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    log.is_archived = False
    await db.commit()
    return {"ok": True, "message": "Лог восстановлен"}


# ==================== BULK ACTIONS ====================

@app.post("/api/logs/bulk/delete")
async def bulk_delete_logs(data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Массовое удаление логов"""
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="Не указаны ID")
    
    for log_id in ids:
        result = await db.execute(select(Log).where(Log.id == log_id))
        log = result.scalar_one_or_none()
        if log:
            if user.role == UserRole.WORKER and user.worker_id != log.worker_id:
                continue
            await db.delete(log)
    
    await db.commit()
    return {"ok": True, "deleted": len(ids)}


@app.post("/api/logs/bulk/archive")
async def bulk_archive_logs(data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Массовая архивация логов"""
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="Не указаны ID")
    
    count = 0
    for log_id in ids:
        result = await db.execute(select(Log).where(Log.id == log_id))
        log = result.scalar_one_or_none()
        if log:
            if user.role == UserRole.WORKER and user.worker_id != log.worker_id:
                continue
            log.is_archived = True
            count += 1
    
    await db.commit()
    return {"ok": True, "archived": count}


@app.post("/api/logs/bulk/tag")
async def bulk_change_tag(data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Массовое изменение тега"""
    ids = data.get("ids", [])
    tag = data.get("tag")
    if not ids or not tag:
        raise HTTPException(status_code=400, detail="Не указаны ID или тег")
    
    count = 0
    for log_id in ids:
        result = await db.execute(select(Log).where(Log.id == log_id))
        log = result.scalar_one_or_none()
        if log:
            if user.role == UserRole.WORKER and user.worker_id != log.worker_id:
                continue
            log.tag = tag
            count += 1
    
    await db.commit()
    return {"ok": True, "updated": count}


# ==================== PIN & DUPLICATE ====================

@app.post("/api/logs/{log_id}/pin")
async def pin_log(log_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Закрепить/открепить лог"""
    result = await db.execute(select(Log).where(Log.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Лог не найден")
    
    if user.role == UserRole.WORKER and user.worker_id != log.worker_id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    log.is_pinned = not log.is_pinned
    await db.commit()
    return {"ok": True, "is_pinned": log.is_pinned}


@app.post("/api/logs/{log_id}/duplicate")
async def duplicate_log(log_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Дублировать лог"""
    result = await db.execute(select(Log).options(selectinload(Log.worker)).where(Log.id == log_id))
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Лог не найден")
    
    if user.role == UserRole.WORKER and user.worker_id != original.worker_id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    new_log = Log(
        worker_id=original.worker_id,
        log_number=f"{original.log_number}_copy",
        balance=original.balance,
        profit=original.profit,
        owner=original.owner,
        install_date=original.install_date,
        check_date=original.check_date,
        tag=original.tag,
        comment=original.comment
    )
    db.add(new_log)
    await db.commit()
    
    # XP за новый лог
    await add_xp(db, new_log.worker_id, 10)
    
    result = await db.execute(select(Log).options(selectinload(Log.worker)).where(Log.id == new_log.id))
    return result.scalar_one().to_dict()


@app.delete("/api/logs/{log_id}")
async def delete_log(log_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Log).where(Log.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Лог не найден")
    
    # Воркер может удалять только свои логи
    if user.role == UserRole.WORKER and user.worker_id != log.worker_id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    await db.delete(log)
    await db.commit()
    return {"message": "Удалено"}


# ==================== REMINDERS ====================

@app.get("/api/reminders")
async def get_reminders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(Log).options(selectinload(Log.worker)).where(
        Log.check_date.isnot(None),
        Log.check_date != ""
    )
    
    if user.role == UserRole.WORKER and user.worker_id:
        query = query.where(Log.worker_id == user.worker_id)
    
    query = query.order_by(Log.check_date.asc())
    result = await db.execute(query)
    return [log.to_dict() for log in result.scalars().all()]


@app.get("/api/reminders/today")
async def get_today_reminders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    today = datetime.now()
    today_day = today.day
    tomorrow_day = (today + timedelta(days=1)).day
    
    query = select(Log).options(selectinload(Log.worker)).where(Log.check_date.isnot(None))
    
    if user.role == UserRole.WORKER and user.worker_id:
        query = query.where(Log.worker_id == user.worker_id)
    
    result = await db.execute(query)
    logs = []
    for log in result.scalars().all():
        if log.check_date:
            # Парсим числа из check_date (формат: "8-24-25-29" = дни месяца)
            days = [int(d.strip()) for d in log.check_date.replace(".", "-").split("-") if d.strip().isdigit()]
            # Проверяем есть ли сегодня или завтра в списке
            if today_day in days or tomorrow_day in days:
                logs.append(log)
    
    return [log.to_dict() for log in logs]


# ==================== STATS ====================

@app.get("/api/stats")
async def get_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Базовые запросы
    logs_query = select(func.count(Log.id))
    
    if user.role == UserRole.WORKER and user.worker_id:
        logs_query = logs_query.where(Log.worker_id == user.worker_id)
    
    total_logs = (await db.execute(logs_query)).scalar() or 0
    total_workers = (await db.execute(select(func.count(Worker.id)))).scalar() or 0
    
    # По тегам
    by_tag = {}
    for tag in LogTag:
        q = select(func.count(Log.id)).where(Log.tag == tag)
        if user.role == UserRole.WORKER and user.worker_id:
            q = q.where(Log.worker_id == user.worker_id)
        by_tag[tag.value] = (await db.execute(q)).scalar() or 0
    
    # По воркерам с планом (только для админа)
    workers_stats = []
    if user.role == UserRole.ADMIN:
        workers_result = await db.execute(select(Worker).options(selectinload(Worker.logs)))
        workers = workers_result.scalars().all()
        
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())  # Понедельник
        month_start = today.replace(day=1)
        
        for w in workers:
            # Логи за сегодня (не архивные)
            active_logs = [log for log in w.logs if not log.is_archived]
            today_logs = sum(1 for log in active_logs if log.created_at and log.created_at.date() == today)
            # Логи за неделю
            week_logs = sum(1 for log in active_logs if log.created_at and log.created_at.date() >= week_start)
            # Логи за месяц
            month_logs = sum(1 for log in active_logs if log.created_at and log.created_at.date() >= month_start)
            
            workers_stats.append({
                "id": w.id,
                "name": w.name,
                "total": len(active_logs),
                "today": today_logs,
                "week": week_logs,
                "month": month_logs,
                "daily_goal": w.daily_goal or 3,
                "weekly_goal": w.weekly_goal or 15,
                "monthly_goal": w.monthly_goal or 60,
                "xp": w.xp or 0,
                "level": w.level or 1,
                "plan_done": min(today_logs, w.daily_goal or 3)
            })
    
    # Проверки сегодня/завтра
    today = datetime.now()
    today_day = today.day
    tomorrow_day = (today + timedelta(days=1)).day
    
    checks_query = select(Log).where(Log.check_date.isnot(None))
    if user.role == UserRole.WORKER and user.worker_id:
        checks_query = checks_query.where(Log.worker_id == user.worker_id)
    
    checks_result = await db.execute(checks_query)
    today_checks = 0
    for log in checks_result.scalars().all():
        if log.check_date:
            days = [int(d.strip()) for d in log.check_date.replace(".", "-").split("-") if d.strip().isdigit()]
            if today_day in days or tomorrow_day in days:
                today_checks += 1
    
    # Статистика по дням (последние 7 дней)
    daily_stats = []
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).date()
        day_query = select(func.count(Log.id)).where(
            func.date(Log.created_at) == day
        )
        if user.role == UserRole.WORKER and user.worker_id:
            day_query = day_query.where(Log.worker_id == user.worker_id)
        count = (await db.execute(day_query)).scalar() or 0
        daily_stats.append(count)
    
    # Подсчёт профита
    profit_query = select(Log).where(Log.profit.isnot(None))
    if user.role == UserRole.WORKER and user.worker_id:
        profit_query = profit_query.where(Log.worker_id == user.worker_id)
    
    profit_result = await db.execute(profit_query)
    total_profit = 0
    for log in profit_result.scalars().all():
        if log.profit:
            # Парсим профит (50к -> 50, 1.5кк -> 1500)
            try:
                p = log.profit.lower().replace(" ", "")
                if "кк" in p:
                    total_profit += float(p.replace("кк", "")) * 1000
                elif "к" in p:
                    total_profit += float(p.replace("к", ""))
                else:
                    total_profit += float(p)
            except:
                pass
    
    # Форматируем профит
    if total_profit >= 1000:
        total_profit_str = f"{total_profit/1000:.1f}кк"
    elif total_profit > 0:
        total_profit_str = f"{total_profit:.0f}к"
    else:
        total_profit_str = "0"
    
    # Тренды - сравнение с прошлой неделей
    today = datetime.now().date()
    this_week_start = today - timedelta(days=today.weekday())
    last_week_start = this_week_start - timedelta(days=7)
    last_week_end = this_week_start - timedelta(days=1)
    
    this_week_query = select(func.count(Log.id)).where(
        func.date(Log.created_at) >= this_week_start,
        Log.is_archived == False
    )
    last_week_query = select(func.count(Log.id)).where(
        func.date(Log.created_at) >= last_week_start,
        func.date(Log.created_at) <= last_week_end,
        Log.is_archived == False
    )
    
    if user.role == UserRole.WORKER and user.worker_id:
        this_week_query = this_week_query.where(Log.worker_id == user.worker_id)
        last_week_query = last_week_query.where(Log.worker_id == user.worker_id)
    
    this_week_count = (await db.execute(this_week_query)).scalar() or 0
    last_week_count = (await db.execute(last_week_query)).scalar() or 0
    
    if last_week_count > 0:
        trend_percent = round(((this_week_count - last_week_count) / last_week_count) * 100)
    else:
        trend_percent = 100 if this_week_count > 0 else 0
    
    return {
        "total_logs": total_logs,
        "total_workers": total_workers if user.role == UserRole.ADMIN else 1,
        "total_balance": "—",
        "total_profit": total_profit_str,
        "by_tag": by_tag,
        "workers_stats": workers_stats,
        "today_checks": today_checks,
        "daily_stats": daily_stats,
        "this_week": this_week_count,
        "last_week": last_week_count,
        "trend_percent": trend_percent
    }


# ==================== USERS (Admin only) ====================

@app.get("/api/users")
async def get_users(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    result = await db.execute(select(User).options(selectinload(User.worker)))
    return [u.to_dict() for u in result.scalars().all()]


# ==================== LOG NOTES ====================

@app.get("/api/logs/{log_id}/notes")
async def get_log_notes(log_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Получить заметки к логу"""
    result = await db.execute(
        select(LogNote)
        .options(selectinload(LogNote.user))
        .where(LogNote.log_id == log_id)
        .order_by(LogNote.created_at.desc())
    )
    return [n.to_dict() for n in result.scalars().all()]


@app.post("/api/logs/{log_id}/notes")
async def add_log_note(log_id: int, data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Добавить заметку к логу"""
    text = data.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Текст заметки обязателен")
    
    # Проверяем существование лога
    result = await db.execute(select(Log).where(Log.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Лог не найден")
    
    # Воркер может добавлять заметки только к своим логам
    if user.role == UserRole.WORKER and user.worker_id != log.worker_id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    note = LogNote(
        log_id=log_id,
        user_id=user.id,
        text=text
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    
    return {"ok": True, "note": note.to_dict()}


@app.delete("/api/notes/{note_id}")
async def delete_log_note(note_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Удалить заметку"""
    result = await db.execute(select(LogNote).where(LogNote.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    
    # Только автор или админ может удалить
    if user.role != UserRole.ADMIN and note.user_id != user.id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    await db.delete(note)
    await db.commit()
    return {"ok": True}


# ==================== CUSTOM TAGS ====================

@app.get("/api/tags")
async def get_custom_tags(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Получить все теги (стандартные + кастомные)"""
    # Стандартные теги
    standard = [
        {"id": "fat", "name": "Жир", "color": "#ef4444", "icon": "🔥", "standard": True},
        {"id": "poor", "name": "Нищий", "color": "#a855f7", "icon": "💸", "standard": True},
        {"id": "medium", "name": "Средний", "color": "#3b82f6", "icon": "📊", "standard": True},
        {"id": "salary", "name": "Есть ЗП", "color": "#22c55e", "icon": "💰", "standard": True},
    ]
    
    # Кастомные теги
    result = await db.execute(select(CustomTag).order_by(CustomTag.name))
    custom = [{"id": f"custom_{t.id}", **t.to_dict(), "standard": False} for t in result.scalars().all()]
    
    return standard + custom


@app.post("/api/tags")
async def create_custom_tag(data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Создать кастомный тег (только админ)"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название обязательно")
    
    tag = CustomTag(
        name=name,
        color=data.get("color", "#8b5cf6"),
        icon=data.get("icon", "🏷️")
    )
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    
    return {"ok": True, "tag": tag.to_dict()}


@app.delete("/api/tags/{tag_id}")
async def delete_custom_tag(tag_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Удалить кастомный тег (только админ)"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    result = await db.execute(select(CustomTag).where(CustomTag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Тег не найден")
    
    await db.delete(tag)
    await db.commit()
    return {"ok": True}


# ==================== ACHIEVEMENTS & LEADERBOARD ====================

ACHIEVEMENTS = {
    "first_log": {"name": "Первый лог", "icon": "🎯", "desc": "Добавить первый лог"},
    "logs_10": {"name": "Десятка", "icon": "🔟", "desc": "10 логов"},
    "logs_50": {"name": "Полтинник", "icon": "5️⃣0️⃣", "desc": "50 логов"},
    "logs_100": {"name": "Сотня", "icon": "💯", "desc": "100 логов"},
    "streak_3": {"name": "Три дня", "icon": "🔥", "desc": "3 дня подряд"},
    "streak_7": {"name": "Неделя", "icon": "⚡", "desc": "7 дней подряд"},
    "streak_30": {"name": "Месяц огня", "icon": "🏆", "desc": "30 дней подряд"},
    "profit_king": {"name": "Профит-кинг", "icon": "👑", "desc": "Максимальный профит"},
    "early_bird": {"name": "Ранняя пташка", "icon": "🐦", "desc": "Лог до 9 утра"},
    "night_owl": {"name": "Ночная сова", "icon": "🦉", "desc": "Лог после 23:00"},
}


@app.get("/api/achievements")
async def get_achievements(user: User = Depends(get_current_user)):
    """Список всех ачивок"""
    return ACHIEVEMENTS


@app.get("/api/leaderboard/weekly")
async def get_weekly_leaderboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Топ воркеров за неделю"""
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    
    result = await db.execute(select(Worker).options(selectinload(Worker.logs)))
    workers = result.scalars().all()
    
    leaderboard = []
    for w in workers:
        week_logs = sum(1 for log in w.logs 
                       if log.created_at and log.created_at.date() >= week_start and not log.is_archived)
        if week_logs > 0:
            leaderboard.append({
                "id": w.id,
                "name": w.name,
                "count": week_logs,
                "xp": w.xp or 0,
                "level": w.level or 1,
                "streak": w.streak or 0
            })
    
    return sorted(leaderboard, key=lambda x: (-x["count"], -x["xp"]))


@app.get("/api/leaderboard/monthly")
async def get_monthly_leaderboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Топ воркеров за месяц"""
    today = datetime.now().date()
    month_start = today.replace(day=1)
    
    result = await db.execute(select(Worker).options(selectinload(Worker.logs)))
    workers = result.scalars().all()
    
    leaderboard = []
    for w in workers:
        month_logs = sum(1 for log in w.logs 
                        if log.created_at and log.created_at.date() >= month_start and not log.is_archived)
        if month_logs > 0:
            leaderboard.append({
                "id": w.id,
                "name": w.name,
                "count": month_logs,
                "goal": w.monthly_goal or 60,
                "percent": round((month_logs / (w.monthly_goal or 60)) * 100)
            })
    
    return sorted(leaderboard, key=lambda x: -x["count"])


@app.get("/api/workers/{worker_id}/stats")
async def get_worker_stats(worker_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Детальная статистика воркера с графиком"""
    result = await db.execute(select(Worker).options(selectinload(Worker.logs)).where(Worker.id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail="Воркер не найден")
    
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    
    active_logs = [l for l in worker.logs if not l.is_archived]
    
    # Статистика по дням (последние 14 дней)
    daily_data = []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        count = sum(1 for l in active_logs if l.created_at and l.created_at.date() == day)
        daily_data.append({"date": day.strftime("%d.%m"), "count": count})
    
    # По тегам
    by_tag = {}
    for l in active_logs:
        tag = l.tag.value if hasattr(l.tag, 'value') else str(l.tag)
        by_tag[tag] = by_tag.get(tag, 0) + 1
    
    # Профит
    total_profit = 0
    for l in active_logs:
        if l.profit:
            try:
                p = l.profit.lower().replace(' ', '')
                if 'кк' in p:
                    total_profit += float(p.replace('кк', '')) * 1000
                elif 'к' in p:
                    total_profit += float(p.replace('к', ''))
            except:
                pass
    
    profit_str = f"{total_profit/1000:.1f}кк" if total_profit >= 1000 else f"{total_profit:.0f}к"
    
    return {
        "worker": worker.to_dict(),
        "total_logs": len(active_logs),
        "today_logs": sum(1 for l in active_logs if l.created_at and l.created_at.date() == today),
        "week_logs": sum(1 for l in active_logs if l.created_at and l.created_at.date() >= week_start),
        "month_logs": sum(1 for l in active_logs if l.created_at and l.created_at.date() >= month_start),
        "total_profit": profit_str,
        "by_tag": by_tag,
        "daily_data": daily_data,
        "goals": {
            "daily": worker.daily_goal or 3,
            "weekly": worker.weekly_goal or 15,
            "monthly": worker.monthly_goal or 60
        }
    }


# ==================== AUDIT LOG ====================

@app.get("/api/audit")
async def get_audit_log(
    limit: int = Query(50, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получить журнал изменений (только админ)"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    result = await db.execute(
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return [a.to_dict() for a in result.scalars().all()]


# ==================== ADMIN ACTIONS ====================

@app.post("/api/admin/reset-stats")
async def reset_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Сбросить статистику по дням (логи остаются, но счётчики обнуляются)"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    # Сдвигаем дату создания всех логов на 2 недели назад
    # Это обнулит счётчики "за день" и "за неделю"
    old_date = datetime.now() - timedelta(days=14)
    
    from sqlalchemy import update
    await db.execute(
        update(Log).values(created_at=old_date)
    )
    await db.commit()
    
    return {"message": "Статистика сброшена! Логи сохранены.", "ok": True}


@app.post("/api/admin/import-csv")
async def import_csv(data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Импорт логов из CSV (JSON формат)"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    rows = data.get("rows", [])
    if not rows:
        raise HTTPException(status_code=400, detail="Нет данных")
    
    imported = 0
    errors = []
    
    for i, row in enumerate(rows):
        try:
            # Ищем воркера по имени
            worker_name = row.get("worker", "").strip()
            worker = None
            if worker_name:
                result = await db.execute(select(Worker).where(Worker.name.ilike(f"%{worker_name}%")))
                worker = result.scalar_one_or_none()
            
            if not worker:
                # Создаём нового воркера
                worker = Worker(name=worker_name or f"Worker {i+1}")
                db.add(worker)
                await db.commit()
                await db.refresh(worker)
            
            log = Log(
                worker_id=worker.id,
                log_number=row.get("log_number", str(i+1)),
                balance=row.get("balance", "0"),
                profit=row.get("profit"),
                owner=row.get("owner"),
                install_date=row.get("install_date", "—"),
                check_date=row.get("check_date"),
                tag=row.get("tag", "medium"),
                comment=row.get("comment")
            )
            db.add(log)
            imported += 1
        except Exception as e:
            errors.append(f"Строка {i+1}: {str(e)}")
    
    await db.commit()
    
    return {
        "ok": True,
        "imported": imported,
        "errors": errors[:10]  # Первые 10 ошибок
    }


@app.get("/api/admin/export-csv")
async def export_csv(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Экспорт всех логов в JSON (для CSV)"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    result = await db.execute(select(Log).options(selectinload(Log.worker)))
    logs = result.scalars().all()
    
    return [{
        "id": l.id,
        "worker": l.worker.name if l.worker else "",
        "log_number": l.log_number,
        "balance": l.balance,
        "profit": l.profit or "",
        "owner": l.owner or "",
        "install_date": l.install_date,
        "check_date": l.check_date or "",
        "tag": l.tag.value if hasattr(l.tag, 'value') else l.tag,
        "comment": l.comment or "",
        "created_at": l.created_at.isoformat() if l.created_at else ""
    } for l in logs]


@app.delete("/api/admin/delete-all-logs")
async def delete_all_logs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Удалить все логи (только для админа)"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    # Удаляем все логи
    await db.execute(Log.__table__.delete())
    await db.commit()
    
    return {"message": "Все логи удалены", "ok": True}


# ==================== BOT API (no auth, filter by worker_id) ====================

@app.post("/api/bot/auth")
async def bot_auth(data: dict, db: AsyncSession = Depends(get_db)):
    """Авторизация в боте по ключу"""
    bot_key = data.get("key", "").strip()
    
    result = await db.execute(
        select(User).options(selectinload(User.worker)).where(User.bot_key == bot_key)
    )
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        return {"ok": False, "error": "Неверный ключ"}
    
    return {
        "ok": True,
        "user": user.to_dict()
    }


@app.get("/api/bot/logs")
async def bot_get_logs(
    worker_id: int,
    search: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Логи для бота (без авторизации, по worker_id)"""
    query = select(Log).options(selectinload(Log.worker)).where(Log.worker_id == worker_id)
    
    if search:
        query = query.where(or_(
            Log.log_number.ilike(f"%{search}%"),
            Log.owner.ilike(f"%{search}%")
        ))
    
    query = query.order_by(Log.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return [log.to_dict() for log in result.scalars().all()]


@app.post("/api/bot/logs")
async def bot_create_log(data: dict, db: AsyncSession = Depends(get_db)):
    """Создать лог через бота"""
    print(f"Bot create log data: {data}")
    
    worker_id = data.get("worker_id")
    if not worker_id:
        raise HTTPException(status_code=400, detail="worker_id обязателен")
    
    # Убираем пустые значения check_date
    check_date = data.get("check_date")
    if check_date in ["-", "", None]:
        check_date = None
    
    # Конвертируем tag в enum
    tag_str = data.get("tag", "medium").lower()
    try:
        tag = LogTag(tag_str)
    except ValueError:
        tag = LogTag.MEDIUM
    
    log = Log(
        worker_id=worker_id,
        log_number=data["log_number"],
        balance=data.get("balance", "0"),
        profit=data.get("profit"),
        owner=data.get("owner"),
        install_date=data["install_date"],
        check_date=check_date,
        tag=tag,
        comment=data.get("comment")
    )
    db.add(log)
    await db.commit()
    
    result = await db.execute(select(Log).options(selectinload(Log.worker)).where(Log.id == log.id))
    return result.scalar_one().to_dict()


@app.put("/api/bot/logs/{log_id}")
async def bot_update_log(log_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    """Обновить лог через бота"""
    result = await db.execute(select(Log).where(Log.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Лог не найден")
    
    for key in ["log_number", "balance", "owner", "install_date", "check_date", "tag", "comment"]:
        if key in data:
            setattr(log, key, data[key])
    
    await db.commit()
    return {"ok": True}


@app.delete("/api/bot/logs/{log_id}")
async def bot_delete_log(log_id: int, db: AsyncSession = Depends(get_db)):
    """Удалить лог через бота"""
    result = await db.execute(select(Log).where(Log.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Лог не найден")
    
    await db.delete(log)
    await db.commit()
    return {"ok": True}


@app.get("/api/bot/workers")
async def bot_get_workers(db: AsyncSession = Depends(get_db)):
    """Список воркеров для бота"""
    result = await db.execute(select(Worker).order_by(Worker.name))
    return [{"id": w.id, "name": w.name} for w in result.scalars().all()]


@app.get("/api/bot/reminders/today")
async def bot_today_reminders(worker_id: int, db: AsyncSession = Depends(get_db)):
    """Проверки на сегодня/завтра для бота"""
    today = datetime.now()
    today_day = today.day
    tomorrow_day = (today + timedelta(days=1)).day
    
    result = await db.execute(
        select(Log).options(selectinload(Log.worker))
        .where(Log.worker_id == worker_id, Log.check_date.isnot(None))
    )
    logs = []
    for log in result.scalars().all():
        if log.check_date:
            days = [int(d.strip()) for d in log.check_date.replace(".", "-").split("-") if d.strip().isdigit()]
            if today_day in days or tomorrow_day in days:
                logs.append(log)
    
    return [log.to_dict() for log in logs]


# ==================== GEELARK INTEGRATION ====================

GEELARK_API_URL = "https://openapi.geelark.com/open/v1"


async def geelark_request(endpoint: str, data: dict, settings: GeelarkSettings) -> dict:
    """Выполнить запрос к Geelark API"""
    url = f"{GEELARK_API_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "traceId": str(uuid.uuid4())
    }
    
    # Используем Bearer Token авторизацию
    if settings.bearer_token:
        headers["Authorization"] = f"Bearer {settings.bearer_token}"
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as resp:
            return await resp.json()


def parse_geelark_data(serial_name: str, remark: str) -> dict:
    """
    Парсит данные из Geelark (имя + комментарий)
    
    Имя (serialName): "ЖИР 02.02 86650 25% 45к" или "А 30.01 19581 25% 15к"
    Комментарий (remark): "45к в металах накопительный" или "107к ЖИР"
    
    Returns dict with: install_date, balance, tag, comment, owner, check_date
    """
    result = {
        "install_date": "—",
        "balance": "0",
        "tag": "medium",
        "comment": None,
        "owner": None,
        "check_date": None
    }
    
    combined = f"{serial_name or ''} {remark or ''}".strip()
    
    # 1. Извлекаем дату установки (DD.MM или DD,MM)
    date_match = re.search(r'(\d{1,2})[.,](\d{1,2})(?!\d)', combined)
    if date_match:
        result["install_date"] = f"{date_match.group(1)}.{date_match.group(2)}"
    
    # 2. Извлекаем @username → owner
    owner_match = re.search(r'@(\w+)', combined)
    if owner_match:
        result["owner"] = owner_match.group(1)
        combined = combined.replace(owner_match.group(0), '').strip()
    
    # 3. Извлекаем баланс (число + к/кк) — НО не если это "расходы"
    remark_str = remark or ''
    
    # Ищем баланс, но исключаем "расходы"
    # Паттерн: число + к/кк, но НЕ перед словом "расход"
    def find_balance(text):
        # Находим все числа с к/кк
        matches = re.finditer(r'(\d+(?:[.,]\d+)?)\s*(кк|к|k|kk)', text, re.IGNORECASE)
        for m in matches:
            # Проверяем что после числа НЕ идёт "расход"
            after_match = text[m.end():m.end()+15].lower()
            if not re.match(r'\s*расход', after_match):
                return m
        return None
    
    balance_match = find_balance(remark_str)
    if not balance_match:
        # Если в комментарии нет, ищем в имени
        balance_match = find_balance(serial_name or '')
    
    if balance_match:
        balance_num = balance_match.group(1)
        balance_suffix = balance_match.group(2).lower().replace('k', 'к')
        result["balance"] = f"{balance_num}{balance_suffix}"
    
    # 4. Извлекаем теги — ищем в обоих полях
    tag_patterns = {
        "fat": [r'\bжир\w*\b', r'\bфат\b', r'\bтоп\b'],
        "poor": [r'\bнищ\w*\b', r'\bбез\s*зп\b', r'\bпуст\w*\b', r'\bфулл\s*нищ', r'\d+\s*п\b'],
        "salary": [r'\bесть\s*зп\b', r'\bзп\s*есть\b', r'\bзарплат\w*\b'],
    }
    
    combined_lower = combined.lower()
    for tag, patterns in tag_patterns.items():
        for pattern in patterns:
            if re.search(pattern, combined_lower):
                result["tag"] = tag
                break
        if result["tag"] != "medium":
            break
    
    # 5. Извлекаем даты проверки (числа через дефис: 5-20-22)
    # Ищем в комментарии
    check_match = re.search(r'(\d{1,2}(?:\s*-\s*\d{1,2}){1,})', remark_str)
    if check_match:
        dates_str = check_match.group(1).replace(' ', '')
        dates = [d for d in dates_str.split('-') if d.isdigit() and 1 <= int(d) <= 31]
        if len(dates) >= 2:
            result["check_date"] = "-".join(dates)
    
    # 6. Формируем комментарий — берём из remark, убираем баланс и тег
    if remark:
        comment = remark
        # Убираем баланс
        comment = re.sub(r'\d+(?:[.,]\d+)?\s*(кк|к|k|kk)', '', comment, flags=re.IGNORECASE)
        # Убираем известные теги
        for patterns in tag_patterns.values():
            for pattern in patterns:
                comment = re.sub(pattern, '', comment, flags=re.IGNORECASE)
        # Убираем даты проверки
        comment = re.sub(r'\d{1,2}(?:\s*-\s*\d{1,2})+', '', comment)
        # Убираем @username
        comment = re.sub(r'@\w+', '', comment)
        # Чистим
        comment = re.sub(r'\s+', ' ', comment).strip(' -.,')
        if comment:
            result["comment"] = comment
    
    return result



@app.get("/api/geelark/settings")
async def get_geelark_settings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Получить настройки Geelark"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    result = await db.execute(select(GeelarkSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        return {"configured": False}
    
    return {
        "configured": True,
        **settings.to_dict()
    }


@app.post("/api/geelark/settings")
async def save_geelark_settings(data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Сохранить настройки Geelark"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    result = await db.execute(select(GeelarkSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = GeelarkSettings()
        db.add(settings)
    
    # Обновляем поля
    if "bearer_token" in data:
        settings.bearer_token = data["bearer_token"]
    if "app_id" in data:
        settings.app_id = data["app_id"]
    if "api_key" in data:
        settings.api_key = data["api_key"]
    if "auto_sync_enabled" in data:
        settings.auto_sync_enabled = data["auto_sync_enabled"]
    if "sync_interval_minutes" in data:
        settings.sync_interval_minutes = data["sync_interval_minutes"]
    if "default_worker_id" in data:
        settings.default_worker_id = data["default_worker_id"]
    
    await db.commit()
    await db.refresh(settings)
    
    return {"ok": True, "settings": settings.to_dict()}


@app.get("/api/geelark/groups")
async def get_geelark_groups(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Получить группы из Geelark и маппинги"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    # Получаем маппинги из БД
    result = await db.execute(
        select(GeelarkGroupMapping).options(selectinload(GeelarkGroupMapping.worker))
    )
    mappings = [m.to_dict() for m in result.scalars().all()]
    
    return {"mappings": mappings}


@app.post("/api/geelark/groups/mapping")
async def save_group_mapping(data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Сохранить маппинг группы Geelark → воркер"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    geelark_group_id = data.get("geelark_group_id")
    geelark_group_name = data.get("geelark_group_name")
    worker_id = data.get("worker_id")
    
    if not geelark_group_id or not worker_id:
        raise HTTPException(status_code=400, detail="Требуются geelark_group_id и worker_id")
    
    # Ищем существующий маппинг
    result = await db.execute(
        select(GeelarkGroupMapping).where(GeelarkGroupMapping.geelark_group_id == geelark_group_id)
    )
    mapping = result.scalar_one_or_none()
    
    if mapping:
        mapping.worker_id = worker_id
        mapping.geelark_group_name = geelark_group_name
    else:
        mapping = GeelarkGroupMapping(
            geelark_group_id=geelark_group_id,
            geelark_group_name=geelark_group_name,
            worker_id=worker_id
        )
        db.add(mapping)
    
    await db.commit()
    return {"ok": True}


@app.delete("/api/geelark/groups/mapping/{mapping_id}")
async def delete_group_mapping(mapping_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Удалить маппинг группы"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    result = await db.execute(select(GeelarkGroupMapping).where(GeelarkGroupMapping.id == mapping_id))
    mapping = result.scalar_one_or_none()
    if mapping:
        await db.delete(mapping)
        await db.commit()
    
    return {"ok": True}


@app.post("/api/geelark/sync")
async def sync_geelark(data: dict = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Синхронизировать телефоны из Geelark"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    # Получаем настройки
    result = await db.execute(select(GeelarkSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings or not settings.bearer_token:
        raise HTTPException(status_code=400, detail="Geelark не настроен. Укажите Bearer Token.")
    
    # Запрашиваем ВСЕ телефоны из Geelark (с пагинацией)
    phones = []
    page = 1
    page_size = 100
    
    try:
        while True:
            response = await geelark_request("/phone/list", {"page": page, "pageSize": page_size}, settings)
            
            if response.get("code") != 0:
                raise HTTPException(status_code=400, detail=f"Ошибка Geelark: {response.get('msg', 'Неизвестная ошибка')}")
            
            data = response.get("data", {})
            items = data.get("items", [])
            phones.extend(items)
            
            # Проверяем есть ли ещё страницы
            total = data.get("total", 0)
            if len(phones) >= total or not items:
                break
            
            page += 1
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка подключения к Geelark: {str(e)}")
    
    # Получаем маппинги групп
    mappings_result = await db.execute(select(GeelarkGroupMapping))
    group_mappings = {m.geelark_group_id: m.worker_id for m in mappings_result.scalars().all()}
    
    # Получаем всех воркеров для автоматического маппинга по имени
    workers_result = await db.execute(select(Worker))
    workers_list = workers_result.scalars().all()
    
    # Нормализуем имена: нижний регистр, убираем пробелы, заменяем кириллицу на латиницу
    def normalize_name(name):
        if not name:
            return ""
        name = name.lower().strip()
        # Заменяем похожие символы кириллица <-> латиница
        replacements = {
            'с': 'c', 'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 
            'х': 'x', 'у': 'y', 'к': 'k', 'н': 'h', 'в': 'b',
            'м': 'm', 'т': 't'
        }
        for cyr, lat in replacements.items():
            name = name.replace(cyr, lat)
        return name
    
    workers_by_name = {}
    for w in workers_list:
        # Добавляем оригинальное имя
        workers_by_name[w.name.lower().strip()] = w.id
        # Добавляем нормализованное имя
        workers_by_name[normalize_name(w.name)] = w.id
    
    # Получаем уже синхронизированные телефоны
    synced_result = await db.execute(select(GeelarkSyncedPhone))
    synced_phones = {s.geelark_phone_id: s for s in synced_result.scalars().all()}
    
    imported = 0
    skipped = 0
    errors = []
    new_groups = set()
    
    for phone in phones:
        phone_id = phone.get("id")
        
        # Уже синхронизирован?
        if phone_id in synced_phones:
            skipped += 1
            continue
        
        # Определяем воркера
        group = phone.get("group", {})
        group_id = group.get("id")
        group_name = group.get("name", "")
        
        worker_id = None
        
        # 1. Сначала проверяем маппинг группы по ID
        if group_id and group_id in group_mappings:
            worker_id = group_mappings[group_id]
        
        # 2. Автоматический маппинг по имени группы = имени воркера
        if not worker_id and group_name:
            # Пробуем разные варианты имени
            group_name_lower = group_name.lower().strip()
            group_name_normalized = normalize_name(group_name)
            
            if group_name_lower in workers_by_name:
                worker_id = workers_by_name[group_name_lower]
            elif group_name_normalized in workers_by_name:
                worker_id = workers_by_name[group_name_normalized]
        
        # 3. Если нет маппинга — используем воркера по умолчанию
        if not worker_id and settings.default_worker_id:
            worker_id = settings.default_worker_id
        
        # Собираем новые группы (для информации)
        if group_id and group_id not in group_mappings and not worker_id:
            new_groups.add((group_id, group_name))
        
        # Если воркер не определён — пропускаем
        if not worker_id:
            errors.append(f"Телефон {phone.get('serialNo')}: группа '{group_name}' не найдена")
            continue
        
        # Парсим данные
        serial_no = phone.get("serialNo", "")  # Номер лога
        serial_name = phone.get("serialName", "")  # Имя: "ЖИР 02.02 86650 25% 45к"
        remark = phone.get("remark", "")  # Комментарий: "45к в металах"
        
        # Парсим оба поля вместе
        parsed = parse_geelark_data(serial_name, remark)
        
        # Определяем тег
        try:
            tag = LogTag(parsed["tag"])
        except ValueError:
            tag = LogTag.MEDIUM
        
        # Создаём лог
        try:
            log = Log(
                worker_id=worker_id,
                log_number=serial_no,
                balance=parsed["balance"],
                owner=parsed["owner"],
                install_date=parsed["install_date"],
                check_date=parsed["check_date"],
                tag=tag,
                comment=parsed["comment"]
            )
            db.add(log)
            await db.flush()
            
            # Сохраняем связь
            synced = GeelarkSyncedPhone(
                geelark_phone_id=phone_id,
                serial_no=serial_no,
                log_id=log.id
            )
            db.add(synced)
            
            imported += 1
        except Exception as e:
            errors.append(f"Телефон {serial_no}: {str(e)}")
    
    # Проверяем удалённые профили — архивируем логи
    archived_count = 0
    geelark_phone_ids = {p.get("id") for p in phones if p.get("id")}
    
    # Получаем все синхронизированные телефоны
    all_synced = await db.execute(select(GeelarkSyncedPhone).options(selectinload(GeelarkSyncedPhone.log)))
    for synced in all_synced.scalars().all():
        # Если телефона больше нет в Geelark — архивируем лог
        if synced.geelark_phone_id not in geelark_phone_ids:
            if synced.log and not synced.log.is_archived:
                synced.log.is_archived = True
                archived_count += 1
            # Удаляем запись о синхронизации
            await db.delete(synced)
    
    # Обновляем время синхронизации
    settings.last_sync_at = datetime.now()
    await db.commit()
    
    return {
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "archived": archived_count,
        "total_phones": len(phones),
        "errors": errors[:10],
        "new_groups": [{"id": g[0], "name": g[1]} for g in new_groups]
    }


@app.get("/api/geelark/test")
async def test_geelark_connection(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Тест подключения к Geelark"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    result = await db.execute(select(GeelarkSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings or not settings.bearer_token:
        return {"ok": False, "error": "Bearer Token не настроен"}
    
    try:
        response = await geelark_request("/phone/list", {"page": 1, "pageSize": 1}, settings)
        
        if response.get("code") == 0:
            total = response.get("data", {}).get("total", 0)
            return {"ok": True, "message": f"Подключено! Найдено телефонов: {total}"}
        else:
            return {"ok": False, "error": response.get("msg", "Неизвестная ошибка")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/geelark/fetch-groups")
async def fetch_geelark_groups(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Получить список групп из Geelark API"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    result = await db.execute(select(GeelarkSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings or not settings.bearer_token:
        raise HTTPException(status_code=400, detail="Bearer Token не настроен")
    
    try:
        # Получаем телефоны и собираем уникальные группы
        response = await geelark_request("/phone/list", {"page": 1, "pageSize": 100}, settings)
        
        if response.get("code") != 0:
            raise HTTPException(status_code=400, detail=response.get("msg", "Ошибка"))
        
        phones = response.get("data", {}).get("items", [])
        groups = {}
        
        for phone in phones:
            group = phone.get("group", {})
            if group and group.get("id"):
                groups[group["id"]] = {
                    "id": group["id"],
                    "name": group.get("name", "Без названия"),
                    "phones_count": groups.get(group["id"], {}).get("phones_count", 0) + 1
                }
        
        return {"ok": True, "groups": list(groups.values())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
