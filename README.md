# 📊 Logs TRF.404 — Система учёта логов

Система для ведения учёта логов с разделением по воркерам. Telegram бот для быстрого добавления + веб-интерфейс для просмотра и аналитики + интеграция с Geelark.

---

## 🏗️ Архитектура системы

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│   Backend API   │◀────│  Telegram Bot   │
│   (HTML/JS)     │     │   (FastAPI)     │     │   (aiogram)     │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                        ┌────────▼────────┐
                        │   SQLite DB     │
                        │  logs_leads.db  │
                        └─────────────────┘
                                 │
                        ┌────────▼────────┐
                        │  Geelark API    │
                        │  (внешний)      │
                        └─────────────────┘
```

---

## 👥 Роли пользователей

| Роль | Доступ |
|------|--------|
| **Admin** | Все функции: логи, воркеры, статистика, настройки, Geelark |
| **Worker** | Только свои логи, своя статистика |

---

## 🔐 Авторизация

### Веб-интерфейс
1. Открыть сайт `https://trf404.digital/`
2. Ввести **логин** и **пароль**
3. Токен сохраняется в `localStorage` — вход сохраняется

### Telegram бот
1. Запустить бота `/start`
2. Ввести **ключ доступа** (bot_key из профиля)
3. Появится меню с кнопками

---

## 📊 Структура данных

### Лог (Log)

| Поле | Описание | Пример |
|------|----------|--------|
| `log_number` | Номер лога | `86650` |
| `balance` | Баланс | `45к`, `1.5кк` |
| `profit` | Профит | `50к` |
| `owner` | Владелец | `@username` |
| `install_date` | Дата установки | `02.02` |
| `check_date` | Даты проверок | `5-20-22-26` |
| `tag` | Тег | `fat`, `poor`, `medium`, `salary` |
| `comment` | Комментарий | Любой текст |
| `is_pinned` | Закреплён | ✅/❌ |
| `is_archived` | В архиве | ✅/❌ |

### Теги

| Тег | Название | Условие (авто) |
|-----|----------|----------------|
| 🔥 `fat` | Жир | Баланс ≥ 100к |
| 📊 `medium` | Средний | Баланс 30-100к |
| 💰 `salary` | Есть ЗП | Баланс 10-30к |
| 💸 `poor` | Нищий | Баланс < 10к |

---

## 🌐 Веб-интерфейс

### Страницы
1. **Дэшборд** — общая статистика, графики, ближайшие проверки
2. **Логи** — таблица всех логов с фильтрами
3. **Воркеры** — карточки воркеров со статистикой
4. **Напоминания** — логи с датами проверок
5. **⚙️ Настройки** — Geelark интеграция

### Действия с логами
- ➕ **Добавить** — форма создания
- ✏️ **Редактировать** — клик по строке → модалка
- 📌 **Закрепить** — лог будет вверху таблицы
- 📋 **Дублировать** — создать копию
- 📥 **Архивировать** — скрыть (не удалять)
- 🗑️ **Удалить** — безвозвратно

### Массовые действия
1. Выбрать логи чекбоксами
2. Появятся кнопки: **Удалить выбранные**, **Архивировать**, **Изменить тег**

---

## 🤖 Telegram бот

### Команды

| Команда | Описание |
|---------|----------|
| `/start` | Начало / авторизация |
| `/backup` | Скачать бэкап БД (только админ) |

### Меню (админ)
- ➕ Добавить лог
- 📋 Все логи
- 📊 Статистика
- 🏆 Топ недели
- 🔔 Проверки
- 🔍 Поиск
- 🎯 Прогресс
- 🌐 Открыть сайт

### Меню (воркер)
- 📋 Мои логи
- 📊 Статистика
- 🏆 Топ недели
- 🔔 Проверки
- 🎯 Мой прогресс
- 🌐 Открыть сайт

### Автоматические уведомления

| Время | Что |
|-------|-----|
| 09:00 | Утренние проверки |
| 13:00 | Напоминание о проверках |
| 17:00 | Напоминание о проверках |
| 21:00 | Итоги дня |
| 03:00 | Автобэкап БД админу |

---

## 📱 Geelark интеграция

### Настройка
1. Зайти в **⚙️ Настройки** → **Geelark**
2. Вставить **Bearer Token** из Geelark
3. Нажать **Тест подключения**
4. Настроить маппинг групп → воркеры

### Парсинг данных

Из полей Geelark:
- `serialNo` → Номер лога
- `serialName` → Дата установки, баланс, тег
- `remark` → Баланс, даты проверок, комментарий, @владелец

Примеры:
```
serialName: "ЖИР 02.02 86650 25% 45к"
remark: "45к в металах накопительный 5-20-22-26"

Результат:
- install_date: 02.02
- balance: 45к
- tag: fat (из слова "ЖИР")
- check_date: 5-20-22-26
- comment: в металах накопительный
```

### Синхронизация
- **Ручная** — кнопка "Синхронизировать"
- **Авто** — каждые 30 минут (если включено)
- Удалённые в Geelark профили → архивируются на сайте

---

## 🗄️ API Endpoints

### Авторизация
```
POST /api/auth/login     — вход
POST /api/auth/logout    — выход
GET  /api/auth/me        — текущий юзер
```

### Логи
```
GET    /api/logs              — список (фильтры: worker_id, tag, search, date_filter)
GET    /api/logs/{id}         — один лог
POST   /api/logs              — создать
PUT    /api/logs/{id}         — обновить
DELETE /api/logs/{id}         — удалить
POST   /api/logs/{id}/pin     — закрепить/открепить
POST   /api/logs/{id}/archive — архивировать
POST   /api/logs/{id}/duplicate — дублировать
POST   /api/logs/bulk/delete  — массовое удаление
POST   /api/logs/bulk/archive — массовая архивация
POST   /api/logs/bulk/tag     — массовая смена тега
```

### Воркеры
```
GET    /api/workers           — список
GET    /api/workers/{id}      — один воркер
POST   /api/workers           — создать
PUT    /api/workers/{id}      — обновить
DELETE /api/workers/{id}      — удалить
GET    /api/workers/{id}/stats — статистика воркера
```

### Статистика
```
GET /api/stats              — общая статистика
GET /api/leaderboard/weekly — топ за неделю
GET /api/reminders          — все проверки
GET /api/reminders/today    — проверки сегодня/завтра
```

### Geelark
```
GET  /api/geelark/settings      — настройки
POST /api/geelark/settings      — сохранить настройки
GET  /api/geelark/test          — тест подключения
GET  /api/geelark/fetch-groups  — получить группы
POST /api/geelark/sync          — синхронизировать
POST /api/geelark/groups/mapping — сохранить маппинг
```

---

## 📦 Установка

### 1. Клонирование

```bash
git clone <repo>
cd ProjectAi
```

### 2. Установка зависимостей

```bash
cd backend
pip install -r requirements.txt
```

### 3. Настройка окружения

Создайте файл `backend/.env`:

```env
BOT_TOKEN=ваш_токен_бота
API_URL=http://localhost:8000
ADMIN_CHAT_ID=ваш_telegram_id
WEB_APP_URL=https://ваш-домен.com
```

### 4. Инициализация БД

```bash
cd backend
python init_data.py
```

### 5. Запуск

**API сервер:**
```bash
cd backend
python main.py
```

**Telegram бот (в отдельном терминале):**
```bash
cd backend
python bot.py
```

Веб-интерфейс: http://localhost:8000

---

## 🖥️ Деплой на сервер

### Структура файлов

```
/var/www/logs-tracker/
├── backend/
│   ├── main.py          # API сервер
│   ├── bot.py           # Telegram бот
│   ├── models.py        # Модели БД
│   ├── database.py      # Подключение к БД
│   ├── logs_leads.db    # База данных
│   └── .env             # Переменные окружения
├── frontend/
│   ├── index.html
│   ├── script.js
│   └── style.css
```

### Systemd сервисы

```bash
# API сервер
sudo systemctl start logsapp
sudo systemctl restart logsapp
sudo systemctl status logsapp

# Telegram бот
sudo systemctl start logsbot
sudo systemctl restart logsbot
sudo systemctl status logsbot
```

### Миграция БД

```bash
cd /var/www/logs-tracker/backend
python3 migrate_db.py
```

### Бэкап БД

```bash
# Ручной бэкап
cp /var/www/logs-tracker/backend/logs_leads.db ~/backup_$(date +%Y%m%d).db

# Или через бота
/backup
```

---

## 🔧 Частые проблемы

| Проблема | Решение |
|----------|---------|
| Логи не загружаются | `sudo systemctl restart logsapp` |
| Бот не отвечает | `sudo systemctl restart logsbot` |
| Geelark не синхронизирует | Проверить Bearer Token, удалить синхронизированные: `sqlite3 logs_leads.db "DELETE FROM geelark_synced_phones;"` |
| Пустая статистика | Проверить роль пользователя (admin видит всё) |
| Ошибка миграции | Запустить `python3 migrate_db.py` |

---

## 🗂️ Структура проекта

```
ProjectAi/
├── backend/
│   ├── main.py          # FastAPI сервер + API
│   ├── bot.py           # Telegram бот (aiogram)
│   ├── models.py        # Модели SQLAlchemy
│   ├── schemas.py       # Pydantic схемы
│   ├── database.py      # Подключение к БД
│   ├── init_data.py     # Инициализация БД
│   ├── migrate_db.py    # Миграции
│   └── requirements.txt
├── frontend/
│   ├── index.html       # Главная страница
│   ├── style.css        # Стили
│   ├── script.js        # Логика
│   ├── manifest.json    # PWA манифест
│   └── sw.js            # Service Worker
├── Procfile             # Для Render
├── render.yaml          # Конфиг Render
└── README.md
```

---

## 🛠️ Технологии

- **Backend:** Python 3.10+, FastAPI, SQLAlchemy, SQLite, aiohttp
- **Bot:** aiogram 3.x
- **Frontend:** HTML5, CSS3, Vanilla JS, PWA
- **Интеграции:** Geelark API
- **Деплой:** Systemd, Nginx

---

## 📞 Контакты

- **Telegram админ:** @your_username
- **Домен:** https://trf404.digital
