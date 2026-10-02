"""Adras Bot backend: Instagram webhook + boshqaruv API (FastAPI)."""
import hashlib, hmac, json, os, re, uuid
from pathlib import Path
import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()
ENV = lambda k, d="": os.getenv(k, d)
GRAPH = "https://graph.instagram.com/v21.0"
DB = Path("data.json")
app = FastAPI(title="Adras Bot")

# ---------- Saqlash (oddiy JSON; keyin PostgreSQL ga almashtirish mumkin) ----------
def load():
    return json.loads(DB.read_text()) if DB.exists() else {"posts": [], "conv": {}, "log": {"comments": 0}}
def save(d): DB.write_text(json.dumps(d, ensure_ascii=False, indent=1))

def admin(x_admin_key: str = Header(default="")):
    if not ENV("ADMIN_KEY") or not hmac.compare_digest(x_admin_key, ENV("ADMIN_KEY")):
        raise HTTPException(401, "Admin kalit noto'g'ri")

# ---------- Instagram API chaqiruvlari (FAQAT shu yerda) ----------
async def ig(method, path, **kw):
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.request(method, f"{GRAPH}/{path}", params={"access_token": ENV("INSTAGRAM_ACCESS_TOKEN")}, **kw)
        r.raise_for_status(); return r.json()

async def reply_to_comment(comment_id, text):
    if ENV("MODE") != "live": return print("[DEMO] komment javobi:", text)
    await ig("POST", f"{comment_id}/replies", data={"message": text})

async def send_dm(comment_id, text):
    if ENV("MODE") != "live": return print("[DEMO] direct:", text)
    await ig("POST", "me/messages", json={"recipient": {"comment_id": comment_id}, "message": {"text": text}})

_perma = {}
async def permalink(media_id):
    if media_id not in _perma:
        _perma[media_id] = (await ig("GET", media_id, params={"fields": "permalink"}))["permalink"]
    return _perma[media_id]
norm = lambda u: re.sub(r"[?#].*$", "", u).rstrip("/").lower()

# ---------- Webhook ----------
@app.get("/webhook")
def verify(mode: str = Query(None, alias="hub.mode"), token: str = Query(None, alias="hub.verify_token"),
           challenge: str = Query(None, alias="hub.challenge")):
    if mode == "subscribe" and token and hmac.compare_digest(token, ENV("WEBHOOK_VERIFY_TOKEN")):
        return PlainTextResponse(challenge)
    raise HTTPException(403, "Verify token mos emas")

@app.post("/webhook")
async def events(req: Request):
    raw = await req.body()
    sig = req.headers.get("X-Hub-Signature-256", "")
    good = "sha256=" + hmac.new(ENV("INSTAGRAM_APP_SECRET").encode(), raw, hashlib.sha256).hexdigest()
    if ENV("MODE") == "live" and not hmac.compare_digest(sig, good):
        raise HTTPException(403, "Imzo noto'g'ri")
    await handle(json.loads(raw))
    return {"ok": True}  # Meta tez 200 kutadi

async def handle(payload):
    d = load()
    for entry in payload.get("entry", []):
        for ch in entry.get("changes", []):          # KOMMENT
            if ch.get("field") != "comments": continue
            v = ch["value"]; d["log"]["comments"] += 1
            link = norm(await permalink(v["media"]["id"])) if ENV("MODE") == "live" else norm(v["media"].get("permalink", ""))
            post = next((p for p in d["posts"] if p["enabled"] and norm(p["link"]) == link), None)
            if not post: continue
            post["stats"]["comments"] += 1
            await reply_to_comment(v["id"], post["comment_reply"]); post["stats"]["replies"] += 1
            await send_dm(v["id"], post["dm_message"]); post["stats"]["dms"] += 1
            d["conv"][v["from"]["id"]] = post["id"]
        for m in entry.get("messaging", []):          # DIRECT
            uid = m.get("sender", {}).get("id")
            if uid in d["conv"] and m.get("message", {}).get("text"):
                post = next((p for p in d["posts"] if p["id"] == d["conv"][uid]), None)
                if post: post["stats"]["continued"] += 1
    save(d)

# ---------- Panel API ----------
@app.get("/api/posts", dependencies=[Depends(admin)])
def posts(): return load()["posts"]

@app.post("/api/posts", dependencies=[Depends(admin)])
async def add(req: Request):
    b = await req.json(); d = load()
    if not all(b.get(k, "").strip() for k in ("name", "link", "comment_reply", "dm_message")):
        raise HTTPException(422, "4 maydon ham to'ldirilishi kerak")
    p = {**{k: b[k] for k in ("name", "link", "comment_reply", "dm_message")}, "id": uuid.uuid4().hex[:8],
         "enabled": True, "stats": {"comments": 0, "replies": 0, "dms": 0, "continued": 0}}
    d["posts"].append(p); save(d); return p

@app.put("/api/posts/{pid}", dependencies=[Depends(admin)])
async def edit(pid: str, req: Request):
    b = await req.json(); d = load()
    for p in d["posts"]:
        if p["id"] == pid:
            p.update({k: b[k] for k in ("name", "link", "comment_reply", "dm_message", "enabled") if k in b})
            save(d); return p
    raise HTTPException(404)

@app.delete("/api/posts/{pid}", dependencies=[Depends(admin)])
def rm(pid: str):
    d = load(); d["posts"] = [p for p in d["posts"] if p["id"] != pid]; save(d); return {"ok": True}

@app.get("/api/status", dependencies=[Depends(admin)])   # tokenning o'zi HECH QACHON qaytmaydi
async def status():
    info = {"mode": ENV("MODE"), "token_set": bool(ENV("INSTAGRAM_ACCESS_TOKEN")),
            "secret_set": bool(ENV("INSTAGRAM_APP_SECRET")), "verify_set": bool(ENV("WEBHOOK_VERIFY_TOKEN")),
            "username": None, "connected": False}
    if info["token_set"] and ENV("MODE") == "live":
        try: info["username"] = (await ig("GET", "me", params={"fields": "username"}))["username"]; info["connected"] = True
        except Exception: pass
    return info

@app.post("/api/test/{name}", dependencies=[Depends(admin)])
async def test(name: str):
    try:
        if name in ("api", "token"):
            if ENV("MODE") != "live": return {"ok": False, "msg": "Demo rejim: live yoqing"}
            await ig("GET", "me", params={"fields": "username"})
        elif name == "verify":
            assert ENV("WEBHOOK_VERIFY_TOKEN"), "WEBHOOK_VERIFY_TOKEN yo'q"
        elif name == "event":
            await handle({"entry": [{"changes": [{"field": "comments", "value": {"id": "t", "from": {"id": "t"}, "media": {"id": "t", "permalink": "x"}}}]}]})
        else:
            assert ENV("INSTAGRAM_ACCESS_TOKEN"), "Token yo'q"
        return {"ok": True, "msg": "Muvaffaqiyatli"}
    except Exception as e:
        return {"ok": False, "msg": str(e)[:120]}

@app.get("/")
def index(): return FileResponse("static/index.html")
app.mount("/static", StaticFiles(directory="static"), name="static")
