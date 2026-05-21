# Live Deployment Guide

## Railway (Recommended — free tier available)

1. Go to https://railway.app and sign in with GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Select **Soulfullmens/software-brain**
4. Railway detects the Dockerfile automatically
5. Add environment variables (Settings → Variables):
   ```
   GEMINI_API_KEY=your-key
   ANTHROPIC_API_KEY=your-key
   ```
6. Click **Deploy**
7. Railway gives you a URL like `https://software-brain-production.up.railway.app`

To enable auto-deploy from CI:
- Go to Railway → Project Settings → copy the **RAILWAY_TOKEN**
- Go to GitHub → repo Settings → Secrets → add `RAILWAY_TOKEN`
- Now every push to master auto-deploys after tests pass

## Render (alternative)

1. Go to https://render.com → New → Web Service
2. Connect GitHub → select software-brain
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn smart_agent_server:app --host 0.0.0.0 --port $PORT`
5. Add env vars in dashboard

## Demo Video

To record a demo video for the README:
1. Run `python smart_agent_server.py` locally
2. Open http://localhost:8000/docs (Swagger UI)
3. Record screen using OBS or Windows Game Bar (Win+G)
4. Show:
   - The /api/status endpoint returning {"status": "ok"}
   - The /api/chat endpoint with a real message
   - The /api/security/status showing authority level
   - Optional: run pytest and show 37 passing tests
5. Upload to YouTube (unlisted) or GitHub releases
6. Add to README as a badge/link
