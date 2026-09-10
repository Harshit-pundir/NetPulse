function escapeHtml(value) {
    const text = String(value ?? "");
    return text.replace(/[&<>]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[character]));
}

async function loadDevices() {
    const search = document.querySelector("#search").value;
    const response = await fetch(`/api/devices?search=${encodeURIComponent(search)}`);
    const data = await response.json();
    const rows = [];

    for (const device of data.devices) {
        const actions = admin ? `<button onclick='editDevice(${JSON.stringify(device)})'>Edit</button> <button onclick='toggleMonitoring(${device.id}, ${!device.monitoring_enabled})'>Toggle</button> <button onclick='deleteDevice(${device.id})'>Delete</button>` : "";
        const latency = device.current_latency === null ? "-" : device.current_latency.toFixed(1);
        rows.push(`<tr><td><a href="/devices/${device.id}">${escapeHtml(device.name)}</a></td><td>${escapeHtml(device.ip_address)}</td><td>${escapeHtml(device.device_type)}</td><td>${escapeHtml(device.location || "-")}</td><td class="${device.status}">${device.status}</td><td>${latency}</td><td>${device.monitoring_enabled ? "On" : "Off"}</td><td>${actions}</td></tr>`);
    }
    document.querySelector("#devices").innerHTML = rows.join("");
}

function showForm() {
    document.querySelector("#editor").classList.remove("hidden");
    document.querySelector("#deviceForm").reset();
    document.querySelector("#id").value = "";
    document.querySelector("#formTitle").textContent = "Add device";
}

function hideForm() {
    document.querySelector("#editor").classList.add("hidden");
}

function editDevice(device) {
    showForm();
    document.querySelector("#formTitle").textContent = "Edit device";
    for (const [field, value] of Object.entries(device)) {
        const input = document.querySelector(`#${field}`);
        if (input && value !== null) {
            input.value = value;
        }
    }
}

document.querySelector("#deviceForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const fields = ["name", "ip_address", "hostname", "device_type", "location", "description"];
    const device = {};
    for (const field of fields) {
        device[field] = document.querySelector(`#${field}`).value;
    }

    const deviceId = document.querySelector("#id").value;
    const url = deviceId ? `/api/devices/${deviceId}` : "/api/devices";
    const method = deviceId ? "PUT" : "POST";
    const response = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(device) });
    if (!response.ok) {
        const error = await response.json();
        alert(error.error);
        return;
    }
    hideForm();
    loadDevices();
});

async function toggleMonitoring(deviceId, enabled) {
    await fetch(`/api/devices/${deviceId}/monitoring`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ monitoring_enabled: enabled }) });
    loadDevices();
}

async function deleteDevice(deviceId) {
    if (confirm("Delete this device and its history?")) {
        await fetch(`/api/devices/${deviceId}`, { method: "DELETE" });
        loadDevices();
    }
}

loadDevices();
