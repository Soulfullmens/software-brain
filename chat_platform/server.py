"""
server.py — NOMAD SecureChat Backend Server

aiohttp WebSocket server.
Features:
- User auth (register/login) with PBKDF2 hashed passwords
- E2E encrypted message storage (server sees only ciphertext)
- Real-time WebSocket messaging with online presence
- Public key exchange for E2E crypto
- AI translation subtitles for video calls
- Private Mode: agent AI is completely bypassed
"""
import asyncio
import json
import os
import secrets
import time
import sys
import uuid
from typing import Dict, Optional, Set

import aiohttp
from aiohttp import web
import aiohttp.web_routedef

# Local modules
sys.path.insert(0, os.path.dirname(__file__))
import db
from crypto import PasswordHasher
from translator import get_translator

# Store live WebSocket connections: user_id -> ws
CONNECTIONS: Dict[str, web.WebSocketResponse] = {}
# Private mode flags: user_id -> bool
PRIVATE_MODES: Dict[str, bool] = {}


# ─── Auth Routes ──────────────────────────────────────────────

async def handle_register(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        username = data.get('username', '').strip().lower()
        display_name = data.get('display_name', '').strip()
        password = data.get('password', '')
        language = data.get('language', 'en')

        if not username or not password or not display_name:
            return web.json_response({'error': 'All fields required'}, status=400)
        if len(username) < 3 or not username.replace('_', '').replace('.', '').isalnum():
            return web.json_response({'error': 'Username must be 3+ letters/numbers/._'}, status=400)
        if len(password) < 6:
            return web.json_response({'error': 'Password must be 6+ characters'}, status=400)

        user_id = str(uuid.uuid4())
        password_hash = PasswordHasher.hash_password(password)
        
        if not db.create_user(user_id, username, display_name, password_hash, language):
            return web.json_response({'error': 'Username already taken'}, status=409)

        token = secrets.token_urlsafe(32)
        db.create_session(token, user_id)
        user = db.get_user_by_id(user_id)
        
        return web.json_response({
            'token': token,
            'user': _safe_user(user)
        })
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def handle_login(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')

        user = db.get_user_by_username(username)
        if not user or not PasswordHasher.verify_password(password, user['password_hash']):
            return web.json_response({'error': 'Invalid username or password'}, status=401)

        token = secrets.token_urlsafe(32)
        db.create_session(token, user['id'])

        return web.json_response({
            'token': token,
            'user': _safe_user(user)
        })
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def handle_search(request: web.Request) -> web.Response:
    user_id = await _auth(request)
    if not user_id:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    query = request.rel_url.query.get('q', '')
    results = db.search_users(query, user_id)
    return web.json_response({'users': results})


async def handle_rooms(request: web.Request) -> web.Response:
    user_id = await _auth(request)
    if not user_id:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    rooms = db.get_user_rooms(user_id)
    return web.json_response({'rooms': rooms})


async def handle_messages(request: web.Request) -> web.Response:
    user_id = await _auth(request)
    if not user_id:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    room_id = request.match_info['room_id']
    messages = db.get_room_messages(room_id)
    return web.json_response({'messages': messages})


async def handle_pubkey(request: web.Request) -> web.Response:
    user_id = await _auth(request)
    if not user_id:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    data = await request.json()
    pubkey = data.get('public_key', '')
    if pubkey:
        db.update_user_pubkey(user_id, pubkey)
    return web.json_response({'ok': True})


async def handle_get_pubkey(request: web.Request) -> web.Response:
    target_id = request.match_info['user_id']
    user = db.get_user_by_id(target_id)
    if not user:
        return web.json_response({'error': 'User not found'}, status=404)
    return web.json_response({'public_key': user.get('public_key', '')})


# ─── Social & Feed Routes ───────────────────────────────────

async def handle_get_posts(request: web.Request) -> web.Response:
    user_id = await _auth(request)
    if not user_id:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    posts = db.get_global_feed(50)
    return web.json_response({'posts': posts})

async def handle_add_post(request: web.Request) -> web.Response:
    user_id = await _auth(request)
    if not user_id:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    data = await request.json()
    content = data.get('content', '')
    media_url = data.get('media_url')
    if not content and not media_url:
        return web.json_response({'error': 'Empty post'}, status=400)
    
    post_id = str(uuid.uuid4())
    db.add_post(post_id, user_id, content, media_url)
    return web.json_response({'ok': True})


async def handle_update_profile(request: web.Request) -> web.Response:
    user_id = await _auth(request)
    if not user_id:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    data = await request.json()
    bio = data.get('bio', '')
    is_public = bool(data.get('is_public', False))
    status_text = data.get('status_text', 'Available')
    custom_theme = data.get('custom_theme', 'default')
    db.update_profile(user_id, bio, is_public, status_text, custom_theme)

    # Broadcast status change if online
    msg = {'type': 'status_update', 'user_id': user_id, 'status_text': status_text}
    for uid, ws in list(CONNECTIONS.items()):
        if uid != user_id and not ws.closed:
            try:
                await ws.send_str(json.dumps(msg))
            except:
                pass

    return web.json_response({'ok': True})


async def handle_get_friends(request: web.Request) -> web.Response:
    user_id = await _auth(request)
    if not user_id:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    friends = db.get_friends(user_id)
    return web.json_response({'friends': friends})


async def handle_add_friend(request: web.Request) -> web.Response:
    user_id = await _auth(request)
    if not user_id:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    data = await request.json()
    friend_id = data.get('friend_id')
    if friend_id:
        db.add_friend(user_id, friend_id)
    return web.json_response({'ok': True})


# ─── WebSocket ────────────────────────────────────────────────

async def handle_websocket(request: web.Request) -> web.WebSocketResponse:
    token = request.rel_url.query.get('token')
    user_id = db.get_session_user(token) if token else None
    if not user_id:
        return web.Response(status=401, text='Unauthorized')

    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    CONNECTIONS[user_id] = ws
    db.set_online_status(user_id, True)
    await _broadcast_presence(user_id, True)

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await _handle_ws_message(user_id, msg.data)
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                break
    finally:
        CONNECTIONS.pop(user_id, None)
        PRIVATE_MODES.pop(user_id, None)
        db.set_online_status(user_id, False)
        await _broadcast_presence(user_id, False)

    return ws


async def _handle_ws_message(sender_id: str, raw: str):
    try:
        payload = json.loads(raw)
        ptype = payload.get('type')
        
        if ptype == 'set_private_mode':
            PRIVATE_MODES[sender_id] = payload.get('enabled', False)
            
        elif ptype == 'send_message':
            recipient_id = payload.get('recipient_id')
            if not recipient_id:
                return
            room_id = db.get_or_create_room(sender_id, recipient_id)
            is_private = PRIVATE_MODES.get(sender_id, False)
            msg_id = str(uuid.uuid4())
            
            db.store_message(
                msg_id, room_id, sender_id,
                payload.get('encrypted_content', ''),
                payload.get('message_type', 'text'),
                is_private
            )
            
            # Forward to recipient
            msg_out = {
                'type': 'new_message',
                'id': msg_id,
                'room_id': room_id,
                'sender_id': sender_id,
                'encrypted_content': payload.get('encrypted_content', ''),
                'message_type': payload.get('message_type', 'text'),
                'is_private': is_private,
                'timestamp': time.time()
            }
            
            await _send_to(sender_id, msg_out)
            if recipient_id in CONNECTIONS:
                await _send_to(recipient_id, msg_out)

        elif ptype == 'translate_subtitle':
            # Only translate if sender NOT in private mode
            if not PRIVATE_MODES.get(sender_id, False):
                translator = get_translator()
                room_id = payload.get('room_id', '')
                translated = translator.translate(
                    text=payload.get('text', ''),
                    from_lang=payload.get('from_lang', 'en'),
                    to_lang=payload.get('to_lang', 'en'),
                    room_id=room_id
                )
                await _send_to(sender_id, {
                    'type': 'subtitle',
                    'text': translated,
                    'original': payload.get('text', ''),
                    'from_lang': payload.get('from_lang'),
                    'to_lang': payload.get('to_lang'),
                    'speaker_id': sender_id
                })
                # Also send to the other person in the room  
                recipient_id = payload.get('recipient_id')
                if recipient_id and recipient_id in CONNECTIONS:
                    await _send_to(recipient_id, {
                        'type': 'subtitle',
                        'text': translated,
                        'original': payload.get('text', ''),
                        'from_lang': payload.get('from_lang'),
                        'to_lang': payload.get('to_lang'),
                        'speaker_id': sender_id
                    })

        elif ptype in ('call_offer', 'call_answer', 'ice_candidate', 'call_end'):
            # WebRTC signaling relay — server does NOT inspect video content
            recipient_id = payload.get('recipient_id')
            if recipient_id and recipient_id in CONNECTIONS:
                payload['sender_id'] = sender_id
                await _send_to(recipient_id, payload)

        elif ptype == 'typing':
            recipient_id = payload.get('recipient_id')
            if recipient_id and recipient_id in CONNECTIONS:
                await _send_to(recipient_id, {
                    'type': 'typing',
                    'sender_id': sender_id
                })

        elif ptype == 'mark_read':
            room_id = payload.get('room_id')
            recipient_id = payload.get('recipient_id')
            if room_id and recipient_id:
                db.mark_messages_read(room_id, recipient_id)
                if recipient_id in CONNECTIONS:
                    await _send_to(recipient_id, {
                        'type': 'messages_read',
                        'room_id': room_id,
                        'reader_id': sender_id
                    })

        elif ptype == 'agent_command':
            # Run agent asynchronously so we don't block the WebSocket loop
            cmd_text = payload.get('text', '')
            room_id = payload.get('room_id')
            
            async def _process_agent(txt: str, rid: str, sid: str):
                from agent_bridge import ask_agent
                # 1. Send Thinking notification
                await _send_to(sid, {
                    'type': 'new_message',
                    'id': str(uuid.uuid4()),
                    'room_id': rid,
                    'sender_id': 'nomad_agent',
                    'encrypted_content': '🤔 Swarm Agent is analyzing with ReACT loop...',
                    'message_type': 'text',
                    'timestamp': time.time(),
                    'is_agent': True
                })
                # 2. Block on AI thinking in a separate thread
                try:
                    if txt.strip().lower().startswith('/simulate '):
                        scenario = txt.replace('/simulate', '', 1).strip()
                        from src.agent.intelligence.crowd_simulator import execute_simulation_tool
                        reply = execute_simulation_tool({"action": "predict", "scenario": scenario, "population": 300, "rounds": 7})
                    elif txt.strip().lower().startswith('/quick_sim '):
                        scenario = txt.replace('/quick_sim', '', 1).strip()
                        from src.agent.intelligence.crowd_simulator import execute_simulation_tool
                        reply = execute_simulation_tool({"action": "quick", "scenario": scenario})
                    else:
                        reply = await ask_agent(txt)
                except Exception as e:
                    reply = f"Error during reasoning: {e}"
                # 3. Send final answer
                await _send_to(sid, {
                    'type': 'new_message',
                    'id': str(uuid.uuid4()),
                    'room_id': rid,
                    'sender_id': 'nomad_agent',
                    'encrypted_content': reply,
                    'message_type': 'text',
                    'timestamp': time.time(),
                    'is_agent': True
                })
            
            asyncio.create_task(_process_agent(cmd_text, room_id, sender_id))

    except Exception as e:
        print(f"[WS Error] {sender_id}: {e}")


async def _send_to(user_id: str, data: dict):
    ws = CONNECTIONS.get(user_id)
    if ws and not ws.closed:
        try:
            await ws.send_str(json.dumps(data))
        except Exception:
            pass


async def _broadcast_presence(user_id: str, online: bool):
    msg = json.dumps({'type': 'presence', 'user_id': user_id, 'online': online})
    for uid, ws in list(CONNECTIONS.items()):
        if uid != user_id and not ws.closed:
            try:
                await ws.send_str(msg)
            except Exception:
                pass


# ─── Helpers ──────────────────────────────────────────────────

async def _auth(request: web.Request) -> Optional[str]:
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else None
    if not token:
        token = request.rel_url.query.get('token')
    return db.get_session_user(token) if token else None


def _safe_user(user: dict) -> dict:
    return {
        'id': user['id'],
        'username': user['username'],
        'display_name': user['display_name'],
        'avatar_color': user['avatar_color'],
        'bio': user.get('bio', ''),
        'language': user.get('language', 'en'),
        'is_public': bool(user.get('is_public', 0)),
        'status_text': user.get('status_text', 'Available'),
        'custom_theme': user.get('custom_theme', 'default'),
        'online': bool(user.get('online', 0))
    }


# ─── Static Files ─────────────────────────────────────────────

async def handle_static(request: web.Request) -> web.Response:
    filename = request.match_info.get('filename', 'index.html')
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    filepath = os.path.join(static_dir, filename)
    if not os.path.exists(filepath):
        filepath = os.path.join(static_dir, 'index.html')
    with open(filepath, 'rb') as f:
        content = f.read()
    content_types = {
        '.html': 'text/html', '.js': 'application/javascript',
        '.css': 'text/css', '.json': 'application/json',
        '.png': 'image/png', '.ico': 'image/x-icon', '.webp': 'image/webp'
    }
    ext = os.path.splitext(filepath)[1]
    ct = content_types.get(ext, 'application/octet-stream')
    return web.Response(body=content, content_type=ct)


# ─── App Setup ────────────────────────────────────────────────

def create_app() -> web.Application:
    db.init_db()
    app = web.Application()
    
    app.router.add_post('/api/register', handle_register)
    app.router.add_post('/api/login', handle_login)
    app.router.add_get('/api/search', handle_search)
    app.router.add_get('/api/rooms', handle_rooms)
    app.router.add_get('/api/rooms/{room_id}/messages', handle_messages)
    app.router.add_post('/api/pubkey', handle_pubkey)
    app.router.add_get('/api/users/{user_id}/pubkey', handle_get_pubkey)
    app.router.add_post('/api/profile', handle_update_profile)
    app.router.add_get('/api/friends', handle_get_friends)
    app.router.add_post('/api/friends', handle_add_friend)
    app.router.add_get('/api/posts', handle_get_posts)
    app.router.add_post('/api/posts', handle_add_post)
    app.router.add_get('/ws', handle_websocket)
    app.router.add_get('/', lambda r: handle_static(r))
    app.router.add_get('/{filename:.+}', handle_static)
    
    return app


if __name__ == '__main__':
    PORT = int(os.environ.get('CHAT_PORT', 8765))
    print(f"🔐 NOMAD SecureChat Server starting on http://localhost:{PORT}")
    print(f"   E2E Encryption: X25519 + AES-256-GCM")
    print(f"   Private Mode: Agent-Blind messaging available")
    print(f"   WebRTC: Peer-to-peer video calls (no relay)")
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=PORT)
