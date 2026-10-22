let statusChart;
let latencyChart;
let dashboardLoading = false;

function escapeHtml(value) {
    return String(value ?? "-").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[character]));
}

async function getJson(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Request failed: ${url}`);
    return response.json();
}

function updateMetrics(summary) {
    const metrics = [
        { label: "Registered devices", value: summary.total, icon: '<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="6" rx="1.5"/><rect x="4" y="14" width="16" height="6" rx="1.5"/><path d="M8 7h.01M8 17h.01"/></svg>', className: "metric-total", href: "/devices" },
        { label: "Online", value: summary.online, icon: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="m8 12 2.5 2.5L16 9"/></svg>', className: "metric-online", href: "/devices?status=ONLINE" },
        { label: "Offline", value: summary.offline, icon: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="m9 9 6 6m0-6-6 6"/></svg>', className: "metric-offline", href: "/devices?status=OFFLINE" },
        { label: "High latency", value: summary.warning + summary.critical, icon: '<svg viewBox="0 0 24 24"><path d="M3 13h4l3-8 4 14 3-8h4"/></svg>', className: "metric-warning", href: "/devices" },
        { label: "Active alerts", value: summary.active_alerts, icon: '<svg viewBox="0 0 24 24"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg>', className: "metric-alerts", href: "/alerts" },
        { label: "Average latency", value: summary.average_latency === null ? "—" : summary.average_latency, unit: summary.average_latency === null ? "" : "ms", icon: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3 2"/></svg>', className: "metric-latency", href: "/devices" },
    ];
    const container = document.querySelector("#metrics");
    if (container.querySelectorAll(".metric-card").length === metrics.length) {
        metrics.forEach((metric, index) => {
            const value = container.querySelectorAll("[data-metric-value]")[index];
            value.textContent = metric.value;
            value.parentElement.querySelector("small").textContent = metric.unit || "";
            if (value.parentElement.querySelector("small").textContent) value.parentElement.querySelector("small").classList.remove("hidden");
            else value.parentElement.querySelector("small").classList.add("hidden");
        });
        return;
    }
    container.innerHTML = metrics.map((metric) => `
        <a class="metric-card ${metric.className}" href="${metric.href}">
            <div class="metric-top"><span>${metric.label}</span><span class="metric-icon" aria-hidden="true">${metric.icon}</span></div>
            <strong><span data-metric-value>${metric.value}</span><small class="${metric.unit ? "" : "hidden"}">${metric.unit || ""}</small></strong><span class="metric-link">View details <span aria-hidden="true">→</span></span>
        </a>`).join("");
}

function updateCharts(summary, latency) {
    const statusEmpty = document.querySelector("#statusEmpty");
    const latencyEmpty = document.querySelector("#latencyEmpty");
    const statusCanvas = document.querySelector("#statusChart");
    const latencyCanvas = document.querySelector("#latencyChart");
    const labels = ["Online", "Offline", "Warning", "Critical latency", "Unknown"];
    const values = [summary.online, summary.offline, summary.warning, summary.critical, summary.unknown];
    const colors = ["#43d9a2", "#ff7087", "#edbf62", "#b28af7", "#73829d"];

    if (typeof Chart === "undefined") {
        statusEmpty.textContent = "The chart library could not be loaded.";
        latencyEmpty.textContent = "The chart library could not be loaded.";
        return;
    }

    if (!summary.total) {
        if (statusChart) statusChart.destroy();
        statusChart = null;
        statusCanvas.hidden = true;
        statusEmpty.textContent = "Add a device to see its current health here.";
        document.querySelector("#statusLegend").innerHTML = "";
    } else {
        statusCanvas.hidden = false;
        statusEmpty.textContent = "";
        if (statusChart) {
            statusChart.data.datasets[0].data = values;
            statusChart.update("none");
        } else {
            statusChart = new Chart(statusCanvas, {
                type: "doughnut",
                data: { labels, datasets: [{ data: values, backgroundColor: colors, borderColor: "#111b2a", borderWidth: 4, hoverOffset: 5 }] },
                options: { cutout: "76%", maintainAspectRatio: false, animation: { duration: 250 }, plugins: { legend: { display: false }, tooltip: { padding: 10, backgroundColor: "#172337", titleColor: "#f3f7fd", bodyColor: "#b8c5d8", borderColor: "#30405a", borderWidth: 1 } } },
            });
        }
        document.querySelector("#statusLegend").innerHTML = labels.map((label, index) => `
            <div class="legend-row"><span class="legend-dot" style="--dot:${colors[index]}"></span><span>${label}</span><b>${values[index]}</b></div>`).join("");
    }

    if (!latency.points.length) {
        if (latencyChart) latencyChart.destroy();
        latencyChart = null;
        latencyCanvas.hidden = true;
        latencyEmpty.textContent = "No response-time checks recorded in the last 24 hours.";
        return;
    }
    latencyCanvas.hidden = false;
    latencyEmpty.textContent = "";
    const palette = ["#61a9ff", "#5ed4df", "#b28af7", "#43d9a2", "#edbf62", "#ef8eaa", "#91a6c4"];
    const devicePoints = new Map();
    for (const point of latency.points) {
        if (!devicePoints.has(point.device)) devicePoints.set(point.device, []);
        devicePoints.get(point.device).push({ x: new Date(point.time).getTime(), y: point.latency });
    }
    const datasets = Array.from(devicePoints, ([device, points], index) => ({
        label: device,
        data: points.sort((first, second) => first.x - second.x),
        borderColor: palette[index % palette.length],
        backgroundColor: palette[index % palette.length],
        pointRadius: points.length > 32 ? 1.5 : 2.5,
        pointHoverRadius: 4,
        borderWidth: 1.7,
        tension: .28,
        fill: false,
    }));
    if (latencyChart) {
        latencyChart.data.datasets = datasets;
        latencyChart.options.plugins.legend.display = datasets.length > 1;
        latencyChart.update("none");
    } else {
        latencyChart = new Chart(latencyCanvas, {
            type: "line",
            data: { datasets },
            options: {
            maintainAspectRatio: false, parsing: false, animation: { duration: 250 }, interaction: { intersect: false, mode: "nearest" },
            plugins: {
                legend: { display: datasets.length > 1, position: "bottom", labels: { color: "#9aaac0", boxWidth: 8, boxHeight: 8, usePointStyle: true, padding: 16, font: { size: 9 } } },
                tooltip: {
                    padding: 10, backgroundColor: "#172337", titleColor: "#f3f7fd", bodyColor: "#b8c5d8", borderColor: "#30405a", borderWidth: 1,
                    callbacks: { title: (items) => items.length ? new Date(items[0].parsed.x).toLocaleString() : "", label: (item) => `${item.dataset.label}: ${item.parsed.y.toFixed(1)} ms` },
                },
            },
            scales: {
                x: { type: "linear", grid: { display: false }, border: { display: false }, ticks: { color: "#7788a1", maxTicksLimit: 6, maxRotation: 0, callback: (value) => new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) } },
                y: { beginAtZero: true, grid: { color: "rgba(139, 159, 190, .1)" }, border: { display: false }, ticks: { color: "#7788a1", maxTicksLimit: 5, padding: 8 } },
            },
            },
        });
    }
}

function updateLists(alertData, activityData, summary) {
    const alertRows = alertData.alerts.map((alert) => {
        const severity = ["INFO", "WARNING", "CRITICAL"].includes(alert.severity) ? alert.severity : "INFO";
        return `<a class="feed-row alert-row" href="/alerts"><span class="severity-mark ${severity.toLowerCase()}" aria-hidden="true"></span><span class="feed-copy"><b>${escapeHtml(alert.message)}</b><small>${escapeHtml(alert.device)} · ${new Date(alert.created_at).toLocaleString()}</small></span><span class="severity-tag ${severity.toLowerCase()}">${severity}</span></a>`;
    });
    document.querySelector("#alerts").innerHTML = alertRows.join("") || '<p class="empty-state feed-empty">No alerts to review. Device conditions will appear here.</p>';

    const activityRows = activityData.activity.map((activity) => `
        <div class="feed-row activity-row"><span class="activity-mark" aria-hidden="true"><i></i></span><span class="feed-copy"><b>${escapeHtml(activity.message)}</b><small>${escapeHtml(activity.device)} · ${new Date(activity.created_at).toLocaleString()}</small></span></div>`);
    document.querySelector("#activity").innerHTML = activityRows.join("") || '<p class="empty-state feed-empty">No recent activity has been recorded.</p>';

    const statusClasses = { ONLINE: "online", OFFLINE: "offline", WARNING: "warning", CRITICAL: "critical", UNKNOWN: "unknown" };
    const deviceRows = summary.devices.map((device) => {
        const status = statusClasses[device.status] ? device.status : "UNKNOWN";
        const latencyValue = device.current_latency === null ? "—" : `${device.current_latency.toFixed(1)} ms`;
        const checkedAt = device.last_checked_at ? new Date(device.last_checked_at).toLocaleString() : "Not checked";
        return `<tr><td><a class="device-name-link" href="/devices/${device.id}"><span class="device-row-icon" aria-hidden="true">${escapeHtml(device.name.slice(0, 1).toUpperCase())}</span><span><b>${escapeHtml(device.name)}</b><small>${escapeHtml(device.device_type.replaceAll("_", " "))}</small></span></a></td><td class="mono-text">${escapeHtml(device.ip_address)}</td><td><span class="status-pill ${statusClasses[status]}"><i aria-hidden="true"></i>${status.replaceAll("_", " ")}</span></td><td class="latency-value">${latencyValue}</td><td>${escapeHtml(checkedAt)}</td></tr>`;
    });
    document.querySelector("#health").innerHTML = deviceRows.join("") || '<tr><td colspan="5" class="empty-state">No devices yet. Add a device to start monitoring.</td></tr>';
}

function showDashboardError() {
    if (statusChart) statusChart.destroy();
    if (latencyChart) latencyChart.destroy();
    statusChart = null;
    latencyChart = null;
    document.querySelector("#statusChart").hidden = true;
    document.querySelector("#latencyChart").hidden = true;
    const updated = document.querySelector("#updated");
    updated.classList.add("state-error");
    updated.textContent = "Dashboard data unavailable · refresh to retry";
    document.querySelector("#metrics").innerHTML = '<p class="error-state">Could not load network metrics.</p>';
    document.querySelector("#statusEmpty").textContent = "Could not load device status.";
    document.querySelector("#latencyEmpty").textContent = "Could not load response-time history.";
    document.querySelector("#alerts").innerHTML = '<p class="error-state">Could not load alerts.</p>';
    document.querySelector("#activity").innerHTML = '<p class="error-state">Could not load activity.</p>';
    document.querySelector("#health").innerHTML = '<tr><td colspan="5" class="error-state">Could not load devices.</td></tr>';
}

async function loadDashboard() {
    if (dashboardLoading) return;
    dashboardLoading = true;
    try {
        const [summary, latency, alerts, activity] = await Promise.all([
            getJson("/api/dashboard/summary"), getJson("/api/dashboard/latency"),
            getJson("/api/dashboard/alerts"), getJson("/api/dashboard/activity"),
        ]);
        updateMetrics(summary);
        updateCharts(summary, latency);
        updateLists(alerts, activity, summary);
        const updated = document.querySelector("#updated");
        updated.classList.remove("state-error");
        updated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
    } catch (error) {
        console.error("Failed to load dashboard:", error);
        showDashboardError();
    } finally {
        dashboardLoading = false;
    }
}

loadDashboard();
setInterval(loadDashboard, 10000);
