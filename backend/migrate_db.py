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
    
    # 5. Создаём таблицу log_notes (заметки к логам)
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS log_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id INTEGER NOT NULL,
                user_id INTEGER,
                text TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (log_id) REFERENCES logs(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        print("[+] Таблица log_notes создана")
    except Exception as e:
        print(f"[-] Ошибка log_notes: {e}")
    
    # 6. Создаём таблицу custom_tags (кастомные теги)
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(50) NOT NULL,
                color VARCHAR(20) DEFAULT '#8b5cf6',
                icon VARCHAR(10) DEFAULT '🏷️',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("[+] Таблица custom_tags создана")
    except Exception as e:
        print(f"[-] Ошибка custom_tags: {e}")
    
    # 7. Создаём таблицу geelark_settings (настройки Geelark)
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS geelark_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bearer_token VARCHAR(100),
                app_id VARCHAR(100),
                api_key VARCHAR(100),
                auto_sync_enabled BOOLEAN DEFAULT 0,
                sync_interval_minutes INTEGER DEFAULT 30,
                default_worker_id INTEGER,
                last_sync_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (default_worker_id) REFERENCES workers(id)
            )
        """)
        print("[+] Таблица geelark_settings создана")
    except Exception as e:
        print(f"[-] Ошибка geelark_settings: {e}")
    
    # 8. Создаём таблицу geelark_group_mappings (маппинг групп)
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS geelark_group_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                geelark_group_id VARCHAR(100) UNIQUE NOT NULL,
                geelark_group_name VARCHAR(255),
                worker_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (worker_id) REFERENCES workers(id)
            )
        """)
        print("[+] Таблица geelark_group_mappings создана")
    except Exception as e:
        print(f"[-] Ошибка geelark_group_mappings: {e}")
    
    # 9. Создаём таблицу geelark_synced_phones (синхронизированные телефоны)
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS geelark_synced_phones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                geelark_phone_id VARCHAR(100) UNIQUE NOT NULL,
                serial_no VARCHAR(50),
                log_id INTEGER,
                synced_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (log_id) REFERENCES logs(id)
            )
        """)
        print("[+] Таблица geelark_synced_phones создана")
    except Exception as e:
        print(f"[-] Ошибка geelark_synced_phones: {e}")
    
    # 10. Добавляем geelark_phone_id в logs
    try:
        cursor.execute("ALTER TABLE logs ADD COLUMN geelark_phone_id VARCHAR(100)")
        print("[+] logs.geelark_phone_id добавлен")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("[=] logs.geelark_phone_id уже существует")
        else:
            print(f"[-] Ошибка logs.geelark_phone_id: {e}")
    
    # 11. Создаём таблицу check_results (результаты проверки Sberbank)
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS check_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id INTEGER NOT NULL,
                geelark_phone_id VARCHAR(100),
                phone_name VARCHAR(255),
                phone_serial VARCHAR(50),
                status VARCHAR(20) NOT NULL,
                error_message TEXT,
                screenshot_url TEXT,
                checked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (log_id) REFERENCES logs(id)
            )
        """)
        print("[+] Таблица check_results создана")
    except Exception as e:
        print(f"[-] Ошибка check_results: {e}")
    
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
