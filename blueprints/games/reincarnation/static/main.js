/**
 * 重生模拟器 V2 - 现代化交互逻辑
 * 包含地图可视化和增强的用户体验
 */

(function() {
    'use strict';

    // =============== 配置和常量 ===============
    const BASE = window.location.pathname.endsWith('/')
        ? window.location.pathname
        : window.location.pathname + '/';

    const STORAGE_KEY = 'reincarnation_history_v2';
    const ANIMATION_DURATION = 2500;

    // =============== DOM 元素 ===============
    const sections = {
        start: document.getElementById('start-section'),
        loading: document.getElementById('loading-section'),
        result: document.getElementById('result-section'),
        history: document.getElementById('history-section')
    };

    const buttons = {
        startJourney: document.getElementById('btn-start-journey'),
        reincarnate: document.getElementById('btn-reincarnate'),
        viewHistory: document.getElementById('btn-view-history'),
        share: document.getElementById('btn-share'),
        backToResult: document.getElementById('btn-back-to-result'),
        clearHistory: document.getElementById('btn-clear-history')
    };

    // =============== 状态管理 ===============
    let currentCountry = null;
    let history = loadHistory();

    // =============== 工具函数 ===============
    function api(endpoint) {
        return BASE + 'api/' + endpoint;
    }

    function switchSection(targetSection) {
        Object.values(sections).forEach(section => {
            section.classList.remove('active');
        });
        sections[targetSection].classList.add('active');
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
        if (history.length > 50) {
            history = history.slice(0, 50);
        }
        saveHistory();
    }

    // =============== 地图可视化 ===============
    function createWorldMap() {
        const mapContainer = document.getElementById('world-map');
        mapContainer.innerHTML = `
            <svg width="100%" height="100%" viewBox="0 0 800 400" preserveAspectRatio="xMidYMid meet">
                <defs>
                    <radialGradient id="mapGlow" cx="50%" cy="50%">
                        <stop offset="0%" stop-color="rgba(99,102,241,0.3)"/>
                        <stop offset="100%" stop-color="rgba(99,102,241,0)"/>
                    </radialGradient>
                </defs>
                <rect width="800" height="400" fill="url(#mapGlow)" opacity="0.3"/>
                <g id="map-continents">
                    <!-- 大陆将通过CSS显示 -->
                </g>
            </svg>
        `;
    }

    function updateMapMarker(coordinates) {
        const marker = document.getElementById('location-marker');
        // 将经纬度转换为地图坐标
        // 简化的墨卡托投影
        const x = ((coordinates.lng + 180) / 360) * 100;
        const y = ((90 - coordinates.lat) / 180) * 100;
        
        marker.style.left = x + '%';
        marker.style.top = y + '%';
        marker.style.display = 'block';
        
        // 触发动画
        marker.classList.remove('animate');
        void marker.offsetWidth; // 强制重排
        marker.classList.add('animate');
    }

    // =============== 粒子效果 ===============
    function createParticles() {
        const particlesContainer = document.getElementById('particles');
        const particleCount = 30;
        
        for (let i = 0; i < particleCount; i++) {
            const particle = document.createElement('div');
            particle.className = 'particle';
            particle.style.left = Math.random() * 100 + '%';
            particle.style.top = Math.random() * 100 + '%';
            particle.style.animationDelay = Math.random() * 20 + 's';
            particle.style.animationDuration = (20 + Math.random() * 10) + 's';
            particlesContainer.appendChild(particle);
        }
    }

    // =============== API 调用 ===============
    async function reincarnate() {
        try {
            const response = await fetch(api('reincarnate'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) throw new Error('Network response was not ok');

            const data = await response.json();
            if (data.ok) {
                return data.result;
            } else {
                throw new Error(data.error || 'Unknown error');
            }
        } catch (error) {
            console.error('Reincarnation failed:', error);
            alert('😢 重生失败，请稍后再试！');
            return null;
        }
    }

    // =============== 结果展示 ===============
    function displayResult(countryData) {
        currentCountry = countryData;

        // 更新基本信息
        document.getElementById('result-flag').textContent = countryData.flag;
        document.getElementById('result-country').textContent = countryData.country;
        document.getElementById('result-country-en').textContent = countryData.country_en;
        document.getElementById('continent-badge').textContent = countryData.continent;

        // 更新描述
        document.getElementById('result-description').textContent = countryData.description;
        document.getElementById('result-lifestyle').textContent = countryData.lifestyle;

        // 更新特征标签
        const traitsContainer = document.getElementById('result-traits');
        traitsContainer.innerHTML = countryData.traits.map(trait => 
            `<div class="trait-tag">${trait}</div>`
        ).join('');

        // 更新统计
        document.getElementById('result-probability').textContent = 
            countryData.probability.toFixed(2) + '%';
        document.getElementById('result-life-expectancy').textContent = 
            countryData.life_expectancy;

        // 更新趣味知识
        document.getElementById('result-fun-fact').textContent = countryData.fun_fact;

        // 更新著名特色
        const famousContainer = document.getElementById('result-famous');
        famousContainer.innerHTML = countryData.famous_for.map(item =>
            `<div class="famous-item">✨ ${item}</div>`
        ).join('');

        // 更新地图标记
        updateMapMarker(countryData.coordinates);

        // 添加到历史
        addToHistory(countryData);
    }

    // =============== 历史记录 ===============
    function renderHistory() {
        const historyList = document.getElementById('history-list');
        const historyStats = document.getElementById('history-stats');

        if (history.length === 0) {
            historyList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">🌱</div>
                    <h3>还没有转世记录</h3>
                    <p>开始你的第一次重生之旅吧！</p>
                </div>
            `;
            historyStats.innerHTML = '';
            return;
        }

        // 渲染历史列表
        historyList.innerHTML = history.map((entry, index) => `
            <div class="history-item glass-card">
                <div class="history-number">#${index + 1}</div>
                <div class="history-flag">${entry.flag}</div>
                <div class="history-content">
                    <div class="history-title">
                        <span class="history-country">${entry.country}</span>
                        <span class="history-continent">${entry.continent}</span>
                    </div>
                    <div class="history-desc">${entry.description}</div>
                    <div class="history-meta">
                        <span>🎲 ${entry.probability.toFixed(2)}%</span>
                        <span>⏰ ${entry.life_expectancy}</span>
                        <span>📅 ${entry.date}</span>
                    </div>
                </div>
            </div>
        `).join('');

        // 计算统计
        const countryCount = {};
        const continentCount = {};
        history.forEach(entry => {
            countryCount[entry.country] = (countryCount[entry.country] || 0) + 1;
            continentCount[entry.continent] = (continentCount[entry.continent] || 0) + 1;
        });

        const topCountries = Object.entries(countryCount)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3);

        historyStats.innerHTML = `
            <div class="stats-grid">
                <div class="history-stat-card">
                    <div class="stat-number">${history.length}</div>
                    <div class="stat-label">总转世次数</div>
                </div>
                <div class="history-stat-card">
                    <div class="stat-number">${Object.keys(countryCount).length}</div>
                    <div class="stat-label">体验过的国家</div>
                </div>
                <div class="history-stat-card">
                    <div class="stat-number">${Object.keys(continentCount).length}</div>
                    <div class="stat-label">涉足的大洲</div>
                </div>
            </div>
            ${topCountries.length > 0 ? `
                <div class="top-countries-section">
                    <h4>🏆 最常转世的国家</h4>
                    <div class="top-countries-list">
                        ${topCountries.map(([country, count]) => {
                            const entry = history.find(h => h.country === country);
                            return `
                                <div class="top-country-card">
                                    <span class="top-country-flag">${entry.flag}</span>
                                    <span class="top-country-name">${country}</span>
                                    <span class="top-country-count">${count}次</span>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            ` : ''}
        `;
    }

    // =============== 主流程 ===============
    async function startJourney() {
        // 切换到加载界面
        switchSection('loading');

        // 进度条动画
        const progressBar = document.getElementById('progress-bar');
        progressBar.style.width = '0%';
        setTimeout(() => {
            progressBar.style.width = '30%';
        }, 100);

        // 等待动画
        await new Promise(resolve => setTimeout(resolve, 1500));
        progressBar.style.width = '70%';

        // 调用 API
        const countryData = await reincarnate();

        if (countryData) {
            progressBar.style.width = '100%';
            await new Promise(resolve => setTimeout(resolve, 500));

            // 显示结果
            displayResult(countryData);
            switchSection('result');
        } else {
            // 失败，返回开始界面
            switchSection('start');
        }
    }

    function shareResult() {
        if (!currentCountry) return;

        const text = `🌍 重生模拟器：我的下一世将出生在${currentCountry.country}！${currentCountry.description}`;

        if (navigator.share) {
            navigator.share({
                title: '重生模拟器',
                text: text,
                url: window.location.href
            }).catch(err => console.log('分享失败:', err));
        } else if (navigator.clipboard) {
            navigator.clipboard.writeText(text).then(() => {
                alert('📋 结果已复制到剪贴板！');
            });
        } else {
            alert(text);
        }
    }

    function clearHistory() {
        if (confirm('确定要清空所有转世记录吗？此操作不可恢复。')) {
            history = [];
            saveHistory();
            renderHistory();
        }
    }

    // =============== 事件监听 ===============
    buttons.startJourney.addEventListener('click', startJourney);
    buttons.reincarnate.addEventListener('click', startJourney);
    buttons.viewHistory.addEventListener('click', () => {
        renderHistory();
        switchSection('history');
    });
    buttons.share.addEventListener('click', shareResult);
    buttons.backToResult.addEventListener('click', () => switchSection('result'));
    buttons.clearHistory.addEventListener('click', clearHistory);

    // 键盘快捷键
    document.addEventListener('keydown', (e) => {
        if (e.code === 'Space' && sections.result.classList.contains('active')) {
            e.preventDefault();
            startJourney();
        }
        if (e.code === 'KeyH' && sections.result.classList.contains('active')) {
            e.preventDefault();
            buttons.viewHistory.click();
        }
        if (e.code === 'Escape' && sections.history.classList.contains('active')) {
            e.preventDefault();
            buttons.backToResult.click();
        }
    });

    // =============== 初始化 ===============
    function init() {
        createParticles();
        createWorldMap();
        console.log('🌍 重生模拟器 V2 已加载');
        console.log('💡 快捷键：空格键=快速重生 | H=查看历史 | ESC=返回');
    }

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
