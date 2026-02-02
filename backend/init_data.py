"""
Инициализация базы данных
python init_data.py
"""
import asyncio
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_db, async_session, engine
from models import Worker, User, UserRole, Base
from sqlalchemy import select


# Воркеры и их пароли
WORKERS_DATA = [
    {"name": "Литр", "username": "litr", "password": "litr123"},
    {"name": "Валера", "username": "valera", "password": "valera123"},
    {"name": "Тупак", "username": "tupak", "password": "tupak123"},
    {"name": "Ботокс", "username": "botoks", "password": "botoks123"},
    {"name": "Родриго", "username": "rodrigo", "password": "rodrigo123"},
    {"name": "С2", "username": "s2", "password": "s2pass123"},
    {"name": "Гпоинт", "username": "gpoint", "password": "gpoint123"},
    {"name": "Масинтош", "username": "macintosh", "password": "mac123"},
]

# Админ
ADMIN = {"username": "admin", "password": "admin777"}


async def reset_db():
    print("=" * 50)
    print("ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ")
    print("=" * 50)
    
    # Пересоздаем таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    print("\n[+] Таблицы созданы")
    
    async with async_session() as session:
        # Создаем админа
        admin = User(
            username=ADMIN["username"],
            password_hash=User.hash_password(ADMIN["password"]),
            role=UserRole.ADMIN,
            bot_key=User.generate_bot_key()
        )
        session.add(admin)
        await session.flush()
        
        print(f"\n[ADMIN]")
        print(f"    Логин:  {ADMIN['username']}")
        print(f"    Пароль: {ADMIN['password']}")
        print(f"    Ключ бота: {admin.bot_key}")
        
        # Создаем воркеров и их аккаунты
        print(f"\n[ВОРКЕРЫ]")
        print("-" * 50)
        
        for data in WORKERS_DATA:
            # Создаем воркера
            worker = Worker(name=data["name"])
            session.add(worker)
            await session.flush()
            
            # Создаем пользователя для воркера
            bot_key = User.generate_bot_key()
            user = User(
                username=data["username"],
                password_hash=User.hash_password(data["password"]),
                role=UserRole.WORKER,
                worker_id=worker.id,
                bot_key=bot_key
            )
            session.add(user)
            
            print(f"    {data['name']}")
            print(f"        Логин:  {data['username']}")
            print(f"        Пароль: {data['password']}")
            print(f"        Ключ:   {bot_key}")
            print()
        
        await session.commit()
        
        print("=" * 50)
        print("[OK] ГОТОВО!")
        print("=" * 50)
        print("\nСохраните эти данные!")


if __name__ == "__main__":
    asyncio.run(reset_db())
