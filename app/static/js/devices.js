let devicePage = 1;
let devicePages = 1;
let deviceSearchTimer;
let deviceLoadNumber = 0;

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[character]));
}

function showNotice(message, isError = false) {
    const notice = document.querySelector("#deviceNotice");
    notice.textContent = message;
    notice.classList.toggle("notice-error", isError);
    notice.classList.remove("hidden");
}

async function loadDevices() {
    const loadNumber = ++deviceLoadNumber;
    const search = document.querySelector("#search").value.trim();
    const status = document.querySelector("#statusFilter").value;
    const params = new URLSearchParams({ search, status, page: devicePage });
    try {
        const response = await fetch(`/api/devices?${params}`);
        if (!response.ok) throw new Error("Could not load devices.");
        const data = await response.json();
        if (loadNumber !== deviceLoadNumber) return;
        devicePages = Math.max(data.pages, 1);
        if (devicePage > devicePages) { devicePage = devicePages; loadDevices(); return; }
        const statusClasses = { ONLINE: "online", OFFLINE: "offline", WARNING: "warning", CRITICAL: "critical", UNKNOWN: "unknown" };
        const rows = data.devices.map((device) => {
            const status = statusClasses[device.status] ? device.status : "UNKNOWN";
            const latency = device.current_latency === null ? "—" : `${device.current_latency.toFixed(1)} ms`;
            const actions = admin ? `
                <button class="table-action" type="button" data-action="edit" data-id="${device.id}">Edit</button>
                <button class="table-action" type="button" data-action="toggle" data-id="${device.id}" data-enabled="${!device.monitoring_enabled}">${device.monitoring_enabled ? "Pause" : "Resume"}</button>
                <button class="table-action table-action-danger" type="button" data-action="delete" data-id="${device.id}">Delete</button>` : "—";
            return `<tr><td><a class="device-name-link" href="/devices/${device.id}"><span class="device-row-icon" aria-hidden="true">${escapeHtml(device.name.slice(0, 1).toUpperCase())}</span><span><b>${escapeHtml(device.name)}</b><small>${escapeHtml(device.hostname || "No hostname")}</small></span></a></td><td class="mono-text">${escapeHtml(device.ip_address)}</td><td>${escapeHtml(device.device_type.replaceAll("_", " "))}</td><td>${escapeHtml(device.location || "—")}</td><td><span class="status-pill ${statusClasses[status]}"><i aria-hidden="true"></i>${status.replaceAll("_", " ")}</span></td><td class="latency-value">${latency}</td><td><span class="monitor-state ${device.monitoring_enabled ? "enabled" : "paused"}">${device.monitoring_enabled ? "Enabled" : "Paused"}</span></td><td><div class="row-actions">${actions}</div></td></tr>`;
        });

        document.querySelector("#devices").innerHTML = rows.join("") || `<tr><td colspan="8" class="empty-state">${search || status ? "No devices match these filters." : "No devices yet. Add a device to begin monitoring."}</td></tr>`;
        document.querySelector("#deviceCount").textContent = `${data.total} ${data.total === 1 ? "device" : "devices"}${search || status ? " matching filters" : " registered"}`;
        document.querySelector("#pageLabel").textContent = `Page ${devicePage} of ${devicePages}`;
        document.querySelector("#previousPage").disabled = devicePage <= 1;
        document.querySelector("#nextPage").disabled = devicePage >= devicePages;
    } catch (error) {
        if (loadNumber !== deviceLoadNumber) return;
        console.error(error);
        document.querySelector("#devices").innerHTML = '<tr><td colspan="8" class="error-state">Device inventory is unavailable. Refresh to try again.</td></tr>';
        document.querySelector("#deviceCount").textContent = "Unable to load devices";
    }
}

function showForm() {
    document.querySelector("#deviceNotice").classList.add("hidden");
    document.querySelector("#editor").classList.remove("hidden");
    document.querySelector("#deviceForm").reset();
    document.querySelector("#id").value = "";
    document.querySelector("#formTitle").textContent = "Add a device";
    document.querySelector("#name").focus();
}

function hideForm() {
    document.querySelector("#editor").classList.add("hidden");
}

function editDevice(device) {
    showForm();
    document.querySelector("#formTitle").textContent = "Edit device";
    for (const field of ["id", "name", "ip_address", "hostname", "device_type", "location", "description"]) {
        const input = document.querySelector(`#${field}`);
        input.value = device[field] ?? "";
    }
    document.querySelector("#editor").scrollIntoView({ behavior: "smooth", block: "start" });
}

document.querySelector("#deviceForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submitButton = form.querySelector('[type="submit"]');
    const fields = ["name", "ip_address", "hostname", "device_type", "location", "description"];
    const device = Object.fromEntries(fields.map((field) => [field, document.querySelector(`#${field}`).value]));
    const deviceId = document.querySelector("#id").value;
    submitButton.disabled = true;
    submitButton.textContent = "Saving…";
    try {
        const response = await fetch(deviceId ? `/api/devices/${deviceId}` : "/api/devices", {
            method: deviceId ? "PUT" : "POST",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content },
            body: JSON.stringify(device),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Could not save the device.");
        hideForm();
        showNotice(deviceId ? "Device details updated." : "Device added. Its status will update after a monitoring check.");
        devicePage = 1;
        await loadDevices();
    } catch (error) {
        showNotice(error.message || "Could not save the device. Check your connection and try again.", true);
    } finally {
        submitButton.disabled = false;
        submitButton.innerHTML = "Save device";
    }
});

document.querySelector("#devices")?.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const { action, id } = button.dataset;
    try {
        if (action === "edit") {
            const response = await fetch(`/api/devices/${id}`);
            if (!response.ok) throw new Error("Could not load this device.");
            editDevice(await response.json());
        } else if (action === "toggle") {
            const response = await fetch(`/api/devices/${id}/monitoring`, {
                method: "PATCH", headers: { "Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content },
                body: JSON.stringify({ monitoring_enabled: button.dataset.enabled === "true" }),
            });
            if (!response.ok) throw new Error("Could not update monitoring settings.");
            showNotice(`Monitoring ${button.dataset.enabled === "true" ? "resumed" : "paused"}.`);
            await loadDevices();
        } else if (action === "delete" && confirm("Delete this device and its history? This cannot be undone.")) {
            const response = await fetch(`/api/devices/${id}`, { method: "DELETE", headers: { "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content } });
            if (!response.ok) throw new Error("Could not delete this device.");
            showNotice("Device and its monitoring history deleted.");
            await loadDevices();
        }
    } catch (error) {
        showNotice(error.message || "The action could not be completed.", true);
    }
});

document.querySelector("#statusFilter")?.addEventListener("change", () => { devicePage = 1; loadDevices(); });
document.querySelector("#search")?.addEventListener("input", () => {
    clearTimeout(deviceSearchTimer);
    deviceSearchTimer = setTimeout(() => { devicePage = 1; loadDevices(); }, 250);
});
document.querySelector("#previousPage")?.addEventListener("click", () => { if (devicePage > 1) { devicePage -= 1; loadDevices(); } });
document.querySelector("#nextPage")?.addEventListener("click", () => { if (devicePage < devicePages) { devicePage += 1; loadDevices(); } });

const initialStatus = new URLSearchParams(window.location.search).get("status");
if (["ONLINE", "OFFLINE", "WARNING", "CRITICAL", "UNKNOWN"].includes(initialStatus)) document.querySelector("#statusFilter").value = initialStatus;
loadDevices();
