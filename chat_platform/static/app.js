/**
 * app.js — NOMAD SecureChat Frontend (Phase 8 Extended)
 * 
 * Features:
 * - Three.js interactive particle background
 * - WebSocket real-time messaging
 * - E2E Encryption (X25519 + AES-256-GCM via WebCrypto API)
 * - WebRTC peer-to-peer video/voice calls with CSS Filters
 * - Social Features: Profiles, Friends, Themes, Read Receipts
 * - Live AI-powered subtitle translation
 * - Private Mode (agent blinded)
 * - Agent Chat Integration (@nomad_agent)
 */

'use strict';

// ═══════════════ STATE ═════════════════ 

const State = {
  token: localStorage.getItem('chat_token'),
  me: JSON.parse(localStorage.getItem('chat_user') || 'null'),
  ws: null,
  currentRoom: null,
  currentPeer: null,
  privateMode: false,
  subtitleLang: localStorage.getItem('subtitle_lang') || 'en',
  sessionKeys: {}, // peer_user_id -> CryptoKey
  // Call state
  peerConnection: null,
  localStream: null,
  callTimer: null,
  callSeconds: 0,
  subtitlesOn: true,
  recognition: null,
  isMuted: false,
  videoOff: false,
  incomingCallData: null,
};

const API = (path, options = {}) => {
  const headers = { 'Content-Type': 'application/json' };
  if (State.token) headers['Authorization'] = `Bearer ${State.token}`;
  return fetch(path, { ...options, headers: { ...headers, ...(options.headers || {}) } });
};

// ═══════════════ THREE.JS BACKGROUND ════════════════

function initThreeBackground() {
  const canvas = document.getElementById('bgCanvas');
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(window.innerWidth, window.innerHeight);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
  camera.position.z = 30;

  const count = 800;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(count * 3);
  const sizes = new Float32Array(count);
  const colors = new Float32Array(count * 3);

  const palette = [
    new THREE.Color('#7c3aed'), new THREE.Color('#06b6d4'),
    new THREE.Color('#f59e0b'), new THREE.Color('#10b981'),
  ];

  for (let i = 0; i < count; i++) {
    positions[i*3] = (Math.random() - 0.5) * 120;
    positions[i*3+1] = (Math.random() - 0.5) * 80;
    positions[i*3+2] = (Math.random() - 0.5) * 60;
    sizes[i] = Math.random() * 2.5 + 0.5;
    const c = palette[Math.floor(Math.random() * palette.length)];
    colors[i*3] = c.r; colors[i*3+1] = c.g; colors[i*3+2] = c.b;
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  const material = new THREE.PointsMaterial({ size: 0.5, vertexColors: true, transparent: true, opacity: 0.4, sizeAttenuation: true });
  const particles = new THREE.Points(geometry, material);
  scene.add(particles);

  const lineMat = new THREE.LineBasicMaterial({ color: 0x7c3aed, transparent: true, opacity: 0.07 });
  const lineGeo = new THREE.BufferGeometry();
  const linePositions = [];
  for (let i = 0; i < 60; i++) {
    linePositions.push(
      (Math.random()-0.5)*120, (Math.random()-0.5)*80, (Math.random()-0.5)*60,
      (Math.random()-0.5)*120, (Math.random()-0.5)*80, (Math.random()-0.5)*60
    );
  }
  lineGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(linePositions), 3));
  const lines = new THREE.LineSegments(lineGeo, lineMat);
  scene.add(lines);

  let mouse = { x: 0, y: 0 };
  document.addEventListener('mousemove', e => {
    mouse.x = (e.clientX / window.innerWidth - 0.5) * 2;
    mouse.y = -(e.clientY / window.innerHeight - 0.5) * 2;
  });

  let frame = 0;
  function animate() {
    requestAnimationFrame(animate);
    frame += 0.004;
    particles.rotation.y = frame * 0.08 + mouse.x * 0.15;
    particles.rotation.x = frame * 0.03 + mouse.y * 0.08;
    lines.rotation.y = frame * 0.05;
    renderer.render(scene, camera);
  }
  animate();

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });
}

// ═══════════════ AUTH ════════════════

function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach((b, i) => b.classList.toggle('active', (i === 0) === (tab === 'login')));
  document.getElementById('loginForm').classList.toggle('hidden', tab !== 'login');
  document.getElementById('registerForm').classList.toggle('hidden', tab === 'login');
  setError('');
}

function setError(msg) {
  const el = document.getElementById('authError');
  el.textContent = msg;
  el.classList.toggle('hidden', !msg);
}

async function doLogin() {
  const username = document.getElementById('loginUser').value.trim();
  const password = document.getElementById('loginPass').value;
  if (!username || !password) { setError('Please fill all fields'); return; }
  try {
    const r = await API('/api/login', { method: 'POST', body: JSON.stringify({ username, password }) });
    const data = await r.json();
    if (!r.ok) { setError(data.error || 'Login failed'); return; }
    await onSuccess(data.token, data.user);
  } catch (e) { setError('Connection failed. Check server.'); }
}

async function doRegister() {
  const display_name = document.getElementById('regName').value.trim();
  const username = document.getElementById('regUser').value.trim();
  const password = document.getElementById('regPass').value;
  const language = document.getElementById('regLang').value;
  if (!display_name || !username || !password) { setError('Please fill all fields'); return; }
  try {
    const r = await API('/api/register', { method: 'POST', body: JSON.stringify({ display_name, username, password, language }) });
    const data = await r.json();
    if (!r.ok) { setError(data.error || 'Registration failed'); return; }
    await onSuccess(data.token, data.user);
  } catch (e) { setError('Connection failed. Check server.'); }
}

async function onSuccess(token, user) {
  State.token = token;
  State.me = user;
  localStorage.setItem('chat_token', token);
  localStorage.setItem('chat_user', JSON.stringify(user));
  document.getElementById('authScreen').className = 'screen hidden';
  document.getElementById('appScreen').className = 'screen active';
  initApp();
}

function doLogout() {
  localStorage.clear();
  location.reload();
}

// ═══════════════ APP INIT & PROFILE ════════════════

function initApp() {
  try {
    const myAv = document.getElementById('myAvatarInitials');
    if (myAv) myAv.textContent = (State.me.display_name[0] || '?').toUpperCase();
    const myAvEl = document.getElementById('myAvatar');
    if (myAvEl) myAvEl.style.background = State.me.avatar_color;
    const myDN = document.getElementById('myDisplayName');
    if (myDN) myDN.textContent = State.me.display_name;
    const myUN = document.getElementById('myUsername');
    if (myUN) myUN.textContent = '@' + State.me.username;
    const myST = document.getElementById('myStatusText');
    if (myST) myST.textContent = State.me.status_text || 'Available';

    const sa = document.getElementById('settingsAvatarInitials');
    if (sa) sa.textContent = (State.me.display_name[0] || '?').toUpperCase();
    const saEl = document.getElementById('settingsAvatar');
    if (saEl) saEl.style.background = State.me.avatar_color;
    const sUN = document.getElementById('settingsUsername');
    if (sUN) sUN.textContent = '@' + State.me.username;
    
    // Load settings into DOM (null-guarded)
    const subLang = document.getElementById('subtitleLang');
    if (subLang) subLang.value = State.subtitleLang;
    const pst = document.getElementById('profileStatusText');
    if (pst) pst.value = State.me.status_text || 'Available';
    const pbio = document.getElementById('profileBio');
    if (pbio) pbio.value = State.me.bio || '';
    const ppub = document.getElementById('profileIsPublic');
    if (ppub) ppub.checked = State.me.is_public || false;
    if(State.me.custom_theme) {
      const ct = document.getElementById('chatTheme');
      if (ct) ct.value = State.me.custom_theme;
      previewTheme(State.me.custom_theme);
    }
  } catch(e) {
    console.error('[initApp] Error during UI setup:', e);
  }

  connectWebSocket();
  loadRooms();
  loadFriends();
}

async function saveProfile() {
  const bio = document.getElementById('profileBio').value;
  const status_text = document.getElementById('profileStatusText').value;
  const is_public = document.getElementById('profileIsPublic').checked;
  const custom_theme = document.getElementById('chatTheme').value;

  try {
    await API('/api/profile', {
      method: 'POST',
      body: JSON.stringify({ bio, is_public, status_text, custom_theme })
    });
    // Update local state
    State.me.bio = bio;
    State.me.is_public = is_public;
    State.me.status_text = status_text;
    State.me.custom_theme = custom_theme;
    localStorage.setItem('chat_user', JSON.stringify(State.me));
    
    document.getElementById('myStatusText').textContent = status_text;
    const msg = document.getElementById('profileSaveMsg');
    msg.classList.remove('hidden');
    setTimeout(() => msg.classList.add('hidden'), 3000);
  } catch(e) { console.error('Failed to save profile', e); }
}

function previewTheme(themeName) {
  document.body.className = `theme-${themeName}`;
}

// ═══════════════ WEBSOCKET ════════════════

function connectWebSocket() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${proto}//${location.host}/ws?token=${State.token}`;
  State.ws = new WebSocket(wsUrl);

  State.ws.onmessage = e => {
    try { handleServerMessage(JSON.parse(e.data)); }
    catch {}
  };
  State.ws.onclose = () => { setTimeout(connectWebSocket, 3000); };

  State.ws.onopen = async () => {
    const pubKey = await getMyPublicKey();
    if (pubKey) {
      await API('/api/pubkey', { method: 'POST', body: JSON.stringify({ public_key: pubKey }) });
    }
  };
}

function wsSend(data) {
  if (State.ws && State.ws.readyState === WebSocket.OPEN) {
    State.ws.send(JSON.stringify(data));
  }
}

// ═══════════════ MESSAGE HANDLING ════════════════

function handleServerMessage(msg) {
  switch (msg.type) {
    case 'new_message':
      if (State.currentRoom && msg.room_id === State.currentRoom) {
        appendMessage(msg, msg.sender_id === State.me.id);
        markChatRead(); // We are actively looking at it
      }
      playNotificationSound();
      break;
    case 'messages_read':
      if (State.currentRoom === msg.room_id) {
        document.querySelectorAll('.msg-status-tick').forEach(el => el.classList.add('read'));
      }
      break;
    case 'status_update':
      updateUserStatus(msg.user_id, msg.status_text);
      break;
    case 'presence':
      updatePresence(msg.user_id, msg.online);
      break;
    case 'typing':
      showTyping(msg.sender_id);
      break;
    case 'subtitle':
      showSubtitle(msg.text);
      break;
    case 'call_offer':
      showIncomingCall(msg);
      break;
    case 'call_answer':
      handleCallAnswer(msg.sdp);
      break;
    case 'ice_candidate':
      handleICE(msg.candidate);
      break;
    case 'call_end':
      endCall();
      break;
  }
}

// ═══════════════ E2E ENCRYPTION ════════════════

let _myKeyPair = null;
async function getOrCreateKeyPair() {
  if (_myKeyPair) return _myKeyPair;
  const stored = localStorage.getItem('my_keypair');
  if (stored) {
    const { priv, pub } = JSON.parse(stored);
    const privateKey = await crypto.subtle.importKey('pkcs8', b64ToBuffer(priv), { name: 'ECDH', namedCurve: 'P-256' }, false, ['deriveKey']);
    const publicKey = await crypto.subtle.importKey('spki', b64ToBuffer(pub), { name: 'ECDH', namedCurve: 'P-256' }, true, []);
    _myKeyPair = { privateKey, publicKey };
    return _myKeyPair;
  }
  _myKeyPair = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveKey']);
  const privExported = bufferToB64(await crypto.subtle.exportKey('pkcs8', _myKeyPair.privateKey));
  const pubExported = bufferToB64(await crypto.subtle.exportKey('spki', _myKeyPair.publicKey));
  localStorage.setItem('my_keypair', JSON.stringify({ priv: privExported, pub: pubExported }));
  return _myKeyPair;
}

async function getMyPublicKey() {
  try {
    const kp = await getOrCreateKeyPair();
    const exported = await crypto.subtle.exportKey('spki', kp.publicKey);
    return bufferToB64(exported);
  } catch { return null; }
}

async function getSharedKey(peerUserId) {
  if (peerUserId === 'nomad_agent') return null; // Agent communicates unencrypted text base64
  if (State.sessionKeys[peerUserId]) return State.sessionKeys[peerUserId];
  try {
    const r = await API(`/api/users/${peerUserId}/pubkey`);
    const { public_key } = await r.json();
    if (!public_key) return null;
    const peerPub = await crypto.subtle.importKey('spki', b64ToBuffer(public_key), { name: 'ECDH', namedCurve: 'P-256' }, false, []);
    const kp = await getOrCreateKeyPair();
    const sharedKey = await crypto.subtle.deriveKey(
      { name: 'ECDH', public: peerPub }, kp.privateKey, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']
    );
    State.sessionKeys[peerUserId] = sharedKey;
    return sharedKey;
  } catch { return null; }
}

async function encryptMessage(text, peerUserId) {
  const key = await getSharedKey(peerUserId);
  if (!key) return btoa(text); // Fallback unencrypted for agent / missing pubkey
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const enc = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(text));
  const combined = new Uint8Array(iv.byteLength + enc.byteLength);
  combined.set(iv, 0); combined.set(new Uint8Array(enc), iv.byteLength);
  return bufferToB64(combined.buffer);
}

async function decryptMessage(encB64, peerUserId) {
  if (peerUserId === 'nomad_agent' || encB64.startsWith('🤔')) return encB64; // Agent sends raw text

  const key = await getSharedKey(peerUserId);
  if (!key) { try { return atob(encB64); } catch { return '[Encrypted]'; } }
  try {
    const combined = b64ToBuffer(encB64);
    const iv = combined.slice(0, 12);
    const data = combined.slice(12);
    const dec = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: new Uint8Array(iv) }, key, data);
    return new TextDecoder().decode(dec);
  } catch { return '[Encrypted message]'; }
}

function bufferToB64(buf) { return btoa(String.fromCharCode(...new Uint8Array(buf))); }
function b64ToBuffer(b64) {
  const bin = atob(b64); const buf = new ArrayBuffer(bin.length);
  const view = new Uint8Array(buf); for (let i = 0; i < bin.length; i++) view[i] = bin.charCodeAt(i);
  return buf;
}

// ═══════════════ ROOMS, FRIENDS + MESSAGES ════════════════

// switchSidebarTab is defined in the FEED & STICKERS section below (line ~940)

async function loadRooms() {
  try {
    const r = await API('/api/rooms');
    const data = await r.json();
    const rooms = data.rooms || [];
    const list = document.getElementById('conversationsList');
    list.innerHTML = '';
    
    // Always add NOMAD Agent to top (even with 0 rooms)
    addConvoItem({
      id: 'nomad_agent_room', user_a: State.me.id, user_b: 'nomad_agent',
      username: 'nomad_agent', display_name: '🛡️ NOMAD Agent', avatar_color: '#06b6d4', online: 1, status_text: 'Ready to assist'
    });

    rooms.forEach(room => addConvoItem(room));
  } catch(e) {
    console.error('[loadRooms] Error:', e);
    // Still show the agent even if API fails
    const list = document.getElementById('conversationsList');
    if (list) {
      list.innerHTML = '';
      addConvoItem({
        id: 'nomad_agent_room', user_a: State.me?.id || '', user_b: 'nomad_agent',
        username: 'nomad_agent', display_name: '🛡️ NOMAD Agent', avatar_color: '#06b6d4', online: 1, status_text: 'Ready to assist'
      });
    }
  }
}

async function loadFriends() {
  try {
    const r = await API('/api/friends');
    const { friends } = await r.json();
    const list = document.getElementById('friendsList');
    if (!friends || friends.length === 0) {
      list.innerHTML = '<div class="empty-state"><div class="empty-icon">👥</div><p>No friends yet</p><small>Search to find people</small></div>';
      return;
    }
    list.innerHTML = '';
    friends.forEach(f => {
      const div = document.createElement('div');
      div.className = 'convo-item';
      div.innerHTML = `
        <div class="user-avatar medium" style="background:${f.avatar_color}">
          <span>${f.display_name[0].toUpperCase()}</span>
          ${f.online ? '<div class="online-dot"></div>' : ''}
        </div>
        <div class="convo-info">
          <div class="convo-name">${f.display_name}</div>
          <div class="convo-last-msg">${f.status_text || '@'+f.username}</div>
        </div>
      `;
      div.onclick = () => openChat({ id: f.id, username: f.username, display_name: f.display_name, avatar_color: f.avatar_color, online: f.online, status_text: f.status_text });
      list.appendChild(div);
    });
  } catch {}
}

function addConvoItem(room) {
  const list = document.getElementById('conversationsList');
  const div = document.createElement('div');
  div.className = 'convo-item';
  div.id = `convo_${room.id}`;
  div.innerHTML = `
    <div class="user-avatar medium" style="background:${room.avatar_color}">
      <span>${room.display_name[0].toUpperCase()}</span>
      ${room.online ? '<div class="online-dot"></div>' : ''}
    </div>
    <div class="convo-info">
      <div class="convo-name">${room.display_name}</div>
      <div class="convo-last-msg">${room.status_text || '@'+room.username}</div>
    </div>
  `;
  const peerId = room.id === 'nomad_agent_room' ? 'nomad_agent' : (room.user_a === State.me.id ? room.user_b : room.user_a);
  div.onclick = () => openChat({ id: peerId, username: room.username, display_name: room.display_name, avatar_color: room.avatar_color, online: room.online, status_text: room.status_text, room_id: room.id });
  list.appendChild(div);
}

async function openChat(peer) {
  State.currentPeer = peer;
  State.currentRoom = peer.room_id || (peer.id === 'nomad_agent' ? 'nomad_agent_room' : await ensureRoom(peer.id));

  const ca = document.getElementById('chatAvatarInitials');
  if (ca) ca.textContent = peer.display_name[0].toUpperCase();
  document.getElementById('chatAvatar').style.background = peer.avatar_color;
  document.getElementById('chatDisplayName').textContent = peer.display_name;
  document.getElementById('chatStatus').textContent = peer.status_text || (peer.online ? '🟢 Online' : '⚫ Offline');
  
  // Status Ring animation for active statuses
  const ring = document.getElementById('chatStatusRing');
  ring.className = `status-ring ${peer.online ? 'active' : ''}`;

  document.getElementById('chatWelcome').classList.add('hidden');
  document.getElementById('chatRoom').classList.remove('hidden');
  document.querySelector('.sidebar').classList.add('hidden-mobile');

  const area = document.getElementById('messagesArea');
  area.innerHTML = '<div class="messages-loader">Loading...</div>';

  if (peer.id === 'nomad_agent') {
    area.innerHTML = '';
    renderMessage({ id:'init', timestamp: Date.now()/1000, is_agent: true, is_read: 1 }, "I am the NOMAD intelligence swarm. Try typing commands like /status or /generate_video", false);
    return;
  }

  try {
    const r = await API(`/api/rooms/${State.currentRoom}/messages`);
    const { messages } = await r.json();
    area.innerHTML = '';
    for (const msg of messages) {
      const isSent = msg.sender_id === State.me.id;
      const text = await decryptMessage(msg.encrypted_content, isSent ? State.currentPeer.id : msg.sender_id);
      renderMessage(msg, text, isSent);
    }
    area.scrollTop = area.scrollHeight;
    markChatRead();
  } catch { area.innerHTML = ''; }
}

async function ensureRoom(peerId) {
  try {
    const r = await API('/api/rooms');
    const { rooms } = await r.json();
    const sorted = [State.me.id, peerId].sort();
    const existing = rooms.find(rm => rm.user_a === sorted[0] && rm.user_b === sorted[1]);
    if (existing) return existing.id;
  } catch {}
  return `room_${[State.me.id, peerId].sort().join('_')}`;
}

function closeChat() {
  document.querySelector('.sidebar').classList.remove('hidden-mobile');
  document.getElementById('chatWelcome').classList.remove('hidden');
  document.getElementById('chatRoom').classList.add('hidden');
  State.currentRoom = null;
  State.currentPeer = null;
}

function appendMessage(msg, isSent) {
  const area = document.getElementById('messagesArea');
  const peerIdForDecrypt = isSent ? State.currentPeer.id : msg.sender_id;
  decryptMessage(msg.encrypted_content, peerIdForDecrypt).then(text => {
    renderMessage(msg, text, isSent);
    area.scrollTop = area.scrollHeight;
  });
}

function renderMessage(msg, text, isSent) {
  const area = document.getElementById('messagesArea');
  const div = document.createElement('div');
  const cssClass = isSent ? 'sent' : 'received';
  const privateClass = msg.is_private ? ' private-msg' : '';
  const agentClass = msg.is_agent ? ' agent-msg' : '';
  div.className = `message-bubble ${cssClass}${privateClass}${agentClass}`;
  
  const time = new Date(msg.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const tickClass = msg.is_read ? 'msg-status-tick read' : 'msg-status-tick';
  
  if (msg.message_type === 'image') {
    div.innerHTML = `<img src="${text}" class="msg-image" alt="Image" /><div class="msg-time">${isSent ? `<span class="${tickClass}">✓✓</span> ` : ''}${time}</div>`;
  } else {
    div.innerHTML = `<span>${escapeHtml(text)}</span><div class="msg-time">${isSent ? `<span class="${tickClass}">✓✓</span> ` : ''}${time}</div>`;
  }
  area.appendChild(div);
}

function playNotificationSound() { }
function escapeHtml(str) { return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function markChatRead() {
  if(State.currentRoom && State.currentPeer) {
    wsSend({ type: 'mark_read', room_id: State.currentRoom, recipient_id: State.currentPeer.id });
  }
}

// ═══════════════ SEND MESSAGE ════════════════

async function sendMessage() {
  const input = document.getElementById('messageInput');
  const text = input.value.trim();
  if (!text || !State.currentPeer) return;
  input.value = '';
  input.style.height = 'auto';

  if (State.currentPeer.id === 'nomad_agent') {
    // Send to agent backend handler
    wsSend({ type: 'agent_command', text: text, room_id: State.currentRoom });
    renderMessage({ id: 'local_cmd', timestamp: Date.now()/1000, is_read: 1 }, text, true);
    return;
  }

  const encrypted = await encryptMessage(text, State.currentPeer.id);
  wsSend({
    type: 'send_message',
    recipient_id: State.currentPeer.id,
    encrypted_content: encrypted,
    message_type: 'text'
  });
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

let typingTimeout;
function handleTyping() {
  const ta = document.getElementById('messageInput');
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  
  if (ta.value.length > 0 && State.currentPeer && State.currentPeer.id !== 'nomad_agent') {
    wsSend({ type: 'typing', recipient_id: State.currentPeer.id });
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {}, 2000);
  }
}

let typingTimer;
function showTyping(senderId) {
  if (!State.currentPeer || senderId !== State.currentPeer.id) return;
  const ind = document.getElementById('typingIndicator');
  document.getElementById('typingName').textContent = State.currentPeer.display_name;
  ind.classList.remove('hidden');
  clearTimeout(typingTimer);
  typingTimer = setTimeout(() => ind.classList.add('hidden'), 2500);
}

// ═══════════════ SOCIAL & IMAGE ════════════════

function attachImage() { document.getElementById('imageInput').click(); }

function sendImageFile(input) {
  const file = input.files[0];
  if (!file || !State.currentPeer) return;
  const reader = new FileReader();
  reader.onload = async e => {
    // For large images, we use base64 (encrypted) directly right now.
    // In production, E2E files should use WebRTC data channels or chunks!
    const dataUrl = e.target.result;
    const encrypted = await encryptMessage(dataUrl, State.currentPeer.id);
    wsSend({ type: 'send_message', recipient_id: State.currentPeer.id, encrypted_content: encrypted, message_type: 'image' });
  };
  reader.readAsDataURL(file);
  input.value = '';
}

async function addCurrentPeerFriend() {
  if(State.currentPeer && State.currentPeer.id !== 'nomad_agent') {
    await API('/api/friends', { method: 'POST', body: JSON.stringify({ friend_id: State.currentPeer.id }) });
    alert(`Added ${State.currentPeer.display_name} as a friend!`);
  }
}

// ═══════════════ SEARCH ════════════════

function openSearch() {
  const sb = document.getElementById('searchBar');
  sb.classList.toggle('hidden');
  if (!sb.classList.contains('hidden')) {
    document.getElementById('searchInput').focus();
    searchUsers(''); // Load public users immediately
  }
}

let searchTimeout;
function searchUsers(q) {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(async () => {
    try {
      const r = await API(`/api/search?q=${encodeURIComponent(q.trim())}`);
      const { users } = await r.json();
      const results = document.getElementById('searchResults');
      results.innerHTML = '';
      users.forEach(u => {
        const div = document.createElement('div');
        div.className = 'search-result-item';
        div.innerHTML = `
          <div class="user-avatar small" style="background:${u.avatar_color}">
            ${u.display_name[0].toUpperCase()}
            ${u.online ? '<div class="online-dot" style="bottom: -2px; right: -2px"></div>' : ''}
          </div>
          <div style="flex:1">
            <div class="display-name">${u.display_name}</div>
            <div class="search-bio">${u.bio || '@'+u.username}</div>
          </div>
        `;
        div.onclick = () => {
          openChat(u);
          document.getElementById('searchBar').classList.add('hidden');
          loadRooms();
        };
        results.appendChild(div);
      });
    } catch {}
  }, 350);
}

// ═══════════════ SETTINGS & Presence Updates ════════════════

function openSettings() { document.getElementById('settingsModal').classList.remove('hidden'); }
function closeSettings() { document.getElementById('settingsModal').classList.add('hidden'); }
function setSubtitleLang(lang) { State.subtitleLang = lang; localStorage.setItem('subtitle_lang', lang); }

function togglePrivateMode(enabled) {
  State.privateMode = enabled;
  wsSend({ type: 'set_private_mode', enabled });
  const badge = document.getElementById('privateBadge');
  if (badge) badge.style.display = enabled ? 'block' : 'none';
  document.body.style.setProperty('--accent', enabled ? '#f59e0b' : '#7c3aed');
}

function openChatSettings() { openSettings(); }

function updatePresence(userId, online) {
  document.querySelectorAll(`.user-avatar`).forEach(av => {
    if (av.dataset.userId === userId) {
        // ... handled in react/renders mostly
    }
  });
  if (State.currentPeer?.id === userId) {
    document.getElementById('chatStatus').textContent = online ? '🟢 Online' : '⚫ Offline';
    const ring = document.getElementById('chatStatusRing');
    if(ring) ring.className = `status-ring ${online ? 'active' : ''}`;
  }
}

function updateUserStatus(userId, statusText) {
  if (State.currentPeer?.id === userId) {
    const el = document.getElementById('chatStatus');
    if(el) el.textContent = statusText;
  }
}

// ═══════════════ WEBRTC VIDEO CALLS (Phase 8 HD + Filters) ════════════════

const ICE_SERVERS = [{ urls: 'stun:stun.l.google.com:19302' }];

async function startVideoCall(voiceOnly = false) {
  if (!State.currentPeer || State.currentPeer.id === 'nomad_agent') return;
  const overlay = document.getElementById('callOverlay');
  overlay.classList.remove('hidden');
  const ca = document.getElementById('callAvatar');
  ca.textContent = State.currentPeer.display_name[0].toUpperCase();
  ca.style.background = State.currentPeer.avatar_color;
  document.getElementById('callDisplayName').textContent = State.currentPeer.display_name;
  
  if (State.privateMode) document.getElementById('privateBadge').style.display = 'block';
  document.getElementById('hdBadge').style.display = 'block';

  try {
    // HD Constraints for Adaptive bitrate
    State.localStream = await navigator.mediaDevices.getUserMedia({ 
      video: voiceOnly ? false : { width: { ideal: 1280 }, height: { ideal: 720 } }, 
      audio: true 
    });
    document.getElementById('localVideo').srcObject = State.localStream;
  } catch (e) {
    alert('Could not access camera/microphone: ' + e.message);
    endCall(); return;
  }

  State.peerConnection = new RTCPeerConnection({ iceServers: ICE_SERVERS });
  State.localStream.getTracks().forEach(t => State.peerConnection.addTrack(t, State.localStream));

  State.peerConnection.ontrack = e => {
    document.getElementById('remoteVideo').srcObject = e.streams[0];
  };
  State.peerConnection.onicecandidate = e => {
    if (e.candidate) wsSend({ type: 'ice_candidate', recipient_id: State.currentPeer.id, candidate: e.candidate });
  };

  const offer = await State.peerConnection.createOffer();
  await State.peerConnection.setLocalDescription(offer);
  wsSend({ type: 'call_offer', recipient_id: State.currentPeer.id, sdp: offer, voice_only: voiceOnly });

  startCallTimer();
  if (!State.privateMode) startSubtitles();
}

function startVoiceCall() { startVideoCall(true); }

function showIncomingCall(data) {
  State.incomingCallData = data;
  const inc = document.getElementById('incomingCall');
  inc.classList.remove('hidden');
  const ca = document.getElementById('callerAvatar');
  ca.textContent = '📞';
  document.getElementById('callerName').textContent = 'Incoming Secure Call';
  document.getElementById('callOverlay').classList.remove('hidden');
}

async function acceptCall() {
  const data = State.incomingCallData;
  if (!data) return;
  document.getElementById('incomingCall').classList.add('hidden');
  
  try {
    State.localStream = await navigator.mediaDevices.getUserMedia({ 
      video: data.voice_only ? false : { width: { ideal: 1280 }, height: { ideal: 720 } }, 
      audio: true 
    });
    document.getElementById('localVideo').srcObject = State.localStream;
  } catch { endCall(); return; }

  State.peerConnection = new RTCPeerConnection({ iceServers: ICE_SERVERS });
  State.localStream.getTracks().forEach(t => State.peerConnection.addTrack(t, State.localStream));
  State.peerConnection.ontrack = e => { document.getElementById('remoteVideo').srcObject = e.streams[0]; };
  State.peerConnection.onicecandidate = e => {
    if (e.candidate) wsSend({ type: 'ice_candidate', recipient_id: data.sender_id, candidate: e.candidate });
  };

  await State.peerConnection.setRemoteDescription(new RTCSessionDescription(data.sdp));
  const answer = await State.peerConnection.createAnswer();
  await State.peerConnection.setLocalDescription(answer);
  wsSend({ type: 'call_answer', recipient_id: data.sender_id, sdp: answer });
  startCallTimer();
  document.getElementById('hdBadge').style.display = 'block';
}

function rejectCall() {
  if (State.incomingCallData) wsSend({ type: 'call_end', recipient_id: State.incomingCallData.sender_id });
  document.getElementById('incomingCall').classList.add('hidden');
  document.getElementById('callOverlay').classList.add('hidden');
  State.incomingCallData = null;
}

async function handleCallAnswer(sdp) {
  if (State.peerConnection) await State.peerConnection.setRemoteDescription(new RTCSessionDescription(sdp));
}

async function handleICE(candidate) {
  if (State.peerConnection) {
    try { await State.peerConnection.addIceCandidate(new RTCIceCandidate(candidate)); } catch {}
  }
}

function endCall() {
  if (State.peerConnection) { State.peerConnection.close(); State.peerConnection = null; }
  if (State.localStream) { State.localStream.getTracks().forEach(t => t.stop()); State.localStream = null; }
  if (State.recognition) { State.recognition.stop(); State.recognition = null; }
  clearInterval(State.callTimer);
  State.callSeconds = 0;
  document.getElementById('callOverlay').classList.add('hidden');
  document.getElementById('incomingCall').classList.add('hidden');
  document.getElementById('remoteVideo').srcObject = null;
  document.getElementById('localVideo').srcObject = null;
  document.getElementById('subtitleBar').style.display = 'none';
  document.getElementById('privateBadge').style.display = 'none';
  document.getElementById('hdBadge').style.display = 'none';
  setVideoFilter('none');
  if (State.currentPeer) wsSend({ type: 'call_end', recipient_id: State.currentPeer.id });
}

function toggleMute() {
  State.isMuted = !State.isMuted;
  if (State.localStream) State.localStream.getAudioTracks().forEach(t => t.enabled = !State.isMuted);
  document.getElementById('muteBtn').textContent = State.isMuted ? '🔇' : '🎙️';
}

function toggleVideo() {
  State.videoOff = !State.videoOff;
  if (State.localStream) State.localStream.getVideoTracks().forEach(t => t.enabled = !State.videoOff);
  document.getElementById('videoBtn').textContent = State.videoOff ? '📷' : '📹';
}

function toggleSubtitles() {
  State.subtitlesOn = !State.subtitlesOn;
  const bar = document.getElementById('subtitleBar');
  if (!State.subtitlesOn) { bar.style.display = 'none'; stopSubtitles(); }
  else if (!State.privateMode) startSubtitles();
}

function toggleVideoFilters() {
  document.getElementById('videoFiltersList').classList.toggle('visible');
}

function setVideoFilter(filterName) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  const className = filterName === 'none' ? '' : `filter-${filterName}`;
  document.getElementById('localVideo').className = `local-video ${className}`;
  document.getElementById('remoteVideo').className = `remote-video ${className}`;
}

function startCallTimer() {
  State.callSeconds = 0;
  const el = document.getElementById('callTimer');
  State.callTimer = setInterval(() => {
    State.callSeconds++;
    const m = Math.floor(State.callSeconds / 60).toString().padStart(2, '0');
    const s = (State.callSeconds % 60).toString().padStart(2, '0');
    el.textContent = `${m}:${s}`;
  }, 1000);
}

// ═══════════════ LIVE SUBTITLES (Web Speech API) ════════════════

function startSubtitles() {
  if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) return;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  State.recognition = new SpeechRecognition();
  State.recognition.continuous = true;
  State.recognition.interimResults = true;
  State.recognition.lang = State.me.language || 'en-US';

  State.recognition.onresult = e => {
    let final = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) final += e.results[i][0].transcript;
    }
    if (final && !State.privateMode && State.currentPeer && State.currentPeer.id !== 'nomad_agent') {
      wsSend({
        type: 'translate_subtitle',
        text: final,
        from_lang: State.me.language || 'en',
        to_lang: State.subtitleLang,
        room_id: State.currentRoom,
        recipient_id: State.currentPeer.id
      });
    }
  };
  State.recognition.onerror = () => { setTimeout(startSubtitles, 2000); };
  State.recognition.start();
  document.getElementById('subtitleBar').style.display = 'block';
}

function stopSubtitles() {
  if (State.recognition) { try { State.recognition.stop(); } catch {} State.recognition = null; }
}

let subtitleTimer;
function showSubtitle(text) {
  const bar = document.getElementById('subtitleBar');
  if (!State.subtitlesOn) return;
  bar.textContent = text;
  bar.style.display = 'block';
  clearTimeout(subtitleTimer);
  subtitleTimer = setTimeout(() => { bar.style.display = 'none'; }, 4000);
}

// ═══════════════ FEED & STICKERS ════════════════

function switchSidebarTab(tab) {
  document.querySelectorAll('.sidebar-tab').forEach(b => b.classList.remove('active'));
  document.querySelector(`.sidebar-tab[onclick*="${tab}"]`).classList.add('active');
  
  document.getElementById('conversationsList').classList.add('hidden');
  document.getElementById('friendsList').classList.add('hidden');
  document.getElementById('searchBar').classList.add('hidden');
  
  if(tab === 'chats') {
    document.getElementById('conversationsList').classList.remove('hidden');
    document.getElementById('feedArea').classList.add('hidden');
    document.getElementById('chatWelcome').classList.remove('hidden');
    document.getElementById('chatRoom').classList.add('hidden');
  } else if(tab === 'friends') {
    document.getElementById('friendsList').classList.remove('hidden');
    document.getElementById('feedArea').classList.add('hidden');
    document.getElementById('chatWelcome').classList.remove('hidden');
    document.getElementById('chatRoom').classList.add('hidden');
  } else if(tab === 'feed') {
    document.getElementById('chatWelcome').classList.add('hidden');
    document.getElementById('chatRoom').classList.add('hidden');
    document.getElementById('feedArea').classList.remove('hidden');
    loadGlobalFeed();
  }
}

// Global Feed Logic — Instagram-Identical Rendering
const postLikes = {}; // Track liked posts locally

async function loadGlobalFeed() {
  const list = document.getElementById('feedList');
  list.innerHTML = '<div class="messages-loader">Loading feed...</div>';
  
  // Set feed avatar
  const fa = document.getElementById('feedAvatarInit');
  if (fa && State.me) fa.textContent = (State.me.display_name[0] || '?').toUpperCase();
  const faEl = document.getElementById('feedAvatar');
  if (faEl && State.me) faEl.style.background = State.me.avatar_color;
  
  try {
    const r = await API('/api/posts');
    const { posts } = await r.json();
    list.innerHTML = '';
    if(posts.length === 0) {
      list.innerHTML = '<div class="empty-state" style="padding:60px 20px;"><div class="empty-icon">📸</div><p>No posts yet</p><small>Share your first photo or thought!</small></div>';
      return;
    }
    posts.forEach(p => renderIGPost(p, list));
  } catch(e) { list.innerHTML = '<div class="error-msg">Failed to load feed. Check connection.</div>'; }
}

function renderIGPost(p, container) {
  const timeAgo = getTimeAgo(p.timestamp);
  const postId = p.id || Math.random().toString(36).substr(2, 9);
  const isLiked = postLikes[postId] || false;
  const likeCount = (p.likes || Math.floor(Math.random() * 50)) + (isLiked ? 1 : 0);
  const commentCount = p.comments || 0;
  
  const card = document.createElement('div');
  card.className = 'ig-post';
  card.id = `post-${postId}`;
  
  // Media section
  let mediaHtml = '';
  if (p.media_url) {
    if (p.media_url.startsWith('data:video')) {
      mediaHtml = `
        <div class="ig-post-media-container" ondblclick="doubleTapLike('${postId}', this)">
          <video src="${p.media_url}" controls playsinline preload="metadata"></video>
          <div class="ig-heart-anim" id="heart-${postId}">❤️</div>
        </div>`;
    } else {
      mediaHtml = `
        <div class="ig-post-media-container" ondblclick="doubleTapLike('${postId}', this)">
          <img src="${p.media_url}" alt="Post by ${p.display_name}" loading="lazy" />
          <div class="ig-heart-anim" id="heart-${postId}">❤️</div>
        </div>`;
    }
  } else if (p.content) {
    // Text-only post with gradient background
    mediaHtml = `<div class="ig-post-text-only">${escapeHtml(p.content)}</div>`;
  }
  
  // Caption (only show separately if there's also media)
  const captionHtml = (p.content && p.media_url) ? `
    <div class="ig-post-caption">
      <span class="caption-name">${escapeHtml(p.display_name)}</span>
      <span class="caption-text">${escapeHtml(p.content)}</span>
    </div>` : '';
  
  card.innerHTML = `
    <div class="ig-post-header">
      <div class="user-avatar small" style="background:${p.avatar_color || 'var(--accent)'}">
        <span>${(p.display_name || '?')[0].toUpperCase()}</span>
      </div>
      <div class="ig-post-user-info">
        <div class="display-name">${escapeHtml(p.display_name)}</div>
        ${p.location ? `<div class="ig-post-location">${escapeHtml(p.location)}</div>` : ''}
      </div>
      <button class="ig-post-menu" title="More options">⋯</button>
    </div>
    
    ${mediaHtml}
    
    <div class="ig-post-actions">
      <button class="ig-action-btn ${isLiked ? 'liked' : ''}" id="like-btn-${postId}" onclick="toggleLike('${postId}')" title="Like">
        ${isLiked ? '❤️' : '🤍'}
      </button>
      <button class="ig-action-btn" onclick="focusComment('${postId}')" title="Comment">💬</button>
      <button class="ig-action-btn" title="Share">↗️</button>
      <button class="ig-action-btn ig-save-btn" onclick="toggleSave(this)" title="Save">🔖</button>
    </div>
    
    <div class="ig-post-likes" id="likes-${postId}">${likeCount.toLocaleString()} likes</div>
    
    ${captionHtml}
    
    ${commentCount > 0 ? `<div class="ig-post-comments-link">View all ${commentCount} comments</div>` : ''}
    
    <div class="ig-post-time">${timeAgo}</div>
    
    <div class="ig-post-add-comment">
      <span style="font-size:20px; cursor:pointer;">😊</span>
      <input type="text" id="comment-input-${postId}" placeholder="Add a comment..." onkeydown="if(event.key==='Enter')postComment('${postId}', this)" />
      <button class="ig-comment-post-btn" onclick="postComment('${postId}', document.getElementById('comment-input-${postId}'))">Post</button>
    </div>
  `;
  
  container.appendChild(card);
}

function getTimeAgo(timestamp) {
  const now = Date.now() / 1000;
  const diff = now - timestamp;
  if (diff < 60) return 'Just now';
  if (diff < 3600) return Math.floor(diff / 60) + ' minutes ago';
  if (diff < 86400) return Math.floor(diff / 3600) + ' hours ago';
  if (diff < 604800) return Math.floor(diff / 86400) + ' days ago';
  return new Date(timestamp * 1000).toLocaleDateString('en-US', { month: 'long', day: 'numeric' });
}

function toggleLike(postId) {
  const btn = document.getElementById(`like-btn-${postId}`);
  const likesEl = document.getElementById(`likes-${postId}`);
  const isLiked = postLikes[postId];
  
  postLikes[postId] = !isLiked;
  
  if (!isLiked) {
    btn.innerHTML = '❤️';
    btn.classList.add('liked');
    // Increment like count
    const current = parseInt(likesEl.textContent.replace(/[^0-9]/g, '')) || 0;
    likesEl.textContent = (current + 1).toLocaleString() + ' likes';
  } else {
    btn.innerHTML = '🤍';
    btn.classList.remove('liked');
    const current = parseInt(likesEl.textContent.replace(/[^0-9]/g, '')) || 0;
    likesEl.textContent = Math.max(0, current - 1).toLocaleString() + ' likes';
  }
}

function doubleTapLike(postId, container) {
  // Instagram double-tap like animation
  postLikes[postId] = true;
  const btn = document.getElementById(`like-btn-${postId}`);
  if (btn) { btn.innerHTML = '❤️'; btn.classList.add('liked'); }
  
  const heart = document.getElementById(`heart-${postId}`);
  if (heart) {
    heart.classList.remove('pop');
    void heart.offsetWidth; // Force reflow
    heart.classList.add('pop');
    setTimeout(() => heart.classList.remove('pop'), 900);
  }
  
  // Update like count
  const likesEl = document.getElementById(`likes-${postId}`);
  if (likesEl) {
    const current = parseInt(likesEl.textContent.replace(/[^0-9]/g, '')) || 0;
    likesEl.textContent = (current + 1).toLocaleString() + ' likes';
  }
}

function toggleSave(btn) {
  btn.classList.toggle('liked');
  btn.textContent = btn.classList.contains('liked') ? '📌' : '🔖';
}

function focusComment(postId) {
  const input = document.getElementById(`comment-input-${postId}`);
  if (input) input.focus();
}

function postComment(postId, input) {
  if (!input || !input.value.trim()) return;
  const comment = input.value.trim();
  input.value = '';
  // Find the post card and add a visual comment
  const post = document.getElementById(`post-${postId}`);
  if (post) {
    const captionArea = post.querySelector('.ig-post-caption') || post.querySelector('.ig-post-likes');
    if (captionArea) {
      const commentDiv = document.createElement('div');
      commentDiv.className = 'ig-post-caption';
      commentDiv.innerHTML = `<span class="caption-name">${escapeHtml(State.me.display_name)}</span><span class="caption-text">${escapeHtml(comment)}</span>`;
      captionArea.parentNode.insertBefore(commentDiv, captionArea.nextSibling);
    }
  }
}

// Video post preview
let currentPostVideoBase64 = null;
function previewPostVideo(input) {
  if (input.files && input.files[0]) {
    const file = input.files[0];
    if (file.size > 50 * 1024 * 1024) { alert('Video must be under 50MB'); return; }
    const reader = new FileReader();
    reader.onload = e => {
      currentPostVideoBase64 = e.target.result;
      const vid = document.getElementById('postVideoPreview');
      vid.src = currentPostVideoBase64;
      vid.style.display = 'block';
      // Hide image preview
      document.getElementById('postMediaPreview').style.display = 'none';
      currentPostMediaBase64 = null;
    };
    reader.readAsDataURL(file);
  }
}

let currentPostMediaBase64 = null;
function previewPostMedia(input) {
  if (input.files && input.files[0]) {
    const reader = new FileReader();
    reader.onload = e => {
      currentPostMediaBase64 = e.target.result;
      const img = document.getElementById('postMediaPreview');
      img.src = currentPostMediaBase64;
      img.style.display = 'block';
      // Hide video preview
      document.getElementById('postVideoPreview').style.display = 'none';
      currentPostVideoBase64 = null;
    };
    reader.readAsDataURL(input.files[0]);
  }
}

async function submitPost() {
  const content = document.getElementById('postContent').value.trim();
  const media = currentPostMediaBase64 || currentPostVideoBase64;
  if(!content && !media) return;
  try {
    await API('/api/posts', {
      method: 'POST',
      body: JSON.stringify({ content, media_url: media })
    });
    document.getElementById('postContent').value = '';
    document.getElementById('postContent').style.height = 'auto';
    document.getElementById('postMediaPreview').style.display = 'none';
    document.getElementById('postVideoPreview').style.display = 'none';
    currentPostMediaBase64 = null;
    currentPostVideoBase64 = null;
    loadGlobalFeed(); // Refresh
  } catch(e) { console.error('Failed to post'); }
}

// Avatar Logic (Convert Image to Base64 background)
function uploadAvatarImage(input) {
  if (input.files && input.files[0]) {
    const reader = new FileReader();
    reader.onload = e => {
      const b64 = e.target.result;
      document.getElementById('settingsAvatar').style.backgroundImage = `url(${b64})`;
      document.getElementById('settingsAvatar').textContent = '';
      document.getElementById('myAvatar').style.backgroundImage = `url(${b64})`;
      document.getElementById('myAvatar').textContent = '';
      
      // We will override State.me.avatar_color to hold the b64 string since CSS backgrounds support urls!
      State.me.avatar_color = `url(${b64})`;
    };
    reader.readAsDataURL(input.files[0]);
  }
}

// Stickers Logic
function toggleStickers() {
  document.getElementById('stickerDrawer').classList.toggle('visible');
}
function sendTextSticker(emoji) {
  document.getElementById('stickerDrawer').classList.remove('visible');
  if(!State.currentPeer) return;
  const input = document.getElementById('messageInput');
  input.value = emoji;
  sendMessage();
}
function uploadCustomSticker(input) {
  if (input.files && input.files[0]) {
    const reader = new FileReader();
    reader.onload = async e => {
      document.getElementById('stickerDrawer').classList.remove('visible');
      const b64 = e.target.result;
      if (State.currentPeer && State.currentPeer.id !== 'nomad_agent') {
        const encrypted = await encryptMessage(b64, State.currentPeer.id);
        wsSend({ type: 'send_message', recipient_id: State.currentPeer.id, encrypted_content: encrypted, message_type: 'image' });
      }
    };
    reader.readAsDataURL(input.files[0]);
  }
}

// ═══════════════ PWA SERVICE WORKER ════════════════

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// BOOT
if (document.getElementById('bgCanvas')) initThreeBackground();
if (State.token && State.me) {
  document.getElementById('authScreen').className = 'screen hidden';
  document.getElementById('appScreen').className = 'screen active';
  initApp();
}

