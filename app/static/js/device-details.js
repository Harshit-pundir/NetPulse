let historyChart;

async function loadDeviceDetails() {
    const [historyResponse, uptimeResponse] = await Promise.all([
        fetch(`/api/devices/${deviceId}/history?hours=24`),
        fetch(`/api/devices/${deviceId}/uptime`),
    ]);
    const historyData = await historyResponse.json();
    const uptimeData = await uptimeResponse.json();

    if (historyChart) {
        historyChart.destroy();
    }
    historyChart = new Chart(document.querySelector("#historyChart"), {
        type: "line",
        data: { labels: historyData.history.map((item) => new Date(item.checked_at).toLocaleTimeString()), datasets: [{ label: "Latency (ms)", data: historyData.history.map((item) => item.latency), borderColor: "#4f9cff", tension: 0.3 }] },
    });

    const rows = [];
    for (const hours of ["1", "24", "168"]) {
        const label = hours === "168" ? "7 days" : `${hours} hour${hours === "1" ? "" : "s"}`;
        const value = uptimeData[hours] === null ? "Insufficient data" : `${uptimeData[hours]}%`;
        rows.push(`<div class="item">Last ${label}: <b>${value}</b></div>`);
    }
    document.querySelector("#uptime").innerHTML = rows.join("");
}

loadDeviceDetails();
