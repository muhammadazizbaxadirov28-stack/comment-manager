# Adras Bot: Instagram webhook serveri

## 1. Kompyuterda sinash (PowerShell)
    python -m venv venv; .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env      # .env ni to'ldiring
    uvicorn main:app --reload
Panel: http://localhost:8000  |  Webhook: http://localhost:8000/webhook

## 2. Public HTTPS URL olish
A) Tez sinov: `ngrok http 8000` -> https://xxxx.ngrok-free.app/webhook
B) Doimiy: Render.com -> New Web Service -> GitHub repo ulang ->
   Build: `pip install -r requirements.txt`, Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
   Environment bo'limiga .env dagi qiymatlarni kiriting. URL: https://nomi.onrender.com/webhook
   (Railway ham xuddi shunday; Vercel doimiy FastAPI uchun mos emas.)
   Eslatma: Render bepul rejasida data.json qayta ishga tushganda o'chadi; doimiy baza kerak bo'ladi.

## 3. Meta ulash
developers.facebook.com -> App -> Instagram -> Webhooks:
 Callback URL = https://.../webhook, Verify Token = WEBHOOK_VERIFY_TOKEN dagi so'z.
 `comments` va `messages` maydonlariga obuna bo'ling. So'ng MODE=live qiling.
