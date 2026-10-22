let historyChart;

async function loadDeviceDetails() {
    const hours = document.querySelector("#historyRange").value;
    try {
        const [historyResponse, uptimeResponse] = await Promise.all([
            fetch(`/api/devices/${deviceId}/history?hours=${hours}`),
            fetch(`/api/devices/${deviceId}/uptime`),
        ]);
        if (!historyResponse.ok || !uptimeResponse.ok) throw new Error("Could not load monitoring history.");
        const [historyData, uptimeData] = await Promise.all([historyResponse.json(), uptimeResponse.json()]);
        const validPoints = historyData.history.filter((item) => item.latency !== null);
        const monitorErrors = historyData.history.filter((item) => item.status === "MONITOR_ERROR").length;

        if (historyChart) historyChart.destroy();
        if (typeof Chart === "undefined") {
            document.querySelector("#historyEmpty").textContent = "The chart library could not be loaded.";
        } else if (!validPoints.length) {
            document.querySelector("#historyEmpty").textContent = monitorErrors
                ? `${monitorErrors} local monitoring error${monitorErrors === 1 ? "" : "s"} recorded. No response-time measurements are available for this range.`
                : "No response-time measurements are available for this range.";
        } else {
            document.querySelector("#historyEmpty").textContent = "";
            historyChart = new Chart(document.querySelector("#historyChart"), {
                type: "line",
                data: {
                    labels: validPoints.map((item) => new Date(item.checked_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })),
                    datasets: [{ label: "Response time", data: validPoints.map((item) => item.latency), borderColor: "#62aaff", backgroundColor: "rgba(69, 142, 233, .12)", fill: true, pointRadius: validPoints.length > 60 ? 0 : 2.5, pointHoverRadius: 4, borderWidth: 2, tension: .3 }],
                },
                options: {
                    maintainAspectRatio: false, interaction: { intersect: false, mode: "index" },
                    plugins: { legend: { display: false }, tooltip: { padding: 10, backgroundColor: "#172337", titleColor: "#f3f7fd", bodyColor: "#b8c5d8", borderColor: "#30405a", borderWidth: 1 } },
                    scales: {
                        x: { grid: { display: false }, border: { display: false }, ticks: { color: "#7788a1", maxTicksLimit: 7, maxRotation: 0 } },
                        y: { beginAtZero: true, grid: { color: "rgba(139, 159, 190, .1)" }, border: { display: false }, ticks: { color: "#7788a1", maxTicksLimit: 5, padding: 8 } },
                    },
                },
            });
        }

        const periods = [{ hours: "1", title: "Past hour" }, { hours: "24", title: "Past 24 hours" }, { hours: "168", title: "Past 7 days" }];
        document.querySelector("#uptime").innerHTML = periods.map(({ hours: period, title }) => {
            const value = uptimeData[period] === null ? "—" : `${uptimeData[period]}%`;
            const detail = uptimeData[period] === null ? "No completed checks" : "Successful checks";
            return `<div class="uptime-card"><span>${title}</span><strong>${value}</strong><small>${detail}</small></div>`;
        }).join("");
    } catch (error) {
        console.error(error);
        document.querySelector("#historyEmpty").textContent = "Monitoring history is unavailable. Refresh to try again.";
        document.querySelector("#uptime").innerHTML = '<p class="error-state">Could not calculate observed uptime.</p>';
    }
}

document.querySelector("#historyRange").addEventListener("change", loadDeviceDetails);
loadDeviceDetails();
