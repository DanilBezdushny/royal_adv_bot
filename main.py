from fastapi import FastAPI, Request
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

@app.get("/")
async def confirmation():
    return CONFIRM_TOKEN

@app.post("/")
async def webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"error": "invalid json"}

    if data.get("secret") != SECRET_KEY:
        return {"error": "invalid secret"}

    if data.get("type") == "confirmation":
        return CONFIRM_TOKEN

    if data.get("type") == "message_new":
        obj = data.get("object", {})
        if obj.get("peer_id") != CHAT_PEER_ID:
            return {"status": "not our chat"}

        from_id = obj.get("from_id")
        text = obj.get("text", "").strip().lower()
        action = obj.get("action")

        if action and action.get("type") == "chat_invite_user":
            member_id = action.get("member_id")
            welcome = "🚪 Добро пожаловать!\n📋 Подпишись.\n💬 Напиши ГОТОВО."
            send_message(CHAT_PEER_ID, f"[id{member_id}|Новый] зашел!\n{welcome}")

        if text == "согласен":
            lst = "\n".join([f"{i+1}. {u}" for i, u in enumerate(GROUPS)])
            send_message(CHAT_PEER_ID, f"[id{from_id}|Принято]\n{lst}")

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