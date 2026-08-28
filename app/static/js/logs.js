async function loadLogs(){let x=await fetch('/api/logs').then(r=>r.json());logs.innerHTML=x.logs.map(l=>`<tr><td>${new Date(l.created_at).toLocaleString()}</td><td>${l.device}</td><td>${l.ip}</td><td>${l.event_type}</td><td>${l.message}</td></tr>`).join('')||'<tr><td colspan="5">No activity recorded.</td></tr>'}
loadLogs();
