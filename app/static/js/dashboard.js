let statusChart;
let latencyChart;

function escapeHtml(value) {
    const text = String(value ?? "-");
    return text.replace(/[&<>]/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
    }[character]));
}

async function getJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Request failed: ${url}`);
    }
    return response.json();
}

function updateMetrics(summary) {
    const metrics = [
        ["Total devices", summary.total],
        ["Online", summary.online],
        ["Offline", summary.offline],
        ["Warning", summary.warning],
        ["Active alerts", summary.active_alerts],
        ["Average latency", summary.average_latency === null ? "-" : `${summary.average_latency} ms`],
    ];

    const cards = [];
    for (const [label, value] of metrics) {
        cards.push(`<div><b>${label}</b><strong>${value}</strong></div>`);
    }
    document.querySelector("#metrics").innerHTML = cards.join("");
}

function updateCharts(summary, latency) {
    if (statusChart) {
        statusChart.destroy();
    }
    statusChart = new Chart(document.querySelector("#statusChart"), {
        type: "doughnut",
        data: {
            labels: ["Online", "Offline", "Warning", "Unknown"],
            datasets: [{
                data: [summary.online, summary.offline, summary.warning, summary.unknown],
                backgroundColor: ["#31d09a", "#fa657a", "#f5bd52", "#71809c"],
            }],
        },
        options: { plugins: { legend: { labels: { color: "#e7edf9" } } } },
    });

    if (latencyChart) {
        latencyChart.destroy();
    }
    latencyChart = new Chart(document.querySelector("#latencyChart"), {
        type: "line",
        data: {
            labels: latency.points.map((point) => new Date(point.time).toLocaleTimeString()),
            datasets: [{
                label: "Latency (ms)",
                data: latency.points.map((point) => point.latency),
                borderColor: "#4f9cff",
                tension: 0.3,
            }],
        },
        options: { scales: { x: { ticks: { color: "#91a0bd" } }, y: { ticks: { color: "#91a0bd" } } } },
    });
}

function updateLists(alertData, activityData, summary) {
    const alertRows = [];
    for (const alert of alertData.alerts) {
        alertRows.push(`<div class="item"><span class="badge ${alert.severity}">${alert.severity}</span> ${escapeHtml(alert.message)}<small>${escapeHtml(alert.device)} · ${new Date(alert.created_at).toLocaleString()}</small></div>`);
    }
    document.querySelector("#alerts").innerHTML = alertRows.join("") || "No alerts.";

    const activityRows = [];
    for (const activity of activityData.activity) {
        activityRows.push(`<div class="item">${escapeHtml(activity.message)}<small>${new Date(activity.created_at).toLocaleString()}</small></div>`);
    }
    document.querySelector("#activity").innerHTML = activityRows.join("") || "No activity yet.";

    const deviceRows = [];
    for (const device of summary.devices) {
        const latency = device.current_latency === null ? "-" : device.current_latency.toFixed(1);
        const checkedAt = device.last_checked_at ? new Date(device.last_checked_at).toLocaleString() : "Never";
        deviceRows.push(`<tr><td><a href="/devices/${device.id}">${escapeHtml(device.name)}</a></td><td>${escapeHtml(device.ip_address)}</td><td>${escapeHtml(device.device_type)}</td><td class="${device.status}">${device.status}</td><td>${latency} ms</td><td>${checkedAt}</td></tr>`);
    }
    document.querySelector("#health").innerHTML = deviceRows.join("");
}

async function loadDashboard() {
    try {
        const [summary, latency, alerts, activity] = await Promise.all([
            getJson("/api/dashboard/summary"),
            getJson("/api/dashboard/latency"),
            getJson("/api/dashboard/alerts"),
            getJson("/api/dashboard/activity"),
        ]);
        updateMetrics(summary);
        updateCharts(summary, latency);
        updateLists(alerts, activity, summary);
        document.querySelector("#updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
    } catch (error) {
        console.error("Failed to load dashboard:", error);
    }
}

loadDashboard();
setInterval(loadDashboard, 8000);
