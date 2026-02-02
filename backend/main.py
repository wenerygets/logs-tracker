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
from models import Log, Worker, LogTag, User, UserRole

app = FastAPI(title="Logs Tracker", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

# Простые токены сессий (в памяти)
sessions = {}  # token -> user_id


@app.on_event("startup")
async def startup():
    await init_db()


# ==================== AUTH ====================

def generate_token():
    return secrets.token_hex(32)


async def get_current_user(authorization: Optional[str] = Header(None), db: AsyncSession = Depends(get_db)):
    """Получить текущего пользователя по токену"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    
    token = authorization.replace("Bearer ", "")
    user_id = sessions.get(token)
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Недействительный токен")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
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
async def login(data: dict, db: AsyncSession = Depends(get_db)):
    """Вход в систему"""
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    
    result = await db.execute(select(User).options(selectinload(User.worker)).where(User.username == username))
    user = result.scalar_one_or_none()
    
    if not user or not user.check_password(password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Аккаунт отключен")
    
    token = generate_token()
    sessions[token] = user.id
    
    return {
        "token": token,
        "user": user.to_dict()
    }


@app.post("/api/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Выход"""
    if authorization:
        token = authorization.replace("Bearer ", "")
        sessions.pop(token, None)
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
    limit: int = Query(100, le=1000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Log).options(selectinload(Log.worker))
    
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
        owner=data.get("owner"),
        install_date=data["install_date"],
        check_date=data.get("check_date"),
        tag=data.get("tag", "medium"),
        comment=data.get("comment")
    )
    db.add(log)
    await db.commit()
    
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
    
    for key in ["log_number", "balance", "owner", "install_date", "check_date", "tag", "comment"]:
        if key in data:
            setattr(log, key, data[key])
    
    await db.commit()
    
    result = await db.execute(select(Log).options(selectinload(Log.worker)).where(Log.id == log_id))
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
        
        for w in workers:
            # Логи за сегодня
            today_logs = sum(1 for log in w.logs if log.created_at and log.created_at.date() == today)
            # Логи за неделю
            week_logs = sum(1 for log in w.logs if log.created_at and log.created_at.date() >= week_start)
            
            workers_stats.append({
                "id": w.id,
                "name": w.name,
                "total": len(w.logs),
                "today": today_logs,
                "week": week_logs,
                "plan": 3,  # Дневной план
                "plan_done": min(today_logs, 3)
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
    
    return {
        "total_logs": total_logs,
        "total_workers": total_workers if user.role == UserRole.ADMIN else 1,
        "total_balance": "—",
        "by_tag": by_tag,
        "workers_stats": workers_stats,
        "today_checks": today_checks
    }


# ==================== USERS (Admin only) ====================

@app.get("/api/users")
async def get_users(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только для админа")
    
    result = await db.execute(select(User).options(selectinload(User.worker)))
    return [u.to_dict() for u in result.scalars().all()]


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
