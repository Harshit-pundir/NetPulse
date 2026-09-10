async function loadAlerts() {
    const response = await fetch("/api/alerts");
    const data = await response.json();
    const rows = [];
    for (const alert of data.alerts) {
        const state = alert.acknowledged ? "Acknowledged" : (admin ? `<button onclick="acknowledgeAlert(${alert.id})">Acknowledge</button>` : "Active");
        rows.push(`<tr><td class="${alert.severity}">${alert.severity}</td><td>${alert.device}</td><td>${alert.alert_type}</td><td>${alert.message}</td><td>${new Date(alert.created_at).toLocaleString()}</td><td>${state}</td></tr>`);
    }
    document.querySelector("#alerts").innerHTML = rows.join("") || '<tr><td colspan="6">No alerts.</td></tr>';
}

async function acknowledgeAlert(alertId) {
    await fetch(`/api/alerts/${alertId}/acknowledge`, { method: "PATCH" });
    loadAlerts();
}

loadAlerts();
