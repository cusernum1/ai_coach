// ============================================================
// app.js — фронт мини-приложения «Дашборд тренера»
// ============================================================
// Получает:
//   • Telegram.WebApp.initDataUnsafe.user.id — ID тренера в TG
//   • /coach/data?tid=<id>                    — агрегаты
//   • /coach/athlete/<id>                     — детали по клику
// ============================================================

(function () {
    const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
    if (tg) tg.expand();

    // ── Получить telegram_id тренера ─────────────────────────
    function getTelegramId() {
        if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
            return tg.initDataUnsafe.user.id;
        }
        // Fallback: ?tid=... в URL (для открытия из браузера вне TG)
        const url = new URL(window.location.href);
        const tid = url.searchParams.get("tid");
        return tid ? parseInt(tid, 10) : null;
    }

    // ── Рендер статистики ────────────────────────────────────
    function renderStats(data) {
        document.getElementById("brand").textContent = data.brand_name || "AI Coach";
        document.getElementById("t-athletes").textContent = data.stats.athletes;
        document.getElementById("t-active").textContent = data.stats.active_subscriptions;
        document.getElementById("t-revenue").textContent = data.stats.revenue_rub.toLocaleString("ru-RU");
    }

    // ── Список спортсменов ───────────────────────────────────
    function renderAthletes(list) {
        const host = document.getElementById("athletes");
        host.innerHTML = "";
        if (!list.length) {
            host.innerHTML = '<div class="empty">Пока нет спортсменов.</div>';
            return;
        }
        list.forEach((a) => {
            const el = document.createElement("div");
            el.className = "row";
            el.innerHTML = `
                <div>
                    <div><b>${escapeHtml(a.name)}</b></div>
                    <div class="meta">${a.sport || "—"} · ${a.level || "—"} · ${a.sessions_per_week || "?"}/нед</div>
                </div>
                <span class="badge ${a.subscription_active ? "on" : ""}">
                    ${a.subscription_active ? "подписка" : "—"}
                </span>
            `;
            el.addEventListener("click", () => loadAthleteDetails(a.id));
            host.appendChild(el);
        });
    }

    // ── Детали спортсмена ────────────────────────────────────
    async function loadAthleteDetails(id) {
        try {
            const resp = await fetch(`/coach/athlete/${id}`);
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            const data = await resp.json();
            showDetails(data);
        } catch (e) {
            alert("Не удалось загрузить детали: " + e.message);
        }
    }

    function showDetails(d) {
        document.getElementById("details").hidden = false;
        document.getElementById("d-title").textContent = `Спортсмен: ${d.profile.name}`;

        // Графики: RPE по датам
        const host = document.getElementById("d-plots");
        host.innerHTML = "";
        if (window.Plotly && d.logs.length) {
            const dates = d.logs.map((l) => l.date).reverse();
            const rpe = d.logs.map((l) => l.rpe).reverse();
            Plotly.newPlot(host, [{
                x: dates, y: rpe, type: "scatter", mode: "lines+markers", name: "RPE",
                line: {color: "#3390ec"},
            }], {
                margin: {t: 10, r: 10, b: 40, l: 40},
                paper_bgcolor: "transparent",
                plot_bgcolor: "transparent",
                font: {color: getComputedStyle(document.body).color},
                yaxis: {range: [0, 10]},
                height: 260,
            }, {displayModeBar: false, responsive: true});
        }

        // Журнал
        const logsHost = document.getElementById("d-logs");
        logsHost.innerHTML = "";
        if (!d.logs.length) {
            logsHost.innerHTML = '<div class="empty">Записей пока нет.</div>';
            return;
        }
        d.logs.forEach((l) => {
            const el = document.createElement("div");
            el.className = "log";
            el.innerHTML = `
                <span class="date">${l.date}</span>
                <b>${escapeHtml(l.name)}</b> — ${l.status} (RPE ${l.rpe})
                <span class="src">${l.source}</span>
            `;
            logsHost.appendChild(el);
        });
    }

    function escapeHtml(s) {
        return String(s || "").replace(/[&<>"']/g, (c) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        }[c]));
    }

    // ── Инициализация ────────────────────────────────────────
    async function init() {
        const tid = getTelegramId();
        if (!tid) {
            document.querySelector(".app").innerHTML =
                "<h2>Нужен Telegram ID</h2><p>Откройте этот дашборд через кнопку в боте.</p>";
            return;
        }
        try {
            const resp = await fetch(`/coach/data?tid=${tid}`);
            if (!resp.ok) {
                const t = await resp.text();
                throw new Error(`HTTP ${resp.status}: ${t}`);
            }
            const data = await resp.json();
            renderStats(data);
            renderAthletes(data.athletes);
        } catch (e) {
            document.querySelector(".app").innerHTML =
                `<h2>Ошибка загрузки</h2><pre>${escapeHtml(e.message)}</pre>`;
        }
    }

    init();
})();
