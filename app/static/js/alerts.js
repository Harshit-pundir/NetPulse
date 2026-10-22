let alertPage = 1;
let alertPages = 1;
let alertLoading = false;
let alertReloadRequested = false;

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[character]));
}

async function loadAlerts() {
    if (alertLoading) { alertReloadRequested = true; return; }
    alertLoading = true;
    const params = new URLSearchParams({ page: alertPage });
    const severity = document.querySelector("#severity").value;
    const acknowledged = document.querySelector("#alertStatus").value;
    const deviceId = document.querySelector("#alertDevice").value;
    if (severity) params.set("severity", severity);
    if (acknowledged !== "") params.set("acknowledged", acknowledged);
    if (deviceId) params.set("device_id", deviceId);

    try {
        const response = await fetch(`/api/alerts?${params}`);
        if (!response.ok) throw new Error("Could not load alert history.");
        const data = await response.json();
        alertPages = Math.max(data.pages, 1);
        if (alertPage > alertPages) { alertPage = alertPages; alertReloadRequested = true; return; }
        const rows = data.alerts.map((alert) => {
            const severityClass = ["INFO", "WARNING", "CRITICAL"].includes(alert.severity) ? alert.severity.toLowerCase() : "info";
            const status = alert.acknowledged ? '<span class="resolved-state">Resolved</span>' : (admin ? `<button class="button button-small" type="button" data-alert-id="${alert.id}">Acknowledge</button>` : '<span class="active-state">Active</span>');
            return `<tr><td><span class="severity-tag ${severityClass}"><i aria-hidden="true"></i>${escapeHtml(alert.severity)}</span></td><td><a class="table-link" href="/devices">${escapeHtml(alert.device)}</a></td><td>${escapeHtml(alert.alert_type.replaceAll("_", " "))}</td><td class="message-cell">${escapeHtml(alert.message)}</td><td>${new Date(alert.created_at).toLocaleString()}</td><td>${status}</td></tr>`;
        });
        document.querySelector("#alerts").innerHTML = rows.join("") || '<tr><td colspan="6" class="empty-state">No alerts match these filters.</td></tr>';
        document.querySelector("#alertCount").textContent = `${data.total} ${data.total === 1 ? "alert" : "alerts"} match these filters`;
        document.querySelector("#alertPageLabel").textContent = `Page ${alertPage} of ${alertPages}`;
        document.querySelector("#alertPrevious").disabled = alertPage <= 1;
        document.querySelector("#alertNext").disabled = alertPage >= alertPages;
    } catch (error) {
        console.error(error);
        document.querySelector("#alerts").innerHTML = '<tr><td colspan="6" class="error-state">Alert history is unavailable. Refresh to try again.</td></tr>';
        document.querySelector("#alertCount").textContent = "Unable to load alerts";
    } finally {
        alertLoading = false;
        if (alertReloadRequested) { alertReloadRequested = false; loadAlerts(); }
    }
}

function resetAlertPage() { alertPage = 1; loadAlerts(); }
document.querySelector("#severity").addEventListener("change", resetAlertPage);
document.querySelector("#alertStatus").addEventListener("change", resetAlertPage);
document.querySelector("#alertDevice").addEventListener("change", resetAlertPage);
document.querySelector("#alertPrevious").addEventListener("click", () => { if (alertPage > 1) { alertPage -= 1; loadAlerts(); } });
document.querySelector("#alertNext").addEventListener("click", () => { if (alertPage < alertPages) { alertPage += 1; loadAlerts(); } });
document.querySelector("#alerts").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-alert-id]");
    if (!button) return;
    button.disabled = true;
    try {
        const response = await fetch(`/api/alerts/${button.dataset.alertId}/acknowledge`, { method: "PATCH", headers: { "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content } });
        if (!response.ok) throw new Error("Could not acknowledge this alert.");
        await loadAlerts();
    } catch (error) {
        button.disabled = false;
        button.title = error.message;
    }
});

loadAlerts();
