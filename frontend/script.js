const API = '';
let logs = [], workers = [], stats = {}, currentView = 'dashboard', reminderDays = 0;
let currentUser = null;
let authToken = localStorage.getItem('token');

// Charts
let logsChart = null;
let tagsChart = null;

// Selection for bulk actions
let selectedLogs = new Set();

// ============ THEME ============

function toggleTheme() {
    const body = document.body;
    const btn = document.getElementById('themeToggle');
    body.classList.toggle('light-theme');
    const isLight = body.classList.contains('light-theme');
    btn.textContent = isLight ? '☀️' : '🌙';
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
}

function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        document.body.classList.add('light-theme');
        const btn = document.getElementById('themeToggle');
        if (btn) btn.textContent = '☀️';
    }
}

const TAG_LABELS = {
    fat: '🔥 Жир',
    poor: '💸 Нищий',
    medium: '📊 Средний',
    salary: '💰 Есть ЗП'
};

// API with auth
async function api(method, url, data) {
    const opts = { 
        method, 
        headers: { 'Content-Type': 'application/json' }
    };
    if (authToken) {
        opts.headers['Authorization'] = 'Bearer ' + authToken;
    }
    if (data && method !== 'GET') opts.body = JSON.stringify(data);
    if (data && method === 'GET') {
        const params = new URLSearchParams();
        Object.entries(data).forEach(([k, v]) => v && params.append(k, v));
        if (params.toString()) url += '?' + params;
    }
    try {
        const r = await fetch(API + url, opts);
        if (r.status === 401) {
            logout();
            return null;
        }
        return r.ok ? await r.json() : null;
    } catch (e) {
        console.error(e);
        return null;
    }
}

// Auth
async function login(e) {
    e.preventDefault();
    const username = document.getElementById('loginUsername').value.trim().toLowerCase();
    const password = document.getElementById('loginPassword').value;
    const errorEl = document.getElementById('loginError');
    
    errorEl.textContent = '';
    
    const r = await fetch(API + '/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });
    
    if (!r.ok) {
        errorEl.textContent = 'Неверный логин или пароль';
        return;
    }
    
    const data = await r.json();
    authToken = data.token;
    currentUser = data.user;
    localStorage.setItem('token', authToken);
    
    showApp();
}

function logout() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem('token');
    showLogin();
}

async function checkAuth() {
    if (!authToken) {
        showLogin();
        return;
    }
    
    const user = await api('GET', '/api/auth/me');
    if (!user) {
        showLogin();
        return;
    }
    
    currentUser = user;
    showApp();
}

function showLogin() {
    document.getElementById('loginScreen').style.display = 'flex';
    document.getElementById('appScreen').style.display = 'none';
}

function showApp() {
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('appScreen').style.display = 'flex';
    
    // Update UI based on role
    const isAdmin = currentUser.role === 'admin';
    
    // User info
    document.getElementById('userInfo').innerHTML = `
        <strong>${currentUser.worker_name || currentUser.username}</strong>
        <small>${isAdmin ? '👑 Админ' : '👤 Воркер'}</small>
    `;
    
    // Hide workers nav for workers
    document.getElementById('navWorkers').style.display = isAdmin ? 'flex' : 'none';
    
    // Hide workers card in stats
    document.getElementById('statWorkersCard').style.display = isAdmin ? 'flex' : 'none';
    document.getElementById('workersChartCard').style.display = isAdmin ? 'block' : 'none';
    
    // Hide worker filter for workers
    document.getElementById('filterWorker').style.display = isAdmin ? 'block' : 'none';
    
    // Hide worker column for workers
    document.getElementById('thWorker').style.display = isAdmin ? '' : 'none';
    
    // Hide worker select in log form for workers
    document.getElementById('logWorkerGroup').style.display = isAdmin ? 'block' : 'none';
    
    // Update mobile UI
    updateMobileUI();
    
    // Show admin buttons
    const resetStatsBtn = document.getElementById('resetStatsBtn');
    if (resetStatsBtn) {
        resetStatsBtn.style.display = isAdmin ? 'block' : 'none';
    }
    const importBtn = document.getElementById('importBtn');
    if (importBtn) {
        importBtn.style.display = isAdmin ? 'block' : 'none';
    }
    
    loadWorkers().then(() => switchView('dashboard'));
}

// Data Loading
async function loadStats() {
    stats = await api('GET', '/api/stats') || {};
    document.getElementById('statTotalLogs').textContent = stats.total_logs || 0;
    document.getElementById('statWorkers').textContent = stats.total_workers || 0;
    document.getElementById('statTodayChecks').textContent = stats.today_checks || 0;
    const profitEl = document.getElementById('statTotalProfit');
    if (profitEl) profitEl.textContent = stats.total_profit || '0';
    
    // Trend
    const trendEl = document.getElementById('statTrend');
    const trendCard = document.getElementById('statTrendCard');
    if (trendEl && trendCard) {
        const trend = stats.trend_percent || 0;
        const sign = trend >= 0 ? '+' : '';
        trendEl.textContent = `${sign}${trend}%`;
        trendCard.classList.toggle('trend-up', trend > 0);
        trendCard.classList.toggle('trend-down', trend < 0);
    }
    renderTagBars(stats.by_tag);
    renderLogsChart(stats.daily_stats);
    if (currentUser.role === 'admin') {
        renderWorkersWithPlan(stats.workers_stats || []);
        renderLeaderboard(stats.workers_stats || []);
        document.getElementById('workersPlanCard').style.display = 'block';
    } else {
        const planCard = document.getElementById('workersPlanCard');
        if (planCard) planCard.style.display = 'none';
    }
}

async function loadWorkers() {
    workers = await api('GET', '/api/workers') || [];
    updateWorkerSelects();
}

async function loadLogs(filters = {}) {
    logs = await api('GET', '/api/logs', filters) || [];
    renderLogsTable();
}

async function loadReminders(days = 7) {
    const url = days === 0 ? '/api/reminders/today' : '/api/reminders';
    const reminders = await api('GET', url, days ? { days } : null) || [];
    renderReminders(reminders);
    if (days <= 7) renderUpcomingChecks(reminders.slice(0, 5));
}

// Render
function renderTagBars(byTag) {
    const el = document.getElementById('tagBars');
    if (!byTag) { el.innerHTML = '<div class="empty-state">Нет данных</div>'; return; }
    const total = Object.values(byTag).reduce((a, b) => a + b, 0) || 1;
    const tags = [
        { k: 'fat', l: '🔥 Жир' },
        { k: 'poor', l: '💸 Нищий' },
        { k: 'medium', l: '📊 Средний' },
        { k: 'salary', l: '💰 Есть ЗП' }
    ];
    el.innerHTML = tags.map(t => `
        <div class="tag-bar">
            <span class="tag-bar-label">${t.l}</span>
            <div class="tag-bar-track">
                <div class="tag-bar-fill ${t.k}" style="width:${((byTag[t.k]||0)/total)*100}%"></div>
            </div>
            <span class="tag-bar-value">${byTag[t.k]||0}</span>
        </div>
    `).join('');
    
    // Render tags pie chart
    renderTagsChart(byTag);
}

// ============ CHARTS ============

function renderLogsChart(dailyStats) {
    const ctx = document.getElementById('logsChart');
    if (!ctx) return;
    
    // Destroy existing chart
    if (logsChart) {
        logsChart.destroy();
    }
    
    // Generate last 7 days labels
    const labels = [];
    const data = [];
    const today = new Date();
    
    for (let i = 6; i >= 0; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        const dayName = date.toLocaleDateString('ru-RU', { weekday: 'short' });
        const dayNum = date.getDate();
        labels.push(`${dayName} ${dayNum}`);
        // Use real data from API
        const dataIndex = 6 - i;
        data.push(dailyStats?.[dataIndex] ?? 0);
    }
    
    logsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Логи',
                data: data,
                borderColor: '#8b5cf6',
                backgroundColor: 'rgba(139, 92, 246, 0.1)',
                borderWidth: 3,
                fill: true,
                tension: 0.4,
                pointBackgroundColor: '#8b5cf6',
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointRadius: 5,
                pointHoverRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(139, 92, 246, 0.1)'
                    },
                    ticks: {
                        color: '#7a7a95'
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#7a7a95'
                    }
                }
            }
        }
    });
}

function renderTagsChart(byTag) {
    const ctx = document.getElementById('tagsChart');
    if (!ctx || !byTag) return;
    
    if (tagsChart) {
        tagsChart.destroy();
    }
    
    const data = [
        byTag.fat || 0,
        byTag.medium || 0,
        byTag.salary || 0,
        byTag.poor || 0
    ];
    
    tagsChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['🔥 Жир', '📊 Средний', '💰 Есть ЗП', '💸 Нищий'],
            datasets: [{
                data: data,
                backgroundColor: [
                    'rgba(239, 68, 68, 0.8)',
                    'rgba(139, 92, 246, 0.8)',
                    'rgba(16, 185, 129, 0.8)',
                    'rgba(107, 114, 128, 0.8)'
                ],
                borderColor: [
                    '#ef4444',
                    '#8b5cf6',
                    '#10b981',
                    '#6b7280'
                ],
                borderWidth: 2,
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#e8e8f0',
                        padding: 15,
                        font: {
                            size: 12
                        }
                    }
                }
            },
            cutout: '60%'
        }
    });
}

// ============ LEADERBOARD ============

function renderLeaderboard(workersStats) {
    const el = document.getElementById('leaderboard');
    if (!el) return;
    
    if (!workersStats || !workersStats.length) {
        el.innerHTML = '<div class="empty-state">Нет данных</div>';
        return;
    }
    
    // Sort by total logs
    const sorted = [...workersStats].sort((a, b) => b.total - a.total).slice(0, 5);
    
    el.innerHTML = sorted.map((w, idx) => {
        let rankClass = 'regular';
        let rankIcon = idx + 1;
        
        if (idx === 0) { rankClass = 'gold'; rankIcon = '🥇'; }
        else if (idx === 1) { rankClass = 'silver'; rankIcon = '🥈'; }
        else if (idx === 2) { rankClass = 'bronze'; rankIcon = '🥉'; }
        
        return `
        <div class="leaderboard-item" onclick="viewWorkerLogs(${w.id}, '${esc(w.name)}')">
            <div class="leaderboard-rank ${rankClass}">${rankIcon}</div>
            <div class="leaderboard-info">
                <div class="leaderboard-name">${esc(w.name)}</div>
                <div class="leaderboard-stats">Сегодня: ${w.today} | Неделя: ${w.week}</div>
            </div>
            <div class="leaderboard-count">${w.total}</div>
        </div>`;
    }).join('');
}

// ============ EXPORT TO EXCEL ============

async function exportToExcel() {
    // Get all logs
    const allLogs = await api('GET', '/api/logs', { limit: 10000 });
    if (!allLogs || !allLogs.length) {
        alert('Нет данных для экспорта');
        return;
    }
    
    // Create CSV content
    const headers = ['ID', 'Воркер', '№ Лога', 'Баланс', 'Владелец', 'Дата установки', 'Дата проверки', 'Тег', 'Комментарий', 'Создан'];
    const rows = allLogs.map(l => [
        l.id,
        l.worker_name || '',
        l.log_number || '',
        l.balance || '',
        l.owner || '',
        l.install_date || '',
        l.check_date || '',
        TAG_LABELS[l.tag] || l.tag || '',
        (l.comment || '').replace(/[\n\r]/g, ' '),
        l.created_at || ''
    ]);
    
    // BOM for UTF-8
    const BOM = '\uFEFF';
    const csvContent = BOM + [
        headers.join(';'),
        ...rows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(';'))
    ].join('\n');
    
    // Download
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `logs_export_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
}

function renderWorkersWithPlan(workersStats) {
    const el = document.getElementById('workersList');
    if (!workersStats || !workersStats.length) { 
        el.innerHTML = '<div class="empty-state">Нет данных</div>'; 
        return; 
    }
    
    el.innerHTML = workersStats.sort((a, b) => (b.today || 0) - (a.today || 0)).map(w => {
        const today = w.today || 0;
        const plan = w.daily_goal || 3;
        const week = w.week || 0;
        const total = w.total || 0;
        const percent = Math.min((today / plan) * 100, 100);
        const planStatus = today >= plan ? 'done' : (today > 0 ? 'progress' : 'empty');
        const remaining = plan - today;
        
        return `
        <div class="worker-plan-card clickable" onclick="viewWorkerLogs(${w.id}, '${esc(w.name)}')">
            <div class="worker-plan-header">
                <span class="worker-plan-name">👤 ${esc(w.name)}</span>
                <span class="worker-plan-week" title="За неделю">📅 ${week}</span>
            </div>
            <div class="worker-plan-progress">
                <div class="worker-plan-bar">
                    <div class="worker-plan-fill ${planStatus}" style="width: ${percent}%"></div>
                </div>
                <span class="worker-plan-count ${planStatus}">${today}/${plan}</span>
            </div>
            <div class="worker-plan-footer">
                <span>Всего: ${total}</span>
                <span>${today >= plan ? '✅ План выполнен' : `⏳ Осталось: ${remaining}`}</span>
            </div>
        </div>`;
    }).join('');
}

// Просмотр логов воркера
function viewWorkerLogs(workerId, workerName) {
    if (!workerId) return;
    
    // Переключаемся на вкладку "Все логи"
    switchView('logs');
    
    // Устанавливаем фильтр по воркеру
    const filterWorker = document.getElementById('filterWorker');
    if (filterWorker) {
        filterWorker.value = workerId;
    }
    
    // Обновляем заголовок
    document.getElementById('pageTitle').textContent = 'Логи: ' + workerName;
    document.getElementById('pageSubtitle').textContent = 'Все кабинеты воркера';
    
    // Загружаем логи с фильтром
    loadLogs({ worker_id: workerId });
}

// Хранилище для ближайших проверок
let upcomingChecksData = [];

function renderUpcomingChecks(checks) {
    const el = document.getElementById('upcomingChecks');
    upcomingChecksData = checks || [];
    
    if (!checks?.length) { el.innerHTML = '<div class="empty-state">Нет проверок</div>'; return; }
    
    const today = new Date().getDate();
    const tomorrow = new Date(Date.now() + 86400000).getDate();
    
    el.innerHTML = checks.map((l, idx) => {
        // Определяем когда проверка
        const days = (l.check_date || '').split('-').map(d => parseInt(d.trim())).filter(d => !isNaN(d));
        let when = '';
        if (days.includes(today)) when = '🔴 Сегодня';
        else if (days.includes(tomorrow)) when = '🟡 Завтра';
        
        return `
        <div class="check-item clickable" onclick="showLogDetails(${idx})">
            <span class="check-item-when">${when}</span>
            <span class="check-item-log">№${esc(l.log_number)}</span>
            <span class="check-item-worker">${esc(l.worker_name)}</span>
        </div>`;
    }).join('');
}

// Показать детали лога
function showLogDetails(idx) {
    const log = upcomingChecksData[idx];
    if (!log) return;
    
    const tag = TAG_LABELS[log.tag] || log.tag;
    const owner = log.owner ? `@${log.owner}` : '—';
    
    const content = `
        <div class="log-details">
            <div class="log-details-row">
                <span class="log-details-label">Номер лога</span>
                <span class="log-details-value">№${esc(log.log_number)}</span>
            </div>
            <div class="log-details-row">
                <span class="log-details-label">Воркер</span>
                <span class="log-details-value">👤 ${esc(log.worker_name)}</span>
            </div>
            <div class="log-details-row">
                <span class="log-details-label">Баланс</span>
                <span class="log-details-value">💰 ${esc(log.balance)}</span>
            </div>
            <div class="log-details-row">
                <span class="log-details-label">Владелец</span>
                <span class="log-details-value">${esc(owner)}</span>
            </div>
            <div class="log-details-row">
                <span class="log-details-label">Дата установки</span>
                <span class="log-details-value">📅 ${log.install_date || '—'}</span>
            </div>
            <div class="log-details-row">
                <span class="log-details-label">Дни проверки</span>
                <span class="log-details-value">🔔 ${log.check_date || '—'}</span>
            </div>
            <div class="log-details-row">
                <span class="log-details-label">Тег</span>
                <span class="log-details-value">${tag}</span>
            </div>
            <div class="log-details-row">
                <span class="log-details-label">Комментарий</span>
                <span class="log-details-value">${esc(log.comment) || '—'}</span>
            </div>
        </div>
        <div class="form-actions">
            <button class="btn btn-secondary" onclick="closeDetailsModal()">Закрыть</button>
            <button class="btn btn-primary" onclick="editLogFromDetails(${log.id})">✏️ Редактировать</button>
        </div>
    `;
    
    document.getElementById('detailsModalTitle').textContent = `Лог №${log.log_number}`;
    document.getElementById('detailsModalContent').innerHTML = content;
    document.getElementById('detailsModal').classList.add('active');
}

function closeDetailsModal() {
    document.getElementById('detailsModal').classList.remove('active');
}

function editLogFromDetails(logId) {
    closeDetailsModal();
    const log = logs.find(l => l.id === logId) || upcomingChecksData.find(l => l.id === logId);
    if (log) openLogModal(log);
}

function renderLogsTable() {
    const el = document.getElementById('logsTableBody');
    const isAdmin = currentUser.role === 'admin';
    const isArchive = document.getElementById('filterArchive')?.value === 'true';
    
    if (!logs?.length) { 
        el.innerHTML = `<tr><td colspan="${isAdmin ? 12 : 11}" class="empty-state">${isArchive ? 'Архив пуст' : 'Логов нет'}</td></tr>`; 
        return; 
    }
    
    el.innerHTML = logs.map(l => `
        <tr class="${selectedLogs.has(l.id) ? 'selected' : ''} ${l.is_archived ? 'archived' : ''}">
            <td><input type="checkbox" class="log-checkbox" data-id="${l.id}" ${selectedLogs.has(l.id) ? 'checked' : ''} onchange="toggleLogSelect(${l.id})"></td>
            <td class="cell-mono cell-muted">#${l.id}</td>
            ${isAdmin ? `<td><strong>${esc(l.worker_name)}</strong></td>` : ''}
            <td class="cell-mono">${esc(l.log_number)}</td>
            <td class="cell-mono">${esc(l.balance)}</td>
            <td class="cell-mono cell-profit">${l.profit ? `<span class="profit-badge">+${esc(l.profit)}</span>` : '—'}</td>
            <td class="cell-owner">${l.owner ? `<span class="owner-badge">@${esc(l.owner)}</span>` : '—'}</td>
            <td class="cell-mono cell-muted">${l.install_date||'—'}</td>
            <td class="cell-mono cell-muted">${l.check_date||'—'}</td>
            <td><span class="tag-badge ${l.tag}">${TAG_LABELS[l.tag]||l.tag}</span></td>
            <td>
                <div class="actions">
                    <button class="action-btn" onclick="editLog(${l.id})">✏️</button>
                    ${l.is_archived 
                        ? `<button class="action-btn" onclick="unarchiveLog(${l.id})" title="Восстановить">📤</button>`
                        : `<button class="action-btn" onclick="archiveLog(${l.id})" title="Архив">📦</button>`
                    }
                    <button class="action-btn" onclick="deleteLog(${l.id})">🗑️</button>
                </div>
            </td>
        </tr>
    `).join('');
    
    updateBulkActionsUI();
}

function renderWorkersGrid() {
    const el = document.getElementById('workersGrid');
    if (!workers?.length) { el.innerHTML = '<div class="empty-state">Нет воркеров</div>'; return; }
    el.innerHTML = workers.map(w => `
        <div class="worker-card">
            <div class="worker-card-header">
                <span class="worker-card-name">👤 ${esc(w.name)}</span>
                <span class="worker-level">⭐ Ур.${w.level || 1}</span>
                <div class="actions">
                    <button class="action-btn" onclick="editWorker(${w.id})">✏️</button>
                    <button class="action-btn" onclick="deleteWorker(${w.id})">🗑️</button>
                </div>
            </div>
            <div class="worker-xp-bar">
                <div class="worker-xp-fill" style="width: ${Math.min((w.xp || 0) % 100, 100)}%"></div>
            </div>
            <div class="worker-card-stats">${w.logs_count||0}</div>
            <div class="worker-card-label">логов | ${w.xp || 0} XP</div>
        </div>
    `).join('');
}

function renderReminders(reminders) {
    const el = document.getElementById('remindersGrid');
    if (!reminders?.length) { el.innerHTML = '<div class="empty-state">Нет проверок</div>'; return; }
    el.innerHTML = reminders.map(l => `
        <div class="reminder-card">
            <div class="reminder-card-header">
                <span class="reminder-card-pin">№${esc(l.log_number)} | ${esc(l.pin)}</span>
                <span class="reminder-card-date">${l.check_date||'—'}</span>
            </div>
            <div class="reminder-card-info">
                <span>👤 ${esc(l.worker_name)}</span>
                <span>💰 ${esc(l.balance)}</span>
                <span>${TAG_LABELS[l.tag]||l.tag}</span>
            </div>
        </div>
    `).join('');
}

function updateWorkerSelects() {
    const isAdmin = currentUser.role === 'admin';
    
    if (isAdmin) {
        const opts = '<option value="">Все воркеры</option>' + workers.map(w => 
            `<option value="${w.id}">${esc(w.name)}</option>`
        ).join('');
        document.getElementById('filterWorker').innerHTML = opts;
    }
    
    document.getElementById('logWorker').innerHTML = '<option value="">Выберите воркера</option>' + 
        workers.map(w => `<option value="${w.id}">${esc(w.name)}</option>`).join('');
}

// Navigation
function switchView(view) {
    // Workers view only for admin
    if (view === 'workers' && currentUser.role !== 'admin') {
        view = 'dashboard';
    }
    
    currentView = view;
    
    // Update sidebar nav
    document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === view));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    
    // Update bottom nav
    document.querySelectorAll('.bottom-nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.view === view);
    });
    
    // Close mobile menu
    closeMobileMenu();
    
    const titles = {
        dashboard: ['Dashboard', 'Общая статистика'],
        logs: ['Все логи', currentUser.role === 'admin' ? 'Управление логами' : 'Мои логи'],
        workers: ['Воркеры', 'Управление воркерами'],
        reminders: ['Проверки', 'Логи на проверку']
    };
    document.getElementById('pageTitle').textContent = titles[view][0];
    document.getElementById('pageSubtitle').textContent = titles[view][1];
    
    document.getElementById(view + 'View').classList.add('active');
    
    if (view === 'dashboard') { loadStats(); loadReminders(7); }
    else if (view === 'logs') { loadLogs(); }
    else if (view === 'workers') { loadWorkers().then(() => renderWorkersGrid()); }
    else if (view === 'reminders') { loadReminders(reminderDays); }
}

// Log Modal
function openLogModal(log = null) {
    document.getElementById('logModalTitle').textContent = log ? 'Редактировать лог' : 'Добавить лог';
    document.getElementById('logId').value = log?.id || '';
    document.getElementById('logWorker').value = log?.worker_id || (currentUser.worker_id || '');
    document.getElementById('logNumber').value = log?.log_number || '';
    document.getElementById('logBalance').value = log?.balance || '';
    document.getElementById('logProfit').value = log?.profit || '';
    document.getElementById('logOwner').value = log?.owner || '';
    document.getElementById('logInstallDate').value = log?.install_date || '';
    document.getElementById('logCheckDate').value = log?.check_date || '';
    document.getElementById('logTag').value = log?.tag || 'medium';
    document.getElementById('logComment').value = log?.comment || '';
    document.getElementById('logModal').classList.add('active');
}

function closeLogModal() {
    document.getElementById('logModal').classList.remove('active');
}

async function saveLog(e) {
    e.preventDefault();
    const data = {
        worker_id: parseInt(document.getElementById('logWorker').value) || currentUser.worker_id,
        log_number: document.getElementById('logNumber').value,
        balance: document.getElementById('logBalance').value || '0',
        profit: document.getElementById('logProfit').value || null,
        owner: document.getElementById('logOwner').value || null,
        install_date: document.getElementById('logInstallDate').value,
        check_date: document.getElementById('logCheckDate').value || null,
        tag: document.getElementById('logTag').value,
        comment: document.getElementById('logComment').value || null
    };
    const id = document.getElementById('logId').value;
    const r = id ? await api('PUT', `/api/logs/${id}`, data) : await api('POST', '/api/logs', data);
    if (r) { 
        closeLogModal(); 
        loadLogs(); 
        loadStats();
        showToast(id ? '✅ Лог обновлён!' : '✅ Лог добавлен!');
        if (!id) showConfetti(); // Confetti only for new logs
    } else {
        showToast('❌ Ошибка сохранения', 'error');
    }
}

async function editLog(id) {
    const log = logs.find(l => l.id === id);
    if (log) openLogModal(log);
}

async function deleteLog(id) {
    if (!confirm('Удалить лог?')) return;
    if (await api('DELETE', `/api/logs/${id}`)) { loadLogs(); loadStats(); }
}

// Worker Modal (Admin only)
function openWorkerModal(worker = null) {
    document.getElementById('workerModalTitle').textContent = worker ? 'Редактировать воркера' : 'Добавить воркера';
    document.getElementById('workerId').value = worker?.id || '';
    document.getElementById('workerName').value = worker?.name || '';
    document.getElementById('workerNotes').value = worker?.notes || '';
    document.getElementById('workerModal').classList.add('active');
}

function closeWorkerModal() {
    document.getElementById('workerModal').classList.remove('active');
}

async function saveWorker(e) {
    e.preventDefault();
    const data = {
        name: document.getElementById('workerName').value,
        notes: document.getElementById('workerNotes').value || null
    };
    const id = document.getElementById('workerId').value;
    const r = id ? await api('PUT', `/api/workers/${id}`, data) : await api('POST', '/api/workers', data);
    if (r) { closeWorkerModal(); loadWorkers().then(() => { if (currentView === 'workers') renderWorkersGrid(); }); loadStats(); }
}

async function editWorker(id) {
    const w = workers.find(w => w.id === id);
    if (w) openWorkerModal(w);
}

async function deleteWorker(id) {
    const w = workers.find(w => w.id === id);
    if (!confirm(`Удалить воркера "${w?.name}"?`)) return;
    if (await api('DELETE', `/api/workers/${id}`)) { 
        loadWorkers().then(() => { if (currentView === 'workers') renderWorkersGrid(); }); 
        loadStats(); 
    }
}

// ============ ADMIN: RESET STATS ============

async function resetStats() {
    if (!confirm('🔄 Сбросить статистику?\n\nСчётчики "за день" и "за неделю" обнулятся.\nВсе логи останутся на месте!')) return;
    
    const result = await api('POST', '/api/admin/reset-stats');
    if (result && result.ok) {
        showToast('✅ Статистика сброшена!');
        loadStats();
    } else {
        showToast('❌ Ошибка при сбросе', 'error');
    }
}

// ============ IMPORT/EXPORT ============

function openImportModal() {
    document.getElementById('importModal').classList.add('active');
    document.getElementById('importData').value = '';
    document.getElementById('importPreview').innerHTML = '';
}

function closeImportModal() {
    document.getElementById('importModal').classList.remove('active');
}

function handleImportFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const reader = new FileReader();
    reader.onload = (e) => {
        const text = e.target.result;
        
        // Если CSV
        if (file.name.endsWith('.csv')) {
            const rows = parseCSV(text);
            document.getElementById('importData').value = JSON.stringify(rows, null, 2);
            document.getElementById('importPreview').innerHTML = `<div class="import-preview-text">📊 Найдено ${rows.length} записей</div>`;
        } else {
            document.getElementById('importData').value = text;
            try {
                const data = JSON.parse(text);
                document.getElementById('importPreview').innerHTML = `<div class="import-preview-text">📊 Найдено ${data.length} записей</div>`;
            } catch {
                document.getElementById('importPreview').innerHTML = `<div class="import-preview-error">❌ Некорректный JSON</div>`;
            }
        }
    };
    reader.readAsText(file);
}

function parseCSV(text) {
    const lines = text.trim().split('\n');
    if (lines.length < 2) return [];
    
    const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
    const rows = [];
    
    for (let i = 1; i < lines.length; i++) {
        const values = lines[i].split(',');
        const row = {};
        headers.forEach((h, idx) => {
            row[h] = values[idx]?.trim() || '';
        });
        rows.push(row);
    }
    
    return rows;
}

async function doImport() {
    const dataText = document.getElementById('importData').value.trim();
    if (!dataText) {
        showToast('❌ Введите данные', 'error');
        return;
    }
    
    let rows;
    try {
        rows = JSON.parse(dataText);
    } catch {
        showToast('❌ Некорректный JSON', 'error');
        return;
    }
    
    if (!Array.isArray(rows) || rows.length === 0) {
        showToast('❌ Нет данных', 'error');
        return;
    }
    
    const result = await api('POST', '/api/admin/import-csv', { rows });
    if (result?.ok) {
        showToast(`✅ Импортировано: ${result.imported}`);
        if (result.errors?.length) {
            console.warn('Import errors:', result.errors);
        }
        closeImportModal();
        loadLogs();
        loadStats();
    } else {
        showToast('❌ Ошибка импорта', 'error');
    }
}

async function exportToCSV() {
    const data = await api('GET', '/api/admin/export-csv');
    if (!data) return;
    
    const headers = ['id', 'worker', 'log_number', 'balance', 'profit', 'owner', 'install_date', 'check_date', 'tag', 'comment', 'created_at'];
    const csv = [headers.join(',')];
    
    data.forEach(row => {
        const values = headers.map(h => `"${(row[h] || '').toString().replace(/"/g, '""')}"`);
        csv.push(values.join(','));
    });
    
    const blob = new Blob([csv.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `logs_export_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    
    showToast(`📤 Экспортировано ${data.length} записей`);
}

// Filters
function applyFilters() {
    clearSelection();
    loadLogs({
        worker_id: document.getElementById('filterWorker').value,
        tag: document.getElementById('filterTag').value,
        date_filter: document.getElementById('filterDate')?.value || '',
        archived: document.getElementById('filterArchive')?.value || 'false'
    });
}

// ============ SELECTION & BULK ACTIONS ============

function toggleLogSelect(id) {
    if (selectedLogs.has(id)) {
        selectedLogs.delete(id);
    } else {
        selectedLogs.add(id);
    }
    updateBulkActionsUI();
}

function toggleSelectAll() {
    const selectAll = document.getElementById('selectAll');
    if (selectAll.checked) {
        logs.forEach(l => selectedLogs.add(l.id));
    } else {
        selectedLogs.clear();
    }
    renderLogsTable();
}

function clearSelection() {
    selectedLogs.clear();
    const selectAll = document.getElementById('selectAll');
    if (selectAll) selectAll.checked = false;
    updateBulkActionsUI();
    renderLogsTable();
}

function updateBulkActionsUI() {
    const bulkActions = document.getElementById('bulkActions');
    const selectedCount = document.getElementById('selectedCount');
    
    if (bulkActions) {
        bulkActions.style.display = selectedLogs.size > 0 ? 'flex' : 'none';
    }
    if (selectedCount) {
        selectedCount.textContent = `${selectedLogs.size} выбрано`;
    }
}

async function bulkDelete() {
    if (selectedLogs.size === 0) return;
    if (!confirm(`Удалить ${selectedLogs.size} логов?`)) return;
    
    const result = await api('POST', '/api/logs/bulk/delete', { ids: Array.from(selectedLogs) });
    if (result?.ok) {
        showToast(`✅ Удалено: ${result.deleted}`);
        clearSelection();
        loadLogs();
        loadStats();
    }
}

async function bulkArchive() {
    if (selectedLogs.size === 0) return;
    
    const result = await api('POST', '/api/logs/bulk/archive', { ids: Array.from(selectedLogs) });
    if (result?.ok) {
        showToast(`📦 Архивировано: ${result.archived}`);
        clearSelection();
        loadLogs();
        loadStats();
    }
}

async function bulkChangeTag() {
    if (selectedLogs.size === 0) return;
    
    const tag = prompt('Выберите тег:\n1 - Жир\n2 - Нищий\n3 - Средний\n4 - Есть ЗП');
    const tagMap = { '1': 'fat', '2': 'poor', '3': 'medium', '4': 'salary' };
    const newTag = tagMap[tag];
    
    if (!newTag) return;
    
    const result = await api('POST', '/api/logs/bulk/tag', { ids: Array.from(selectedLogs), tag: newTag });
    if (result?.ok) {
        showToast(`🏷 Изменено: ${result.updated}`);
        clearSelection();
        loadLogs();
    }
}

// ============ ARCHIVE ============

async function archiveLog(id) {
    const result = await api('POST', `/api/logs/${id}/archive`);
    if (result?.ok) {
        showToast('📦 Архивировано');
        loadLogs();
        loadStats();
    }
}

async function unarchiveLog(id) {
    const result = await api('POST', `/api/logs/${id}/unarchive`);
    if (result?.ok) {
        showToast('📤 Восстановлено');
        loadLogs();
        loadStats();
    }
}

// Search
let searchTimeout;
function handleSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        if (currentView === 'logs') loadLogs({ search: document.getElementById('searchInput').value });
    }, 300);
}

// Utils
function esc(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// Toast notifications
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    if (type === 'error') {
        toast.style.background = 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)';
    }
    document.body.appendChild(toast);
    
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 400);
    }, 3000);
}

// Confetti effect
function showConfetti() {
    const colors = ['#8b5cf6', '#06b6d4', '#f59e0b', '#10b981', '#ef4444'];
    for (let i = 0; i < 50; i++) {
        const confetti = document.createElement('div');
        confetti.className = 'confetti-piece';
        confetti.style.left = Math.random() * 100 + 'vw';
        confetti.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
        confetti.style.animationDelay = Math.random() * 2 + 's';
        confetti.style.borderRadius = Math.random() > 0.5 ? '50%' : '0';
        document.body.appendChild(confetti);
        setTimeout(() => confetti.remove(), 5000);
    }
}

// ============ MOBILE MENU ============

function toggleMobileMenu() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const burger = document.getElementById('burgerBtn');
    
    sidebar.classList.toggle('open');
    overlay.classList.toggle('active');
    burger.classList.toggle('active');
}

function closeMobileMenu() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const burger = document.getElementById('burgerBtn');
    
    sidebar.classList.remove('open');
    overlay.classList.remove('active');
    burger.classList.remove('active');
}

function mobileNav(view) {
    // Update bottom nav active state
    document.querySelectorAll('.bottom-nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.view === view);
    });
    
    switchView(view);
}

function updateMobileUI() {
    // Hide workers in bottom nav for workers
    const isAdmin = currentUser?.role === 'admin';
    const bottomNavWorkers = document.getElementById('bottomNavWorkers');
    if (bottomNavWorkers) {
        bottomNavWorkers.style.display = isAdmin ? 'flex' : 'none';
    }
}

// Init
document.addEventListener('DOMContentLoaded', () => {
    // Theme
    initTheme();
    
    // Register Service Worker (PWA)
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js')
            .then(reg => console.log('SW registered'))
            .catch(err => console.log('SW error', err));
    }
    
    // Login form
    document.getElementById('loginForm').addEventListener('submit', login);
    
    // Nav
    document.querySelectorAll('.nav-item').forEach(n => {
        n.addEventListener('click', e => { e.preventDefault(); switchView(n.dataset.view); });
    });
    
    // Buttons
    document.getElementById('addLogBtn').addEventListener('click', () => openLogModal());
    document.getElementById('addWorkerBtn').addEventListener('click', () => openWorkerModal());
    
    // Forms
    document.getElementById('logForm').addEventListener('submit', saveLog);
    document.getElementById('workerForm').addEventListener('submit', saveWorker);
    
    // Filters
    document.getElementById('filterWorker').addEventListener('change', applyFilters);
    document.getElementById('filterTag').addEventListener('change', applyFilters);
    document.getElementById('filterDate')?.addEventListener('change', applyFilters);
    document.getElementById('filterArchive')?.addEventListener('change', applyFilters);
    document.getElementById('searchInput').addEventListener('input', handleSearch);
    
    // Tabs
    document.querySelectorAll('.tab').forEach(t => {
        t.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
            t.classList.add('active');
            reminderDays = parseInt(t.dataset.days);
            loadReminders(reminderDays);
        });
    });
    
    // Escape
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') { closeLogModal(); closeWorkerModal(); closeDetailsModal(); }
    });
    
    // Modal overlays
    document.getElementById('logModal').addEventListener('click', e => {
        if (e.target.id === 'logModal') closeLogModal();
    });
    document.getElementById('workerModal').addEventListener('click', e => {
        if (e.target.id === 'workerModal') closeWorkerModal();
    });
    document.getElementById('detailsModal').addEventListener('click', e => {
        if (e.target.id === 'detailsModal') closeDetailsModal();
    });
    
    // Check auth
    checkAuth();
});
