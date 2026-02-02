"""
Скрипт миграции БД - добавляет новые поля и таблицы
"""
import sqlite3

DB_PATH = "logs_leads.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("=== Миграция базы данных ===\n")
    
    # 1. Добавляем новые колонки в таблицу logs
    log_columns = [
        ("profit", "VARCHAR(50)"),
        ("is_archived", "BOOLEAN DEFAULT 0"),
        ("is_pinned", "BOOLEAN DEFAULT 0"),
        ("deadline", "VARCHAR(20)"),
    ]
    
    for col_name, col_type in log_columns:
        try:
            cursor.execute(f"ALTER TABLE logs ADD COLUMN {col_name} {col_type}")
            print(f"[+] logs.{col_name} добавлен")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"[=] logs.{col_name} уже существует")
            else:
                print(f"[-] Ошибка logs.{col_name}: {e}")
    
    # 2. Добавляем новые колонки в таблицу workers
    worker_columns = [
        ("daily_goal", "INTEGER DEFAULT 3"),
        ("weekly_goal", "INTEGER DEFAULT 15"),
        ("monthly_goal", "INTEGER DEFAULT 60"),
        ("xp", "INTEGER DEFAULT 0"),
        ("level", "INTEGER DEFAULT 1"),
        ("streak", "INTEGER DEFAULT 0"),
        ("best_streak", "INTEGER DEFAULT 0"),
        ("achievements", "TEXT"),
    ]
    
    for col_name, col_type in worker_columns:
        try:
            cursor.execute(f"ALTER TABLE workers ADD COLUMN {col_name} {col_type}")
            print(f"[+] workers.{col_name} добавлен")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"[=] workers.{col_name} уже существует")
            else:
                print(f"[-] Ошибка workers.{col_name}: {e}")
    
    # 3. Создаём таблицу sessions (для persistent login)
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token VARCHAR(100) UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                device_info VARCHAR(255),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_sessions_token ON sessions(token)")
        print("[+] Таблица sessions создана")
    except Exception as e:
        print(f"[-] Ошибка sessions: {e}")
    
    # 4. Создаём таблицу audit_logs (история изменений)
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action VARCHAR(50) NOT NULL,
                entity_type VARCHAR(50) NOT NULL,
                entity_id INTEGER,
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        print("[+] Таблица audit_logs создана")
    except Exception as e:
        print(f"[-] Ошибка audit_logs: {e}")
    
    conn.commit()
    
    # Показываем статистику
    print("\n=== Статистика ===")
    cursor.execute("SELECT COUNT(*) FROM logs")
    print(f"Логов: {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT COUNT(*) FROM workers")
    print(f"Воркеров: {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT COUNT(*) FROM users")
    print(f"Пользователей: {cursor.fetchone()[0]}")
    
    conn.close()
    print("\n[OK] Миграция завершена!")

if __name__ == "__main__":
    migrate()
