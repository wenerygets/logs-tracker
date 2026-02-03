const API = '';
let logs = [], workers = [], stats = {}, currentView = 'dashboard', reminderDays = 0;
let currentUser = null;
let authToken = localStorage.getItem('token');

// Charts
let logsChart = null;
let tagsChart = null;

// Selection for bulk actions
let selectedLogs = new Set();

// Sorting
let sortColumn = null;
let sortDirection = 'desc';

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
    
    // Hide admin-only nav items for workers
    document.getElementById('navWorkers').style.display = isAdmin ? 'flex' : 'none';
    document.getElementById('navGeelark').style.display = isAdmin ? 'flex' : 'none';
    document.getElementById('navSberCheck').style.display = isAdmin ? 'flex' : 'none';
    
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
    renderFunnel(stats.by_tag);
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
    updateGeelarkWorkerSelects();
}

async function loadLogs(filters = {}) {
    const profitFilter = filters.profit_filter;
    delete filters.profit_filter;
    
    logs = await api('GET', '/api/logs', filters) || [];
    logs = filterLogsByProfit(logs, profitFilter);
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

// ============ FUNNEL ============

function renderFunnel(byTag) {
    const el = document.getElementById('funnelChart');
    if (!el) return;
    
    if (!byTag || Object.values(byTag).every(v => v === 0)) {
        el.innerHTML = '<div class="empty-state">Нет данных</div>';
        return;
    }
    
    // Сортируем по "воронке": Нищий -> Средний -> Есть ЗП -> Жир
    const funnelData = [
        { key: 'poor', name: 'Нищий', color: '#a855f7', icon: '💸' },
        { key: 'medium', name: 'Средний', color: '#3b82f6', icon: '📊' },
        { key: 'salary', name: 'Есть ЗП', color: '#22c55e', icon: '💰' },
        { key: 'fat', name: 'Жир', color: '#ef4444', icon: '🔥' },
    ];
    
    const total = Object.values(byTag).reduce((a, b) => a + b, 0) || 1;
    
    el.innerHTML = funnelData.map((item, idx) => {
        const count = byTag[item.key] || 0;
        const percent = Math.round((count / total) * 100);
        const width = Math.max(20, 100 - (idx * 15)); // Сужающаяся воронка
        
        return `
        <div class="funnel-item" style="--funnel-color: ${item.color}; --funnel-width: ${width}%">
            <div class="funnel-bar" style="width: ${width}%">
                <span class="funnel-icon">${item.icon}</span>
                <span class="funnel-name">${item.name}</span>
                <span class="funnel-count">${count}</span>
                <span class="funnel-percent">${percent}%</span>
            </div>
        </div>`;
    }).join('');
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

// ============ PDF REPORT ============

async function generatePDFReport() {
    const statsData = await api('GET', '/api/stats');
    if (!statsData) {
        showToast('❌ Ошибка загрузки данных', 'error');
        return;
    }
    
    const today = new Date().toLocaleDateString('ru-RU');
    
    // Создаём HTML отчёт
    const html = `
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Отчёт Logs TRF.404 - ${today}</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 40px; background: white; color: #1e293b; }
        h1 { color: #8b5cf6; border-bottom: 3px solid #8b5cf6; padding-bottom: 10px; }
        h2 { color: #475569; margin-top: 30px; }
        .stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }
        .stat-box { background: #f8fafc; padding: 20px; border-radius: 10px; text-align: center; border: 1px solid #e2e8f0; }
        .stat-value { font-size: 32px; font-weight: bold; color: #8b5cf6; }
        .stat-label { color: #64748b; font-size: 14px; }
        .workers-table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        .workers-table th, .workers-table td { border: 1px solid #e2e8f0; padding: 12px; text-align: left; }
        .workers-table th { background: #f8fafc; font-weight: 600; }
        .workers-table tr:nth-child(even) { background: #f8fafc; }
        .footer { margin-top: 40px; text-align: center; color: #94a3b8; font-size: 12px; }
        @media print { body { padding: 20px; } }
    </style>
</head>
<body>
    <h1>📊 Отчёт Logs TRF.404</h1>
    <p>Дата: <strong>${today}</strong></p>
    
    <div class="stat-grid">
        <div class="stat-box">
            <div class="stat-value">${statsData.total_logs || 0}</div>
            <div class="stat-label">Всего логов</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">${statsData.total_workers || 0}</div>
            <div class="stat-label">Воркеров</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">${statsData.today_checks || 0}</div>
            <div class="stat-label">Проверок сегодня</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">${statsData.total_profit || '0'}</div>
            <div class="stat-label">Общий профит</div>
        </div>
    </div>
    
    <h2>👥 Статистика по воркерам</h2>
    <table class="workers-table">
        <tr>
            <th>Воркер</th>
            <th>Сегодня</th>
            <th>Неделя</th>
            <th>Всего</th>
            <th>План</th>
        </tr>
        ${(statsData.workers_stats || []).map(w => `
        <tr>
            <td>${w.name}</td>
            <td>${w.today || 0}</td>
            <td>${w.week || 0}</td>
            <td>${w.total || 0}</td>
            <td>${w.today || 0}/${w.daily_goal || 3}</td>
        </tr>
        `).join('')}
    </table>
    
    <h2>🏷️ Распределение по тегам</h2>
    <table class="workers-table">
        <tr><th>Тег</th><th>Количество</th></tr>
        <tr><td>🔥 Жир</td><td>${statsData.by_tag?.fat || 0}</td></tr>
        <tr><td>💸 Нищий</td><td>${statsData.by_tag?.poor || 0}</td></tr>
        <tr><td>📊 Средний</td><td>${statsData.by_tag?.medium || 0}</td></tr>
        <tr><td>💰 Есть ЗП</td><td>${statsData.by_tag?.salary || 0}</td></tr>
    </table>
    
    <div class="footer">
        Сгенерировано системой Logs TRF.404 | ${today}
    </div>
</body>
</html>`;
    
    // Открываем в новом окне для печати
    const printWindow = window.open('', '_blank');
    printWindow.document.write(html);
    printWindow.document.close();
    
    // Автоматически открываем диалог печати
    setTimeout(() => {
        printWindow.print();
    }, 500);
    
    showToast('📄 Отчёт готов к печати!');
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
    
    currentView = 'logs';
    
    // Update UI without calling loadLogs
    document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === 'logs'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.bottom-nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === 'logs'));
    document.getElementById('logsView').classList.add('active');
    
    // Устанавливаем фильтр по воркеру
    const filterWorker = document.getElementById('filterWorker');
    if (filterWorker) {
        filterWorker.value = workerId;
    }
    
    // Сбрасываем остальные фильтры
    document.getElementById('filterTag').value = '';
    document.getElementById('filterDate').value = '';
    document.getElementById('filterArchive').value = 'false';
    document.getElementById('filterProfit').value = '';
    
    // Обновляем заголовок
    document.getElementById('pageTitle').textContent = 'Логи: ' + workerName;
    document.getElementById('pageSubtitle').textContent = 'Все кабинеты воркера';
    
    // Загружаем логи ТОЛЬКО этого воркера
    loadLogs({ worker_id: workerId });
}

// Хранилище для ближайших проверок
let upcomingChecksData = [];

function renderUpcomingChecks(checks) {
    const el = document.getElementById('upcomingChecks');
    
    if (!checks?.length) { 
        upcomingChecksData = [];
        el.innerHTML = '<div class="empty-state">Нет проверок</div>'; 
        return; 
    }
    
    const today = new Date().getDate();
    const tomorrow = new Date(Date.now() + 86400000).getDate();
    
    // Фильтруем только логи на сегодня и завтра
    const filtered = checks.filter(l => {
        const days = (l.check_date || '').split('-').map(d => parseInt(d.trim())).filter(d => !isNaN(d));
        return days.includes(today) || days.includes(tomorrow);
    });
    
    upcomingChecksData = filtered;
    
    if (!filtered.length) { 
        el.innerHTML = '<div class="empty-state">Нет проверок на сегодня/завтра</div>'; 
        return; 
    }
    
    el.innerHTML = filtered.map((l, idx) => {
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

function sortLogs(column) {
    if (sortColumn === column) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortColumn = column;
        sortDirection = 'desc';
    }
    renderLogsTable();
}

function renderLogsTable() {
    const el = document.getElementById('logsTableBody');
    const isAdmin = currentUser.role === 'admin';
    const isArchive = document.getElementById('filterArchive')?.value === 'true';
    
    if (!logs?.length) { 
        el.innerHTML = `<tr><td colspan="${isAdmin ? 12 : 11}" class="empty-state">${isArchive ? 'Архив пуст' : 'Логов нет'}</td></tr>`; 
        return; 
    }
    
    // Функция парсинга даты из формата DD.MM или D.MM
    function parseInstallDate(dateStr) {
        if (!dateStr) return new Date(0);
        const parts = dateStr.split('.');
        if (parts.length !== 2) return new Date(0);
        const day = parseInt(parts[0]) || 1;
        const month = parseInt(parts[1]) || 1;
        // Используем текущий год, или предыдущий если месяц больше текущего
        const now = new Date();
        let year = now.getFullYear();
        if (month > now.getMonth() + 1) year--; // Если месяц в будущем, значит это прошлый год
        return new Date(year, month - 1, day);
    }
    
    // Сортировка: закреплённые сверху, затем по дате установки (новые сверху)
    let sortedLogs = [...logs].sort((a, b) => {
        // Закреплённые всегда сверху
        if (a.is_pinned && !b.is_pinned) return -1;
        if (!a.is_pinned && b.is_pinned) return 1;
        
        // Если выбран столбец для сортировки
        if (sortColumn) {
            let valA = a[sortColumn] || '';
            let valB = b[sortColumn] || '';
            
            if (typeof valA === 'string') valA = valA.toLowerCase();
            if (typeof valB === 'string') valB = valB.toLowerCase();
            
            if (valA < valB) return sortDirection === 'asc' ? -1 : 1;
            if (valA > valB) return sortDirection === 'asc' ? 1 : -1;
            return 0;
        }
        
        // По умолчанию: по дате установки (новые сверху)
        const dateA = parseInstallDate(a.install_date);
        const dateB = parseInstallDate(b.install_date);
        return dateB - dateA; // DESC - новые сверху
    });
    
    el.innerHTML = sortedLogs.map(l => `
        <tr class="${selectedLogs.has(l.id) ? 'selected' : ''} ${l.is_archived ? 'archived' : ''} ${l.is_pinned ? 'pinned' : ''} clickable-row" onclick="openLogDetailModal(${l.id}, event)">
            <td onclick="event.stopPropagation()"><input type="checkbox" class="log-checkbox" data-id="${l.id}" ${selectedLogs.has(l.id) ? 'checked' : ''} onchange="toggleLogSelect(${l.id})"></td>
            <td class="cell-mono cell-muted">#${l.id}</td>
            ${isAdmin ? `<td><strong>${esc(l.worker_name)}</strong></td>` : ''}
            <td class="cell-mono">${esc(l.log_number)}</td>
            <td class="cell-mono">${esc(l.balance)}</td>
            <td class="cell-mono cell-profit">${l.profit ? `<span class="profit-badge">+${esc(l.profit)}</span>` : '—'}</td>
            <td class="cell-owner">${l.owner ? `<span class="owner-badge">@${esc(l.owner)}</span>` : '—'}</td>
            <td class="cell-mono cell-muted">${l.install_date||'—'}</td>
            <td class="cell-mono cell-muted">${l.check_date||'—'}</td>
            <td><span class="tag-badge ${l.tag}">${TAG_LABELS[l.tag]||l.tag}</span></td>
            <td onclick="event.stopPropagation()">
                <div class="actions">
                    <button class="action-btn" onclick="openNotesModal(${l.id}, '${esc(l.log_number)}')" title="Заметки">💬</button>
                    <button class="action-btn" onclick="togglePin(${l.id})" title="${l.is_pinned ? 'Открепить' : 'Закрепить'}">${l.is_pinned ? '📌' : '📍'}</button>
                    <button class="action-btn" onclick="duplicateLog(${l.id})" title="Дублировать">📋</button>
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
        <div class="worker-card clickable" onclick="viewWorkerLogs(${w.id}, '${esc(w.name)}')">
            <div class="worker-card-header">
                <span class="worker-card-name">👤 ${esc(w.name)}</span>
                <span class="worker-level">⭐ Ур.${w.level || 1}</span>
                <div class="actions" onclick="event.stopPropagation()">
                    <button class="action-btn" onclick="openWorkerStatsModal(${w.id}, '${esc(w.name)}')" title="Статистика">📊</button>
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
    // Admin-only views
    if ((view === 'workers' || view === 'geelark' || view === 'sbercheck') && currentUser.role !== 'admin') {
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
        reminders: ['Проверки', 'Логи на проверку'],
        geelark: ['Geelark', 'Интеграция с Geelark'],
        sbercheck: ['Проверка Sber', 'Результаты проверки балансов']
    };
    document.getElementById('pageTitle').textContent = titles[view]?.[0] || view;
    document.getElementById('pageSubtitle').textContent = titles[view]?.[1] || '';
    
    document.getElementById(view + 'View').classList.add('active');
    
    if (view === 'dashboard') { loadStats(); loadReminders(7); }
    else if (view === 'logs') { loadLogs(); }
    else if (view === 'workers') { loadWorkers().then(() => renderWorkersGrid()); }
    else if (view === 'reminders') { loadReminders(reminderDays); }
    else if (view === 'geelark') { loadGeelarkSettings(); }
    else if (view === 'sbercheck') { loadSberResults(); }
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
        archived: document.getElementById('filterArchive')?.value || 'false',
        profit_filter: document.getElementById('filterProfit')?.value || ''
    });
}

// Фильтрация по профиту на клиенте (после загрузки)
function filterLogsByProfit(logsArr, profitFilter) {
    if (!profitFilter) return logsArr;
    if (profitFilter === 'with') return logsArr.filter(l => l.profit && l.profit.trim());
    if (profitFilter === 'without') return logsArr.filter(l => !l.profit || !l.profit.trim());
    return logsArr;
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

// ============ PIN & DUPLICATE ============

async function togglePin(id) {
    const result = await api('POST', `/api/logs/${id}/pin`);
    if (result?.ok) {
        showToast(result.is_pinned ? '📌 Закреплено' : '📍 Откреплено');
        loadLogs();
    }
}

async function duplicateLog(id) {
    const result = await api('POST', `/api/logs/${id}/duplicate`);
    if (result?.id) {
        showToast('📋 Лог скопирован!');
        confetti();
        loadLogs();
        loadStats();
    }
}

// ============ NOTES ============

let currentNotesLogId = null;
let currentDetailLogId = null;
let currentDetailLog = null;

// ============ LOG DETAIL MODAL ============

async function openLogDetailModal(logId, event) {
    // Не открывать если клик был на кнопке или чекбоксе
    if (event && (event.target.closest('button') || event.target.closest('input'))) {
        return;
    }
    
    const log = logs.find(l => l.id === logId);
    if (!log) return;
    
    currentDetailLogId = logId;
    currentDetailLog = log;  // Сохраняем лог для редактирования
    
    const content = document.getElementById('logDetailContent');
    const isAdmin = currentUser?.role === 'admin';
    
    content.innerHTML = `
        <div class="log-detail-grid">
            <div class="log-detail-item">
                <label>ID</label>
                <span>#${log.id}</span>
            </div>
            <div class="log-detail-item">
                <label>№ Лога</label>
                <span class="log-detail-value">${esc(log.log_number)}</span>
            </div>
            <div class="log-detail-item">
                <label>Воркер</label>
                <span class="log-detail-value">👤 ${esc(log.worker_name)}</span>
            </div>
            <div class="log-detail-item">
                <label>Баланс</label>
                <span class="log-detail-value balance-highlight">💰 ${esc(log.balance)}</span>
            </div>
            <div class="log-detail-item">
                <label>Профит</label>
                <span class="log-detail-value ${log.profit ? 'profit-highlight' : ''}">${log.profit ? '+' + esc(log.profit) : '—'}</span>
            </div>
            <div class="log-detail-item">
                <label>Владелец</label>
                <span class="log-detail-value">${log.owner ? '@' + esc(log.owner) : '—'}</span>
            </div>
            <div class="log-detail-item">
                <label>Дата установки</label>
                <span class="log-detail-value">📅 ${log.install_date || '—'}</span>
            </div>
            <div class="log-detail-item">
                <label>Дата проверки</label>
                <span class="log-detail-value">🔔 ${log.check_date || '—'}</span>
            </div>
            <div class="log-detail-item">
                <label>Тег</label>
                <span class="tag-badge ${log.tag}">${TAG_LABELS[log.tag] || log.tag}</span>
            </div>
            <div class="log-detail-item">
                <label>Статус</label>
                <span class="log-detail-value">
                    ${log.is_pinned ? '📌 Закреплён' : ''}
                    ${log.is_archived ? '📦 В архиве' : ''}
                    ${!log.is_pinned && !log.is_archived ? '✅ Активен' : ''}
                </span>
            </div>
            ${log.deadline ? `
            <div class="log-detail-item">
                <label>Дедлайн</label>
                <span class="log-detail-value">⏰ ${log.deadline}</span>
            </div>
            ` : ''}
        </div>
        ${log.comment ? `
        <div class="log-detail-comment">
            <label>Комментарий</label>
            <p>${esc(log.comment)}</p>
        </div>
        ` : ''}
        <div class="log-detail-meta">
            Создан: ${formatDate(log.created_at)}
        </div>
    `;
    
    document.getElementById('logDetailModal').classList.add('active');
}

function closeLogDetailModal() {
    document.getElementById('logDetailModal').classList.remove('active');
    currentDetailLogId = null;
    currentDetailLog = null;
}

function editLogFromDetail() {
    if (currentDetailLog) {
        const log = currentDetailLog;
        closeLogDetailModal();
        openLogModal(log);
    }
}

async function openNotesModal(logId, logNumber) {
    currentNotesLogId = logId;
    document.getElementById('notesLogNumber').textContent = `#${logNumber}`;
    document.getElementById('noteText').value = '';
    document.getElementById('notesModal').classList.add('active');
    await loadNotes();
}

function closeNotesModal() {
    document.getElementById('notesModal').classList.remove('active');
    currentNotesLogId = null;
}

async function loadNotes() {
    if (!currentNotesLogId) return;
    const notes = await api('GET', `/api/logs/${currentNotesLogId}/notes`) || [];
    const el = document.getElementById('notesList');
    
    if (!notes.length) {
        el.innerHTML = '<div class="empty-state">Нет заметок</div>';
        return;
    }
    
    el.innerHTML = notes.map(n => `
        <div class="note-item">
            <div class="note-header">
                <span class="note-author">👤 ${esc(n.user_name)}</span>
                <span class="note-date">${formatDate(n.created_at)}</span>
                <button class="action-btn action-btn-sm" onclick="deleteNote(${n.id})">🗑️</button>
            </div>
            <div class="note-text">${esc(n.text)}</div>
        </div>
    `).join('');
}

async function addNote() {
    const text = document.getElementById('noteText').value.trim();
    if (!text) return;
    
    const result = await api('POST', `/api/logs/${currentNotesLogId}/notes`, { text });
    if (result?.ok) {
        document.getElementById('noteText').value = '';
        await loadNotes();
        showToast('💬 Заметка добавлена');
    }
}

async function deleteNote(noteId) {
    if (!confirm('Удалить заметку?')) return;
    const result = await api('DELETE', `/api/notes/${noteId}`);
    if (result?.ok) {
        await loadNotes();
        showToast('🗑️ Заметка удалена');
    }
}

function formatDate(isoDate) {
    if (!isoDate) return '';
    const d = new Date(isoDate);
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

// ============ WORKER STATS MODAL ============

let workerStatsChart = null;

async function openWorkerStatsModal(workerId, workerName) {
    document.getElementById('workerStatsName').textContent = workerName;
    document.getElementById('workerStatsModal').classList.add('active');
    
    const data = await api('GET', `/api/workers/${workerId}/stats`);
    if (!data) return;
    
    // Заполняем статистику
    document.getElementById('wsToday').textContent = data.today_logs;
    document.getElementById('wsWeek').textContent = data.week_logs;
    document.getElementById('wsMonth').textContent = data.month_logs;
    document.getElementById('wsProfit').textContent = data.total_profit;
    
    // Теги
    const tagsEl = document.getElementById('wsTagsGrid');
    const tagColors = { fat: '#ef4444', poor: '#a855f7', medium: '#3b82f6', salary: '#22c55e' };
    const tagNames = { fat: '🔥 Жир', poor: '💸 Нищий', medium: '📊 Средний', salary: '💰 Есть ЗП' };
    tagsEl.innerHTML = Object.entries(data.by_tag || {}).map(([tag, count]) => 
        `<div class="ws-tag" style="border-color: ${tagColors[tag] || '#8b5cf6'}">${tagNames[tag] || tag}: ${count}</div>`
    ).join('') || '<div class="empty-state">Нет логов</div>';
    
    // График
    const ctx = document.getElementById('workerChart').getContext('2d');
    if (workerStatsChart) workerStatsChart.destroy();
    
    workerStatsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.daily_data.map(d => d.date),
            datasets: [{
                label: 'Логов',
                data: data.daily_data.map(d => d.count),
                backgroundColor: 'rgba(139, 92, 246, 0.6)',
                borderColor: '#8b5cf6',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, ticks: { stepSize: 1, color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.1)' } },
                x: { ticks: { color: '#94a3b8' }, grid: { display: false } }
            }
        }
    });
}

function closeWorkerStatsModal() {
    document.getElementById('workerStatsModal').classList.remove('active');
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

// ============ GEELARK INTEGRATION ============

let geelarkSettings = null;
let geelarkMappings = [];

async function loadGeelarkSettings() {
    const data = await api('GET', '/api/geelark/settings');
    if (data) {
        geelarkSettings = data;
        
        // Update UI
        if (data.configured) {
            document.getElementById('geelarkToken').value = '••••••••••••••••••';
            document.getElementById('geelarkDefaultWorker').value = data.default_worker_id || '';
            document.getElementById('geelarkAutoSync').checked = data.auto_sync_enabled || false;
            
            if (data.last_sync_at) {
                document.getElementById('geelarkLastSync').textContent = `Последняя синхронизация: ${formatDate(data.last_sync_at)}`;
            }
            
            // Test connection on load
            testGeelarkConnection();
        }
    }
    
    // Load mappings
    await loadGeelarkMappings();
}

async function loadGeelarkMappings() {
    const data = await api('GET', '/api/geelark/groups');
    if (data?.mappings) {
        geelarkMappings = data.mappings;
        renderGeelarkMappings();
    }
}

function renderGeelarkMappings() {
    const el = document.getElementById('geelarkMappings');
    if (!geelarkMappings.length) {
        el.innerHTML = '<div class="empty-state">Нет маппингов. Добавьте связь группы Geelark с воркером.</div>';
        return;
    }
    
    el.innerHTML = geelarkMappings.map(m => `
        <div class="geelark-mapping-item">
            <div class="geelark-mapping-group">
                <span class="geelark-mapping-group-name">${esc(m.geelark_group_name || 'Без названия')}</span>
                <span class="geelark-mapping-group-id">${esc(m.geelark_group_id)}</span>
            </div>
            <div class="geelark-mapping-worker">
                <span>→</span>
                <span>👤 ${esc(m.worker_name)}</span>
            </div>
            <button class="action-btn" onclick="deleteGeelarkMapping(${m.id})">🗑️</button>
        </div>
    `).join('');
}

async function saveGeelarkSettings() {
    const token = document.getElementById('geelarkToken').value;
    const defaultWorker = document.getElementById('geelarkDefaultWorker').value;
    const autoSync = document.getElementById('geelarkAutoSync').checked;
    
    // Don't send masked token
    const data = {
        default_worker_id: defaultWorker ? parseInt(defaultWorker) : null,
        auto_sync_enabled: autoSync
    };
    
    // Only send token if it's not masked
    if (token && !token.includes('•')) {
        data.bearer_token = token;
    }
    
    const result = await api('POST', '/api/geelark/settings', data);
    if (result?.ok) {
        showToast('✅ Настройки сохранены!');
        loadGeelarkSettings();
    } else {
        showToast('❌ Ошибка сохранения', 'error');
    }
}

async function testGeelarkConnection() {
    const result = await api('GET', '/api/geelark/test');
    const statusDot = document.querySelector('.geelark-status-dot');
    const statusText = document.getElementById('geelarkStatusText');
    
    if (result?.ok) {
        statusDot.classList.remove('not-connected');
        statusDot.classList.add('connected');
        statusText.textContent = result.message;
        showToast('✅ ' + result.message);
    } else {
        statusDot.classList.remove('connected');
        statusDot.classList.add('not-connected');
        statusText.textContent = result?.error || 'Ошибка подключения';
        showToast('❌ ' + (result?.error || 'Ошибка подключения'), 'error');
    }
}

async function syncGeelark() {
    showToast('🔄 Синхронизация...');
    
    const result = await api('POST', '/api/geelark/sync');
    
    if (result?.ok) {
        showToast(`✅ Импортировано: ${result.imported}, пропущено: ${result.skipped}`);
        showConfetti();
        
        // Update stats
        let errorsHtml = '';
        if (result.errors?.length) {
            errorsHtml = `<br>❌ Ошибок: ${result.errors.length}<br><div style="margin-top:10px;padding:10px;background:rgba(239,68,68,0.2);border-radius:8px;font-size:12px;max-height:150px;overflow-y:auto;">`;
            errorsHtml += result.errors.map(e => `• ${e}`).join('<br>');
            errorsHtml += '</div>';
        }
        
        document.getElementById('geelarkSyncStats').innerHTML = `
            📊 Всего телефонов: ${result.total_phones}<br>
            ✅ Импортировано: ${result.imported}<br>
            ⏭️ Пропущено: ${result.skipped}
            ${result.archived ? `<br>📦 Архивировано: ${result.archived}` : ''}
            ${errorsHtml}
        `;
        
        document.getElementById('geelarkLastSync').textContent = 'Последняя синхронизация: сейчас';
        
        // Show new groups
        if (result.new_groups?.length) {
            showToast(`⚠️ Найдено ${result.new_groups.length} новых групп. Добавьте маппинги!`);
        }
        
        // Reload logs
        loadLogs();
        loadStats();
    } else {
        showToast('❌ Ошибка синхронизации', 'error');
    }
}

async function fetchGeelarkGroups() {
    showToast('📥 Загрузка групп...');
    
    const result = await api('GET', '/api/geelark/fetch-groups');
    
    if (result?.ok && result.groups) {
        // Show groups for mapping
        const groups = result.groups;
        
        if (!groups.length) {
            showToast('Группы не найдены', 'error');
            return;
        }
        
        // Create a selection dialog
        const existingIds = new Set(geelarkMappings.map(m => m.geelark_group_id));
        
        let html = '<div class="geelark-groups-list">';
        
        for (const g of groups) {
            const isMapped = existingIds.has(g.id);
            html += `
                <div class="geelark-group-item ${isMapped ? 'mapped' : ''}" onclick="selectGroupForMapping('${esc(g.id)}', '${esc(g.name)}')">
                    <div class="geelark-group-info">
                        <span class="geelark-group-name">${esc(g.name)}</span>
                        <span class="geelark-group-phones">${g.phones_count} телефонов</span>
                    </div>
                    ${isMapped ? '<span title="Уже привязано">✅</span>' : '<span title="Нажмите для привязки">➕</span>'}
                </div>
            `;
        }
        
        html += '</div>';
        
        // Insert after mappings
        const mappingsEl = document.getElementById('geelarkMappings');
        mappingsEl.insertAdjacentHTML('afterend', html);
        
        showToast(`✅ Найдено ${groups.length} групп`);
    } else {
        showToast('❌ Ошибка загрузки групп', 'error');
    }
}

function selectGroupForMapping(groupId, groupName) {
    document.getElementById('newMappingGroupId').value = groupId;
    document.getElementById('newMappingGroupName').value = groupName;
    
    // Remove the groups list
    document.querySelector('.geelark-groups-list')?.remove();
    
    // Focus worker select
    document.getElementById('newMappingWorker').focus();
}

async function addGeelarkMapping() {
    const groupId = document.getElementById('newMappingGroupId').value.trim();
    const groupName = document.getElementById('newMappingGroupName').value.trim();
    const workerId = document.getElementById('newMappingWorker').value;
    
    if (!groupId || !workerId) {
        showToast('Укажите ID группы и воркера', 'error');
        return;
    }
    
    const result = await api('POST', '/api/geelark/groups/mapping', {
        geelark_group_id: groupId,
        geelark_group_name: groupName,
        worker_id: parseInt(workerId)
    });
    
    if (result?.ok) {
        showToast('✅ Маппинг добавлен!');
        document.getElementById('newMappingGroupId').value = '';
        document.getElementById('newMappingGroupName').value = '';
        document.getElementById('newMappingWorker').value = '';
        loadGeelarkMappings();
    } else {
        showToast('❌ Ошибка добавления', 'error');
    }
}

async function deleteGeelarkMapping(id) {
    if (!confirm('Удалить маппинг?')) return;
    
    const result = await api('DELETE', `/api/geelark/groups/mapping/${id}`);
    if (result?.ok) {
        showToast('🗑️ Маппинг удалён');
        loadGeelarkMappings();
    }
}

function updateGeelarkWorkerSelects() {
    const opts = workers.map(w => `<option value="${w.id}">${esc(w.name)}</option>`).join('');
    
    const defaultWorkerSelect = document.getElementById('geelarkDefaultWorker');
    if (defaultWorkerSelect) {
        defaultWorkerSelect.innerHTML = '<option value="">Выберите воркера</option>' + opts;
    }
    
    const newMappingWorkerSelect = document.getElementById('newMappingWorker');
    if (newMappingWorkerSelect) {
        newMappingWorkerSelect.innerHTML = '<option value="">Воркер</option>' + opts;
    }
}


// ============ SBER CHECK ============

let sberCheckInterval = null;

async function startSberCheck() {
    const selected = Array.from(document.querySelectorAll('.log-checkbox:checked'))
        .map(cb => parseInt(cb.dataset.id));
    
    if (selected.length === 0) {
        showToast('Выберите логи для проверки', 'error');
        return;
    }
    
    if (!confirm(`Запустить проверку ${selected.length} логов?\n\nЭто может занять несколько минут.`)) {
        return;
    }
    
    showToast(`🚀 Запуск проверки ${selected.length} логов...`);
    
    const result = await api('POST', '/api/sber-check/start', selected);
    
    if (result?.ok) {
        showToast('✅ Проверка запущена!');
        clearSelection();
        switchView('sbercheck');
        startSberStatusPolling();
    } else {
        showToast('❌ ' + (result?.detail || 'Ошибка запуска'), 'error');
    }
}

function startSberStatusPolling() {
    // Clear existing interval
    if (sberCheckInterval) clearInterval(sberCheckInterval);
    
    // Show progress
    document.getElementById('sberCheckProgress').style.display = 'block';
    document.getElementById('sberCheckStatus').innerHTML = `
        <div class="sber-status-running">
            <div class="spinner"></div>
            <div>
                <strong>Проверка выполняется...</strong>
                <p style="margin:5px 0 0;color:var(--text-muted)">Не закрывайте страницу</p>
            </div>
        </div>
    `;
    
    // Poll status
    sberCheckInterval = setInterval(async () => {
        const status = await api('GET', '/api/sber-check/status');
        
        if (status) {
            const progress = status.total > 0 ? (status.progress / status.total) * 100 : 0;
            document.getElementById('sberProgressFill').style.width = progress + '%';
            document.getElementById('sberProgressText').textContent = `${status.progress} / ${status.total}`;
            document.getElementById('sberProgressCurrent').textContent = status.current || '';
            
            if (!status.running) {
                clearInterval(sberCheckInterval);
                sberCheckInterval = null;
                
                document.getElementById('sberCheckStatus').innerHTML = `
                    <div class="sber-status-idle">
                        <span>✅</span>
                        <p>Проверка завершена</p>
                    </div>
                `;
                
                showToast('✅ Проверка завершена!');
                showConfetti();
                loadSberResults();
            }
        }
    }, 3000);
    
    // Also load results periodically
    loadSberResults();
}

async function loadSberResults() {
    const data = await api('GET', '/api/sber-check/results');
    
    if (!data) return;
    
    // Update status if check is active
    if (data.active?.running) {
        startSberStatusPolling();
    }
    
    const results = data.results || [];
    
    // Summary
    const success = results.filter(r => r.status === 'success').length;
    const errors = results.filter(r => r.status === 'error').length;
    const skipped = results.filter(r => r.status === 'skipped').length;
    
    document.getElementById('sberResultsSummary').innerHTML = results.length > 0 ? `
        <div class="sber-summary-item success">✅ Успешно: ${success}</div>
        <div class="sber-summary-item error">❌ Ошибки: ${errors}</div>
        <div class="sber-summary-item skipped">⏭️ Пропущено: ${skipped}</div>
    ` : '';
    
    // Results grid
    const grid = document.getElementById('sberResultsGrid');
    
    if (results.length === 0) {
        grid.innerHTML = '<div class="empty-state">Нет результатов</div>';
        return;
    }
    
    grid.innerHTML = results.map(r => `
        <div class="sber-result-item ${r.status}">
            <div class="sber-result-header">
                <span class="sber-result-phone">#${esc(r.phone_serial || '?')} - ${esc(r.phone_name || 'N/A')}</span>
                <span class="sber-result-status ${r.status}">
                    ${r.status === 'success' ? '✅' : r.status === 'error' ? '❌' : '⏭️'}
                    ${r.status === 'success' ? 'Успешно' : r.status === 'error' ? 'Ошибка' : 'Пропущено'}
                </span>
            </div>
            <div class="sber-result-body">
                <div class="sber-result-info">
                    <span>📋 Лог: ${esc(r.log_number || 'N/A')}</span>
                    <span>🕐 ${formatDate(r.checked_at)}</span>
                </div>
                ${r.error_message ? `<div class="sber-result-error">${esc(r.error_message)}</div>` : ''}
                ${r.screenshot_url ? `
                    <div class="sber-result-screenshot">
                        <img src="${r.screenshot_url}" alt="Screenshot" onclick="openScreenshot(this.src)">
                    </div>
                ` : ''}
            </div>
        </div>
    `).join('');
}

async function refreshSberResults() {
    showToast('🔄 Обновление...');
    await loadSberResults();
    showToast('✅ Обновлено');
}

async function clearSberResults() {
    if (!confirm('Очистить все результаты проверки?')) return;
    
    const result = await api('DELETE', '/api/sber-check/results');
    
    if (result?.ok) {
        showToast('🗑️ Результаты очищены');
        document.getElementById('sberResultsGrid').innerHTML = '<div class="empty-state">Нет результатов</div>';
        document.getElementById('sberResultsSummary').innerHTML = '';
        document.getElementById('sberCheckProgress').style.display = 'none';
        document.getElementById('sberCheckStatus').innerHTML = `
            <div class="sber-status-idle">
                <span>⏸️</span>
                <p>Выберите логи во вкладке "Все логи" и нажмите "Проверить Sber"</p>
            </div>
        `;
    }
}

function openScreenshot(src) {
    // Open screenshot in new window/tab
    const win = window.open('', '_blank');
    win.document.write(`
        <html>
        <head><title>Screenshot</title></head>
        <body style="margin:0;background:#000;display:flex;align-items:center;justify-content:center;min-height:100vh">
            <img src="${src}" style="max-width:100%;max-height:100vh">
        </body>
        </html>
    `);
}


// Init
document.addEventListener('DOMContentLoaded', async () => {
    // Theme
    initTheme();
    
    // Check for token in URL (from Telegram Web App)
    const urlParams = new URLSearchParams(window.location.search);
    const tokenFromUrl = urlParams.get('token');
    if (tokenFromUrl) {
        authToken = tokenFromUrl;
        localStorage.setItem('token', authToken);
        // Clear token from URL
        window.history.replaceState({}, document.title, window.location.pathname);
    }
    
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
    document.getElementById('filterProfit')?.addEventListener('change', applyFilters);
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
