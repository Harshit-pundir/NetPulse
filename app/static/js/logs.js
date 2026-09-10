async function loadLogs() {
    const response = await fetch("/api/logs");
    const data = await response.json();
    const rows = [];
    for (const log of data.logs) {
        rows.push(`<tr><td>${new Date(log.created_at).toLocaleString()}</td><td>${log.device}</td><td>${log.ip}</td><td>${log.event_type}</td><td>${log.message}</td></tr>`);
    }
    document.querySelector("#logs").innerHTML = rows.join("") || '<tr><td colspan="5">No activity recorded.</td></tr>';
}

loadLogs();
