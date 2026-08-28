async function loadAlerts(){let x=await fetch('/api/alerts').then(r=>r.json());alerts.innerHTML=x.alerts.map(a=>`<tr><td class="${a.severity}">${a.severity}</td><td>${a.device}</td><td>${a.alert_type}</td><td>${a.message}</td><td>${new Date(a.created_at).toLocaleString()}</td><td>${a.acknowledged?'Acknowledged':admin?`<button onclick="ack(${a.id})">Acknowledge</button>`:'Active'}</td></tr>`).join('')||'<tr><td colspan="6">No alerts.</td></tr>'}
async function ack(id){await fetch('/api/alerts/'+id+'/acknowledge',{method:'PATCH'});loadAlerts()}
loadAlerts();
