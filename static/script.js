// 配置
const CONFIG = {
    refreshInterval: 2000, // 2秒
    apiEndpoints: {
        providers: '/providers',
        capacity: '/capacity',
        refresh: '/refresh'
    }
};

// 状态
const state = {
    providers: [],
    capacityData: {},
    autoRefresh: true,
    refreshTimer: null,
    lastUpdated: null,
    apiKey: localStorage.getItem('how2use_api_key') || ''
};

// DOM 元素
const elements = {
    providersContainer: document.getElementById('providers-container'),
    loading: document.getElementById('loading'),
    error: document.getElementById('error'),
    errorMessage: document.querySelector('.error-message'),
    refreshBtn: document.getElementById('refresh-btn'),
    autoRefreshToggle: document.getElementById('auto-refresh'),
    lastUpdated: document.getElementById('last-updated'),
    apiKeyInput: document.getElementById('api-key')
};

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    // 设置 API 密钥输入框
    elements.apiKeyInput.value = state.apiKey;
    elements.apiKeyInput.addEventListener('input', (e) => {
        state.apiKey = e.target.value;
        localStorage.setItem('how2use_api_key', state.apiKey);
    });

    // 设置自动刷新开关
    elements.autoRefreshToggle.checked = state.autoRefresh;
    elements.autoRefreshToggle.addEventListener('change', (e) => {
        state.autoRefresh = e.target.checked;
        if (state.autoRefresh) {
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });

    // 设置刷新按钮
    elements.refreshBtn.addEventListener('click', handleManualRefresh);

    // 设置重试按钮
    document.querySelector('.retry-btn').addEventListener('click', () => {
        hideError();
        initialize();
    });

    // 初始化
    initialize();
});

// 初始化函数
async function initialize() {
    showLoading();
    try {
        await fetchProviders();
        await fetchCapacity();
        hideLoading();
        if (state.autoRefresh) {
            startAutoRefresh();
        }
    } catch (err) {
        hideLoading();
        showError(`初始化失败: ${err.message}`);
    }
}

// 获取 provider 列表
async function fetchProviders() {
    const response = await fetch(CONFIG.apiEndpoints.providers, {
        headers: getHeaders()
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    state.providers = data.providers || [];
}

// 获取容量数据
async function fetchCapacity() {
    const response = await fetch(CONFIG.apiEndpoints.capacity, {
        headers: getHeaders()
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    state.capacityData = data;
    state.lastUpdated = new Date(data.fetched_at);
    renderProviders();
    updateLastUpdated();
}

// 渲染 providers
function renderProviders() {
    if (!state.capacityData.providers || state.capacityData.providers.length === 0) {
        elements.providersContainer.innerHTML = '<div class="empty-state">暂无 provider 数据</div>';
        return;
    }

    // 按 provider 分组
    const grouped = {};
    state.capacityData.providers.forEach(pool => {
        if (!grouped[pool.provider]) {
            grouped[pool.provider] = [];
        }
        grouped[pool.provider].push(pool);
    });

    let html = '';
    for (const [provider, pools] of Object.entries(grouped)) {
        html += renderProviderCard(provider, pools);
    }
    elements.providersContainer.innerHTML = html;

    // 添加展开/折叠事件
    document.querySelectorAll('.card-header').forEach(header => {
        header.addEventListener('click', () => {
            const details = header.nextElementSibling;
            details.classList.toggle('expanded');
        });
    });
}

// 渲染单个 provider 卡片
function renderProviderCard(provider, pools) {
    let poolsHtml = '';
    pools.forEach(pool => {
        poolsHtml += renderPool(pool);
    });

    return `
        <div class="provider-card">
            <div class="card-header">
                <div class="provider-info">
                    <span class="provider-name">${escapeHtml(provider)}</span>
                </div>
            </div>
            ${poolsHtml}
        </div>
    `;
}

// 渲染单个 pool
function renderPool(pool) {
    const healthClass = pool.healthy ? 'healthy' : 'unhealthy';
    const healthText = pool.healthy ? '健康' : '不健康';

    // 确定显示的指标
    const metrics = [];
    if (pool.accounts_total !== undefined) {
        metrics.push({
            value: pool.accounts_total,
            label: '账号总数'
        });
    }
    if (pool.accounts_active !== undefined) {
        metrics.push({
            value: pool.accounts_active,
            label: '活跃账号'
        });
    }
    if (pool.concurrency_total !== undefined && pool.concurrency_total > 0) {
        metrics.push({
            value: `${pool.concurrency_used || 0}/${pool.concurrency_total}`,
            label: '并发使用'
        });
    }
    if (pool.rpm_limit !== undefined && pool.rpm_limit !== null) {
        metrics.push({
            value: `${pool.rpm_used || 0}/${pool.rpm_limit}`,
            label: 'RPM 使用'
        });
    }
    if (pool.quota_remaining !== undefined && pool.quota_remaining !== null) {
        metrics.push({
            value: formatQuota(pool.quota_remaining),
            label: '剩余额度'
        });
    }

    let metricsHtml = '';
    metrics.forEach(metric => {
        metricsHtml += `
            <div class="metric">
                <div class="metric-value">${escapeHtml(String(metric.value))}</div>
                <div class="metric-label">${escapeHtml(metric.label)}</div>
            </div>
        `;
    });

    // 账号详情表格
    let accountsHtml = '';
    if (pool.accounts && pool.accounts.length > 0) {
        let tableRows = '';
        pool.accounts.forEach(account => {
            const statusClass = `status-${account.status}`;
            tableRows += `
                <tr>
                    <td>${escapeHtml(account.id)}</td>
                    <td class="${statusClass}">${escapeHtml(account.status)}</td>
                    <td>${account.rpm_limit || '-'}</td>
                    <td>${account.quota_remaining !== null ? formatQuota(account.quota_remaining) : '-'}</td>
                </tr>
            `;
        });

        accountsHtml = `
            <div class="details">
                <div class="details-content">
                    <table class="accounts-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>状态</th>
                                <th>RPM 限制</th>
                                <th>剩余额度</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${tableRows}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    return `
        <div class="card-header">
            <div class="provider-info">
                <span class="pool-name">${escapeHtml(pool.pool_name || '默认')}</span>
            </div>
            <div class="health-status ${healthClass}">
                <span class="health-dot"></span>
                <span>${healthText}</span>
            </div>
        </div>
        <div class="card-content">
            <div class="metrics-grid">
                ${metricsHtml}
            </div>
        </div>
        ${accountsHtml}
    `;
}

// 手动刷新
async function handleManualRefresh() {
    const btn = elements.refreshBtn;
    btn.disabled = true;
    btn.textContent = '刷新中...';

    try {
        // 调用 refresh 端点
        const refreshResponse = await fetch(CONFIG.apiEndpoints.refresh, {
            method: 'POST',
            headers: getHeaders()
        });

        if (!refreshResponse.ok) {
            throw new Error(`刷新失败: HTTP ${refreshResponse.status}`);
        }

        // 重新获取数据
        await fetchCapacity();
    } catch (err) {
        showError(`刷新失败: ${err.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = '刷新';
    }
}

// 自动刷新控制
function startAutoRefresh() {
    stopAutoRefresh();
    state.refreshTimer = setInterval(async () => {
        try {
            await fetchCapacity();
        } catch (err) {
            console.error('自动刷新失败:', err);
            // 不显示错误，避免干扰
        }
    }, CONFIG.refreshInterval);
}

function stopAutoRefresh() {
    if (state.refreshTimer) {
        clearInterval(state.refreshTimer);
        state.refreshTimer = null;
    }
}

// 工具函数
function getHeaders() {
    const headers = {
        'Content-Type': 'application/json'
    };
    if (state.apiKey) {
        headers['X-API-Key'] = state.apiKey;
    }
    return headers;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatQuota(quota) {
    if (quota === null || quota === undefined) return '-';
    if (quota >= 1000000) {
        return (quota / 1000000).toFixed(1) + 'M';
    }
    if (quota >= 1000) {
        return (quota / 1000).toFixed(1) + 'K';
    }
    return quota.toFixed(2);
}

function updateLastUpdated() {
    if (state.lastUpdated) {
        const timeStr = state.lastUpdated.toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        elements.lastUpdated.textContent = `最后更新: ${timeStr}`;
    }
}

// UI 状态控制
function showLoading() {
    elements.loading.style.display = 'flex';
    elements.providersContainer.style.display = 'none';
    elements.error.style.display = 'none';
}

function hideLoading() {
    elements.loading.style.display = 'none';
    elements.providersContainer.style.display = 'grid';
}

function showError(message) {
    elements.errorMessage.textContent = message;
    elements.error.style.display = 'block';
    elements.providersContainer.style.display = 'none';
}

function hideError() {
    elements.error.style.display = 'none';
    elements.providersContainer.style.display = 'grid';
}