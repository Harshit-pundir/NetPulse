let logPage = 1;
let logPages = 1;
let logSearchTimer;
let logLoading = false;
let logReloadRequested = false;

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[character]));
}

async function loadLogs() {
    if (logLoading) { logReloadRequested = true; return; }
    logLoading = true;
    const params = new URLSearchParams({ page: logPage });
    const deviceId = document.querySelector("#logDevice").value;
    const search = document.querySelector("#logSearch").value.trim();
    if (deviceId) params.set("device_id", deviceId);
    if (search) params.set("search", search);

    try {
        const response = await fetch(`/api/logs?${params}`);
        if (!response.ok) throw new Error("Could not load activity logs.");
        const data = await response.json();
        logPages = Math.max(data.pages, 1);
        if (logPage > logPages) { logPage = logPages; logReloadRequested = true; return; }
        const rows = data.logs.map((log) => `<tr><td class="timestamp-cell">${new Date(log.created_at).toLocaleString()}</td><td>${escapeHtml(log.device)}</td><td class="mono-text">${escapeHtml(log.ip)}</td><td><span class="event-tag">${escapeHtml(log.event_type.replaceAll("_", " "))}</span></td><td class="message-cell">${escapeHtml(log.message)}</td></tr>`);
        document.querySelector("#logs").innerHTML = rows.join("") || '<tr><td colspan="5" class="empty-state">No activity found for this selection.</td></tr>';
        document.querySelector("#logCount").textContent = `${data.total} ${data.total === 1 ? "event" : "events"} found`;
        document.querySelector("#logPageLabel").textContent = `Page ${logPage} of ${logPages}`;
        document.querySelector("#logPrevious").disabled = logPage <= 1;
        document.querySelector("#logNext").disabled = logPage >= logPages;
    } catch (error) {
        console.error(error);
        document.querySelector("#logs").innerHTML = '<tr><td colspan="5" class="error-state">Activity is unavailable. Refresh to try again.</td></tr>';
        document.querySelector("#logCount").textContent = "Unable to load activity";
    } finally {
        logLoading = false;
        if (logReloadRequested) { logReloadRequested = false; loadLogs(); }
    }
}

function resetLogPage() { logPage = 1; loadLogs(); }
document.querySelector("#logDevice").addEventListener("change", resetLogPage);
document.querySelector("#logSearch").addEventListener("input", () => {
    clearTimeout(logSearchTimer);
    logSearchTimer = setTimeout(resetLogPage, 250);
});
document.querySelector("#logPrevious").addEventListener("click", () => { if (logPage > 1) { logPage -= 1; loadLogs(); } });
document.querySelector("#logNext").addEventListener("click", () => { if (logPage < logPages) { logPage += 1; loadLogs(); } });
loadLogs();
