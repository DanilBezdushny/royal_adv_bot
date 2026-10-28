from fastapi import FastAPI, Request, Response
import os
import json
from vk_api import VkApi
from vk_api.utils import get_random_id
from dotenv import load_dotenv

load_dotenv()

# Настройки
VK_TOKEN = os.getenv("VK_COMMUNITY_TOKEN")
CONFIRM_TOKEN = os.getenv("CONFIRMATION_TOKEN")
SECRET_KEY = os.getenv("SECRET_KEY")
CHAT_PEER_ID = int(os.getenv("CHAT_PEER_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))

app = FastAPI()
vk_session = VkApi(token=VK_TOKEN)

GROUPS = [
    "https://vk.ru/club241519834",
    "https://vk.ru/club241781796",
]

def extract_group_id(url: str):
    if "/club" in url or "/public" in url:
        return url.split("/")[-1]
    return None

def send_message(peer_id: int, message: str):
    try:
        vk_session.method("messages.send", {
            "peer_id": peer_id,
            "message": message,
            "random_id": get_random_id(),
            "dont_parse_links": 1
        })
    except Exception as e:
        print(f"[ERROR] Send: {e}")

# --- ГЛАВНАЯ СТРАНИЦА (для подтверждения ВК) ---
@app.get("/")
async def confirmation():
    return Response(content=CONFIRM_TOKEN, media_type="text/plain", status_code=200)

# --- ВЕБХУК (сюда приходят сообщения) ---
@app.post("/")
async def webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"error": "invalid json"}

    if data.get("secret") != SECRET_KEY:
        return {"error": "invalid secret"}

    # Подтверждение от ВК
    if data.get("type") == "confirmation":
        return Response(content=CONFIRM_TOKEN, media_type="text/plain", status_code=200)

    # --- ОБРАБОТКА СООБЩЕНИЙ ---
    if data.get("type") == "message_new":
        # 1. ДИАГНОСТИКА: Выводим весь JSON в логи Bothost
        print("VK DATA:", json.dumps(data, ensure_ascii=False, indent=2))

        # 2. Берем данные из объекта message
        msg = data.get("object", {}).get("message", {})
        
        if msg.get("peer_id") != CHAT_PEER_ID:
            return {"status": "not our chat"}

        from_id = msg.get("from_id")
        text = msg.get("text", "").strip().lower()
        action = msg.get("action")

        # Если пользователя пригласили
        if action and action.get("type") == "chat_invite_user":
            member_id = action.get("member_id")
            welcome = "🚪 Добро пожаловать!\n📋 Подпишись.\n💬 Напиши ГОТОВО."
            send_message(CHAT_PEER_ID, f"[id{member_id}|Новый] зашел!\n{welcome}")

        # Если написали "согласен"
        if text == "согласен":
            lst = "\n".join([f"{i+1}. {u}" for i, u in enumerate(GROUPS)])
            send_message(CHAT_PEER_ID, f"[id{from_id}|Принято]\n{lst}")

        # Если написали "готово"
        if text == "готово":
            missing = []
            for u in GROUPS:
                gid = extract_group_id(u)
                try:
                    res = vk_session.method("groups.isMember", {"user_id": from_id, "group_id": gid})
                    if res not in [1, 2]:
                        missing.append(u)
                except Exception:
                    missing.append(u)
            
            if not missing:
                send_message(CHAT_PEER_ID, f"[id{from_id}|✅] Проверка пройдена!")
            else:
                miss_text = "\n".join(missing[:5])
                send_message(CHAT_PEER_ID, f"[id{from_id}|❌] Нет подписок:\n{miss_text}")

    return {"status": "ok"}

# --- ЗАПУСК СЕРВЕРА (для локального теста, Bothost обычно игнорирует) ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)