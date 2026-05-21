import os
import shutil

src_bg = r'C:\Users\abdul rahaman\.gemini\antigravity\brain\a34cbc00-b5a2-4448-b43c-15b88c6587ae\premium_tech_bg_1772280369913.png'
src_avatar = r'C:\Users\abdul rahaman\.gemini\antigravity\brain\a34cbc00-b5a2-4448-b43c-15b88c6587ae\core_ai_avatar_1772280385126.png'
dest_dir = r'C:\Users\abdul rahaman\OneDrive\Ai software\software-brain\static'

os.makedirs(dest_dir, exist_ok=True)
bg_dest = os.path.join(dest_dir, 'bg.png')
avatar_dest = os.path.join(dest_dir, 'avatar.png')

shutil.copy(src_bg, bg_dest)
shutil.copy(src_avatar, avatar_dest)

dashboard_path = r'C:\Users\abdul rahaman\OneDrive\Ai software\software-brain\src\business\dashboard.py'
with open(dashboard_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add StaticFiles import
if 'StaticFiles' not in content:
    content = content.replace('from fastapi.responses import HTMLResponse, JSONResponse', 
        'from fastapi.responses import HTMLResponse, JSONResponse\nfrom fastapi.staticfiles import StaticFiles')

# 2. Add mount
mount_code = """
app.add_middleware(
    CORSMiddleware,
"""
new_mount = """
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.add_middleware(
    CORSMiddleware,
"""
if 'app.mount("/static"' not in content:
    content = content.replace(mount_code, new_mount)

# 3. Enhance CSS
css_replace = """body{
  font-family:'Inter',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);
  min-height:100vh;overflow-x:hidden;
}
/* Animated mesh gradient background */
body::before{
  content:'';position:fixed;inset:0;z-index:-1;
  background:
    radial-gradient(ellipse 80% 60% at 10% 20%,rgba(99,102,241,0.12),transparent),
    radial-gradient(ellipse 60% 80% at 90% 80%,rgba(6,182,212,0.10),transparent),
    radial-gradient(ellipse 50% 50% at 50% 0%,rgba(168,85,247,0.08),transparent);
  animation:meshMove 20s ease-in-out infinite alternate;
}
@keyframes meshMove{
  0%{filter:hue-rotate(0deg)}50%{filter:hue-rotate(15deg)}100%{filter:hue-rotate(-10deg)}
}
/* Grain overlay for depth */
body::after{
  content:'';position:fixed;inset:0;z-index:-1;
  background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E");
  background-repeat:repeat;background-size:256px 256px;opacity:.4;pointer-events:none;
}"""

new_css = """body{
  font-family:'Inter',system-ui,-apple-system,sans-serif;color:var(--text);
  min-height:100vh;overflow-x:hidden;
  background: url('/static/bg.png') no-repeat center center fixed;
  background-size: cover;
}
/* Blur overlay for depth */
body::before{
  content:'';position:fixed;inset:0;z-index:-1;
  background: rgba(6, 6, 11, 0.75);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
/* Grain overlay */
body::after{
  content:'';position:fixed;inset:0;z-index:-1;
  background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.06'/%3E%3C/svg%3E");
  pointer-events:none;
}"""
content = content.replace(css_replace, new_css)

# Update logo HTML
logo_old = """<div class="logo-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 17 22 12"></polyline></svg>
        </div>"""
logo_old_real = """<div class="logo-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
        </div>"""
logo_new = """<div class="logo-icon" style="background: transparent; box-shadow: none;">
          <img src="/static/avatar.png" style="width: 48px; height: 48px; object-fit: contain; border-radius: 50%; box-shadow: 0 0 20px rgba(99,102,241,0.5); border: 2px solid rgba(255,255,255,0.1);" />
        </div>"""
if logo_old_real in content:
    content = content.replace(logo_old_real, logo_new)
elif logo_old in content:
    content = content.replace(logo_old, logo_new)

with open(dashboard_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done!')
