/**
 * 重生模拟器 - 前端交互逻辑
 */

(function() {
    'use strict';

    // 获取基础路径
    const BASE = window.location.pathname.endsWith('/')
        ? window.location.pathname
        : window.location.pathname + '/';

    // DOM 元素
    const screens = {
        start: document.getElementById('start-screen'),
        loading: document.getElementById('loading-screen'),
        result: document.getElementById('result-screen'),
        history: document.getElementById('history-screen')
    };

    const buttons = {
        start: document.getElementById('btn-start'),
        again: document.getElementById('btn-again'),
        history: document.getElementById('btn-history'),
        back: document.getElementById('btn-back'),
        clearHistory: document.getElementById('btn-clear-history')
    };

    const resultElements = {
        flag: document.getElementById('country-flag'),
        name: document.getElementById('country-name'),
        nameEn: document.getElementById('country-name-en'),
        description: document.getElementById('country-description'),
        traits: document.getElementById('traits-container'),
        funFact: document.getElementById('fun-fact'),
        probabilityFill: document.getElementById('probability-fill'),
        probabilityText: document.getElementById('probability-text'),
        probabilityNote: document.getElementById('probability-note')
    };

    // 历史记录存储
    const STORAGE_KEY = 'reincarnation_history';
    let history = loadHistory();

    // 工具函数
    function api(endpoint) {
        return BASE + 'api/' + endpoint;
    }

    function switchScreen(targetScreen) {
        Object.values(screens).forEach(screen => {
            screen.classList.remove('active');
        });
        screens[targetScreen].classList.add('active');
    }

    function loadHistory() {
        try {
            const data = localStorage.getItem(STORAGE_KEY);
            return data ? JSON.parse(data) : [];
        } catch (e) {
            console.error('Failed to load history:', e);
            return [];
        }
    }

    function saveHistory() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
        } catch (e) {
            console.error('Failed to save history:', e);
        }
    }

    function addToHistory(countryData) {
        const entry = {
            ...countryData,
            timestamp: Date.now(),
            date: new Date().toLocaleString('zh-CN')
        };
        history.unshift(entry);

        // 最多保存50条记录
        if (history.length > 50) {
            history = history.slice(0, 50);
        }

        saveHistory();
    }

    function clearHistory() {
        if (confirm('确定要清空所有转世记录吗？')) {
            history = [];
            saveHistory();
            renderHistory();
        }
    }

    // API 调用
    async function reincarnate() {
        try {
            const response = await fetch(api('reincarnate'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const data = await response.json();

            if (data.ok) {
                return data.result;
            } else {
                throw new Error(data.error || 'Unknown error');
            }
        } catch (error) {
            console.error('Reincarnation failed:', error);
            alert('重生失败，请稍后再试！');
            return null;
        }
    }

    // 显示结果
    function displayResult(countryData) {
        // 更新国旗和国家名
        resultElements.flag.textContent = countryData.flag;
        resultElements.name.textContent = countryData.country;
        resultElements.nameEn.textContent = countryData.country_en;

        // 更新描述
        resultElements.description.textContent = countryData.description;

        // 更新特征标签
        resultElements.traits.innerHTML = '';
        countryData.traits.forEach(trait => {
            const tag = document.createElement('span');
            tag.className = 'trait-tag';
            tag.textContent = trait;
            resultElements.traits.appendChild(tag);
        });

        // 更新趣味知识
        resultElements.funFact.textContent = countryData.fun_fact;

        // 更新概率信息
        const probability = countryData.probability.toFixed(2);
        resultElements.probabilityFill.style.width = `${Math.min(probability * 10, 100)}%`;
        resultElements.probabilityText.textContent = `出生概率: ${probability}%`;
        resultElements.probabilityNote.textContent = countryData.probability_note;

        // 添加动画效果
        const card = document.querySelector('.country-card');
        card.classList.remove('fade-in');
        void card.offsetWidth; // 触发重排
        card.classList.add('fade-in');
    }

    // 渲染历史记录
    function renderHistory() {
        const historyList = document.getElementById('history-list');
        const historyStats = document.getElementById('history-stats');

        if (history.length === 0) {
            historyList.innerHTML = `
                <div class="empty-history">
                    <div class="empty-icon">🌱</div>
                    <p>还没有转世记录</p>
                    <p class="empty-hint">开始第一次重生吧！</p>
                </div>
            `;
            historyStats.innerHTML = '';
            return;
        }

        // 渲染历史列表
        historyList.innerHTML = history.map((entry, index) => `
            <div class="history-item">
                <div class="history-rank">#${index + 1}</div>
                <div class="history-flag">${entry.flag}</div>
                <div class="history-info">
                    <div class="history-country">
                        ${entry.country}
                        <span class="history-country-en">${entry.country_en}</span>
                    </div>
                    <div class="history-description">${entry.description}</div>
                    <div class="history-meta">
                        <span class="history-time">⏰ ${entry.date}</span>
                        <span class="history-probability">📊 ${entry.probability.toFixed(2)}%</span>
                    </div>
                </div>
            </div>
        `).join('');

        // 计算统计信息
        const countryCount = {};
        history.forEach(entry => {
            countryCount[entry.country] = (countryCount[entry.country] || 0) + 1;
        });

        const sortedCountries = Object.entries(countryCount)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5);

        const totalReincarnations = history.length;

        historyStats.innerHTML = `
            <div class="stats-header">📊 统计信息</div>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">${totalReincarnations}</div>
                    <div class="stat-label">总转世次数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${Object.keys(countryCount).length}</div>
                    <div class="stat-label">体验过的国家</div>
                </div>
            </div>
            ${sortedCountries.length > 0 ? `
                <div class="top-countries">
                    <div class="top-countries-title">🏆 最常转世的地方</div>
                    ${sortedCountries.map(([country, count]) => {
                        const entry = history.find(h => h.country === country);
                        return `
                            <div class="top-country-item">
                                <span class="top-country-flag">${entry.flag}</span>
                                <span class="top-country-name">${country}</span>
                                <span class="top-country-count">${count}次</span>
                            </div>
                        `;
                    }).join('')}
                </div>
            ` : ''}
        `;
    }

    // 开始重生流程
    async function startReincarnation() {
        // 切换到加载界面
        switchScreen('loading');

        // 模拟加载过程（增加悬念）
        await new Promise(resolve => setTimeout(resolve, 2000));

        // 调用 API
        const countryData = await reincarnate();

        if (countryData) {
            // 显示结果
            displayResult(countryData);
            addToHistory(countryData);

            // 切换到结果界面
            switchScreen('result');
        } else {
            // 失败，返回开始界面
            switchScreen('start');
        }
    }

    // 事件监听器
    buttons.start.addEventListener('click', startReincarnation);
    buttons.again.addEventListener('click', startReincarnation);

    buttons.history.addEventListener('click', () => {
        renderHistory();
        switchScreen('history');
    });

    buttons.back.addEventListener('click', () => {
        switchScreen('result');
    });

    buttons.clearHistory.addEventListener('click', clearHistory);

    // 键盘快捷键
    document.addEventListener('keydown', (e) => {
        // 按空格键重新开始
        if (e.code === 'Space' && screens.result.classList.contains('active')) {
            e.preventDefault();
            startReincarnation();
        }
        // 按 H 键查看历史
        if (e.code === 'KeyH' && screens.result.classList.contains('active')) {
            e.preventDefault();
            buttons.history.click();
        }
        // 按 ESC 返回
        if (e.code === 'Escape' && screens.history.classList.contains('active')) {
            e.preventDefault();
            buttons.back.click();
        }
    });

    // 页面加载完成
    console.log('🌍 重生模拟器已加载');
    console.log('💡 提示: 在结果页面按空格键可快速重新转世');
})();
