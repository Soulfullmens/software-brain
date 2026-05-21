import re
import sys

file_path = "src/business/dashboard.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

new_html = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Software Brain — AI Agent Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-1: #09090e; --bg-2: #12121c; --card-bg: rgba(255, 255, 255, 0.03); 
    --card-border: rgba(255, 255, 255, 0.08);
    --accent-1: #4ade80; --accent-2: #3b82f6; --accent-3: #8b5cf6; --accent-4: #f43f5e;
    --text-main: #f8fafc; --text-muted: #94a3b8;
    --glass: rgba(18, 18, 28, 0.7);
  }
  * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Outfit', sans-serif; }
  body { 
    background-color: var(--bg-1); color: var(--text-main); 
    background-image: 
      radial-gradient(circle at 15% 50%, rgba(139, 92, 246, 0.15), transparent 25%),
      radial-gradient(circle at 85% 30%, rgba(59, 130, 246, 0.15), transparent 25%);
    background-attachment: fixed; min-height: 100vh;
  }
  .header {
    background: var(--glass); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--card-border); padding: 24px 40px;
    position: sticky; top: 0; z-index: 100;
  }
  .header h1 { font-family: 'Space Grotesk', sans-serif; font-size: 28px; font-weight: 700; 
               background: linear-gradient(to right, #4ade80, #3b82f6); -webkit-background-clip: text; color: transparent; }
  .header p { color: var(--text-muted); font-size: 15px; margin-top: 6px; font-weight: 300; }
  .container { max-width: 1400px; margin: 0 auto; padding: 40px 24px; animation: fadeIn 0.8s ease-out; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  .grid { display: grid; gap: 24px; }
  .grid-4 { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
  .card {
    background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 16px; 
    padding: 24px; backdrop-filter: blur(8px); transition: transform 0.3s ease, box-shadow 0.3s ease;
  }
  .card:hover { transform: translateY(-4px); box-shadow: 0 12px 24px rgba(0,0,0,0.2); border-color: rgba(255,255,255,0.15); }
  .card h3 { font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 12px; font-weight: 600; }
  .card .value { font-family: 'Space Grotesk', sans-serif; font-size: 36px; font-weight: 700; color: var(--text-main); }
  .card .value.green { color: var(--accent-1); }
  .card .value.orange { color: #fbbf24; }
  .badge { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; letter-spacing: 0.5px; }
  .badge-green { background: rgba(74, 222, 128, 0.15); color: var(--accent-1); }
  .badge-blue { background: rgba(59, 130, 246, 0.15); color: var(--accent-2); }
  .badge-orange { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
  .agent-list { display: flex; flex-direction: column; gap: 16px; }
  .agent-item { 
    display: flex; justify-content: space-between; align-items: center; 
    padding: 16px; background: rgba(255,255,255,0.02); border-radius: 12px; border: 1px solid var(--card-border);
    transition: background 0.2s;
  }
  .agent-item:hover { background: rgba(255,255,255,0.05); }
  .agent-name { font-weight: 600; font-size: 16px; color: #fff; }
  .agent-caps { font-size: 13px; color: var(--text-muted); margin-top: 4px; font-weight: 300; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; }
  th, td { text-align: left; padding: 14px 16px; border-bottom: 1px solid var(--card-border); font-size: 14px; }
  th { color: var(--text-muted); font-weight: 500; text-transform: uppercase; font-size: 11px; letter-spacing: 1px; }
  tr:hover td { background: rgba(255,255,255,0.02); }
  .section { margin-top: 40px; }
  .section-title { font-size: 20px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; gap: 12px; font-family: 'Space Grotesk', sans-serif;}
  .chat-box { background: linear-gradient(145deg, rgba(26,26,38,0.8), rgba(18,18,28,0.9)); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 16px; padding: 24px; position: relative; overflow: hidden; }
  .chat-box::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: linear-gradient(90deg, transparent, rgba(139, 92, 246, 0.8), transparent); }
  .chat-input { display: flex; gap: 12px; margin-top: 16px; }
  .chat-input input { flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--card-border); border-radius: 10px; padding: 14px 20px; color: var(--text-main); font-size: 15px; outline: none; transition: all 0.3s; font-family: 'Outfit', sans-serif;}
  .chat-input input:focus { border-color: var(--accent-3); box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.2); }
  .chat-input button { background: linear-gradient(135deg, var(--accent-3), var(--accent-2)); color: white; border: none; border-radius: 10px; padding: 14px 28px; font-weight: 600; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; font-family: 'Outfit', sans-serif; letter-spacing: 0.5px;}
  .chat-input button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(139, 92, 246, 0.4); }
  .chat-output { max-height: 350px; overflow-y: auto; padding: 16px; font-size: 14px; margin-top: 16px; background: rgba(0,0,0,0.4); border-radius: 10px; border: 1px solid var(--card-border); white-space: pre-wrap; color: #e2e8f0; scroll-behavior: smooth; }
  ::-webkit-scrollbar { width: 8px; }
  ::-webkit-scrollbar-track { background: rgba(0,0,0,0.2); border-radius: 4px; }
  ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
  .tabs { display: flex; gap: 8px; margin-bottom: 24px; overflow-x: auto; padding-bottom: 4px; }
  .tab { padding: 10px 20px; border-radius: 10px; cursor: pointer; font-size: 14px; font-weight: 500; background: rgba(255,255,255,0.03); color: var(--text-muted); border: 1px solid var(--card-border); transition: all 0.2s; white-space: nowrap;}
  .tab.active { background: rgba(139, 92, 246, 0.15); color: var(--accent-3); border-color: rgba(139, 92, 246, 0.4); }
  .tab:hover:not(.active) { background: rgba(255,255,255,0.08); color: var(--text-main); }
  .tab-content { animation: fadeIn 0.4s ease-out; }
  .footer { text-align: center; padding: 40px 24px; color: var(--text-muted); font-size: 14px; border-top: 1px solid var(--card-border); margin-top: 60px; font-weight: 300;}
  .pulse { display: inline-block; width: 8px; height: 8px; background-color: var(--accent-1); border-radius: 50%; box-shadow: 0 0 10px var(--accent-1); animation: pulse 2s infinite; margin-right: 8px;}
  @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.7); } 70% { box-shadow: 0 0 0 10px rgba(74, 222, 128, 0); } 100% { box-shadow: 0 0 0 0 rgba(74, 222, 128, 0); } }
</style>
</head>
<body>

<div class="header">
  <div style="max-width: 1400px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center;">
    <div>
      <h1>✨ Agentic Engine Pro</h1>
      <p>Multi-Agent Cognitive Platform | Real-Time Orchestration</p>
    </div>
    <div style="display: flex; align-items: center; background: rgba(255,255,255,0.05); padding: 8px 16px; border-radius: 20px; border: 1px solid var(--card-border);">
      <span class="pulse"></span>
      <span style="font-size: 13px; font-weight: 500; color: var(--text-main);">System Online</span>
    </div>
  </div>
</div>

<div class="container">

  <!-- KPIs -->
  <div class="grid grid-4" id="kpis">
    <div class="card"><h3>Active Agents</h3><div class="value" id="kpi-agents">-</div></div>
    <div class="card"><h3>Tasks Processed</h3><div class="value green" id="kpi-tasks">-</div></div>
    <div class="card"><h3>Open Tickets</h3><div class="value orange" id="kpi-tickets">-</div></div>
    <div class="card"><h3>Properties Listed</h3><div class="value" id="kpi-properties">-</div></div>
  </div>

  <!-- Agent Chat -->
  <div class="section">
    <div class="chat-box">
      <h3 style="font-size: 18px; font-family: 'Space Grotesk', sans-serif; margin-bottom:4px; display: flex; align-items: center; gap: 8px;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--accent-3)"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
        Command Center
      </h3>
      <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 16px;">Directly prompt the multi-agent orchestrator in natural language.</p>
      <div class="chat-input">
        <input id="chat-in" type="text" placeholder="Type a request (e.g. 'I need a 3-bedroom villa in Dubai Hills' or 'Schedule a consultation at 10am')" onkeydown="if(event.key==='Enter')sendChat()">
        <button onclick="sendChat()">Execute</button>
      </div>
      <div class="chat-output" id="chat-out">System initialized. Waiting for commands...</div>
    </div>
  </div>

  <div class="grid" style="grid-template-columns: 1fr 2fr; margin-top: 40px; gap: 32px; align-items: start;">
    <!-- Agents Section -->
    <div>
      <div class="section-title">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--accent-1)"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
        Agent Fleet
      </div>
      <div class="agent-list" id="agent-list"></div>
    </div>

    <!-- Tabs: CRM | Support | Properties | Schedule -->
    <div style="min-width: 0;">
      <div class="section-title">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--accent-2)"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>
        Data Hub
      </div>
      <div class="tabs">
        <div class="tab active" onclick="showTab('crm')">CRM Pipeline</div>
        <div class="tab" onclick="showTab('support')">Support</div>
        <div class="tab" onclick="showTab('properties')">Properties</div>
        <div class="tab" onclick="showTab('schedule')">Schedule</div>
        <div class="tab" onclick="showTab('uae')">UAE Intel</div>
      </div>

      <div id="tab-crm" class="card tab-content">
        <h3 style="color: var(--accent-3)">CRM Lead Pipeline</h3>
        <div style="overflow-x: auto;">
          <table><thead><tr><th>Name</th><th>Email</th><th>Status</th><th>Score</th></tr></thead>
          <tbody id="crm-table"></tbody></table>
        </div>
      </div>

      <div id="tab-support" class="card tab-content" style="display:none">
        <h3 style="color: var(--accent-3)">Support Tickets</h3>
        <div style="overflow-x: auto;">
          <table><thead><tr><th>ID</th><th>Subject</th><th>Category</th><th>Status</th></tr></thead>
          <tbody id="support-table"></tbody></table>
        </div>
      </div>

      <div id="tab-properties" class="card tab-content" style="display:none">
        <h3 style="color: var(--accent-3)">Property Listings</h3>
        <div style="overflow-x: auto;">
          <table><thead><tr><th>ID</th><th>Type</th><th>Area</th><th>Beds</th><th>Size</th><th>Price (AED)</th></tr></thead>
          <tbody id="property-table"></tbody></table>
        </div>
      </div>

      <div id="tab-schedule" class="card tab-content" style="display:none">
        <h3 style="color: var(--accent-3)">Available Slots</h3>
        <div id="slots-grid" style="display:flex;flex-wrap:wrap;gap:12px;margin-top:16px;"></div>
      </div>

      <div id="tab-uae" class="card tab-content" style="display:none">
        <h3 style="color: var(--accent-3)">UAE Government Services</h3>
        <div style="overflow-x: auto;">
          <table><thead><tr><th>Service</th><th>Department</th><th>Fee</th></tr></thead>
          <tbody id="uae-table"></tbody></table>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="footer">
  &copy; 2026 Agentic Engine Pro | Built intentionally to augment human capability
</div>

<script>
const BASE = '';  // same origin

async function api(path, opts) {
  try {
    const r = await fetch(BASE + path, opts);
    return await r.json();
  } catch(e) { return {error: e.message}; }
}

async function refresh() {
  // Dashboard data
  const d = await api('/api/dashboard');
  if (d.agents) {
    document.getElementById('kpi-agents').textContent = d.agents.length;
    document.getElementById('kpi-tasks').textContent = d.total_tasks || 0;
    document.getElementById('kpi-tickets').textContent = d.active_tickets || 0;
    document.getElementById('kpi-properties').textContent = d.property_listings || 0;

    const al = document.getElementById('agent-list');
    al.innerHTML = d.agents.map(a => `
      <div class="agent-item">
        <div><div class="agent-name">${a.name}</div><div class="agent-caps">${a.capabilities.join(', ')}</div></div>
        <div><span class="badge badge-green">${a.stats.tasks_handled} tasks</span></div>
      </div>`).join('');
  }

  // Properties
  const p = await api('/api/properties');
  if (p.properties) {
    document.getElementById('property-table').innerHTML = p.properties.map(pr => `
      <tr><td>#${pr.id.split('-')[0]}</td><td>${pr.type}</td><td>${pr.area}</td><td>${pr.bedrooms}</td><td>${pr.size_sqft}</td><td style="color:var(--accent-1);font-weight:600;">AED ${pr.price_aed.toLocaleString()}</td></tr>`).join('');
  }

  // CRM
  const leads = await api('/api/crm/leads');
  if (leads.leads) {
    document.getElementById('crm-table').innerHTML = leads.leads.map(l => `
      <tr><td style="font-weight:500">${l.name}</td><td>${l.email||'-'}</td><td><span class="badge badge-${l.status==='qualified'?'green':(l.status==='new'?'blue':'orange')}">${l.status}</span></td><td><span style="background:rgba(255,255,255,0.1);padding:2px 8px;border-radius:12px;font-size:12px;">${l.score}/100</span></td></tr>`).join('') || '<tr><td colspan=4 style="color:var(--text-muted);text-align:center;padding:32px;">No leads yet.</td></tr>';
  }

  // Support
  const tix = await api('/api/support/tickets');
  if (tix.tickets) {
    document.getElementById('support-table').innerHTML = tix.tickets.map(t => `
      <tr><td>#${t.id.split('-')[0]}</td><td>${t.subject}</td><td><span class="badge badge-orange">${t.category}</span></td><td>${t.status}</td></tr>`).join('') || '<tr><td colspan=4 style="color:var(--text-muted);text-align:center;padding:32px;">No support tickets open.</td></tr>';
  }

  // Slots
  const slots = await api('/api/schedule/slots');
  if (slots.available_slots) {
    document.getElementById('slots-grid').innerHTML = slots.available_slots.map(s =>
      `<div style="background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);color:var(--accent-2);padding:10px 18px;border-radius:10px;cursor:pointer;font-weight:500;transition:all 0.2s;" onmouseover="this.style.background='rgba(59,130,246,0.2)'" onmouseout="this.style.background='rgba(59,130,246,0.1)'" onclick="bookSlot('${s}')">${s}</div>`).join('');
  }

  // UAE services
  const srv = await api('/api/uae/services');
  if (srv.services) {
    document.getElementById('uae-table').innerHTML = srv.services.map(s => `
      <tr><td style="font-weight:500">${s.name_en || s.name || '-'}</td><td>${s.department || '-'}</td><td style="color:var(--accent-1);">${s.fee_aed ? s.fee_aed + ' AED' : 'Free'}</td></tr>`).join('');
  }
}

async function sendChat() {
  const inp = document.getElementById('chat-in');
  const out = document.getElementById('chat-out');
  const text = inp.value.trim();
  if (!text) return;
  inp.value = '';
  out.innerHTML += '\\n\\n<span style="color:var(--accent-2)">> USER:</span> ' + text + '\\n<span style="color:var(--text-muted)">⏳ Processing via Multi-Agent Orchestrator...</span>';
  out.scrollTop = out.scrollHeight;
  const r = await api('/api/natural', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text})});
  out.innerHTML += '\\n<span style="color:var(--accent-1)">> SYSTEM:</span>\\n' + JSON.stringify(r, null, 2);
  out.scrollTop = out.scrollHeight;
  setTimeout(refresh, 1000);
}

async function bookSlot(time) {
  const name = prompt('Client name for ' + time + ' slot:');
  if (!name) return;
  await api('/api/schedule', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({type:'consultation',client_name:name,preferred_time:time})});
  refresh();
}

function showTab(name) {
  ['crm','support','properties','schedule','uae'].forEach(t => {
    document.getElementById('tab-'+t).style.display = t===name?'block':'none';
  });
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  event.target.classList.add('active');
}

refresh();
setInterval(refresh, 8000);
</script>
</body>
</html>'''

pattern = r'DASHBOARD_HTML = """<!DOCTYPE html>.*?</html>"""'
new_content = re.sub(pattern, f'DASHBOARD_HTML = """{new_html}"""', content, flags=re.DOTALL)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Dashboard UI updated beautifully.")
