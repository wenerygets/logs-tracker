"""
Показать всех пользователей и их ключи
python show_users.py
"""
import asyncio
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import async_session
from models import User, Worker
from sqlalchemy import select
from sqlalchemy.orm import selectinload


async def show_users():
    print("=" * 60)
    print("ПОЛЬЗОВАТЕЛИ СИСТЕМЫ")
    print("=" * 60)
    
    async with async_session() as session:
        result = await session.execute(
            select(User).options(selectinload(User.worker))
        )
        users = result.scalars().all()
        
        if not users:
            print("\n[!] Пользователей нет! Запустите: python init_data.py")
            return
        
        print("\n[АДМИНЫ]")
        print("-" * 60)
        for u in users:
            if u.role.value == "admin":
                print(f"  Логин: {u.username}")
                print(f"  Ключ бота: {u.bot_key}")
                print()
        
        print("[ВОРКЕРЫ]")
        print("-" * 60)
        for u in users:
            if u.role.value == "worker":
                print(f"  {u.worker.name if u.worker else '???'}")
                print(f"    Логин: {u.username}")
                print(f"    Ключ бота: {u.bot_key}")
                print()


if __name__ == "__main__":
    asyncio.run(show_users())
