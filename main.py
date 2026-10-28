from fastapi import FastAPI, Request
import os
import json
from vk_api import VkApi
from vk_api.utils import get_random_id

# --- ЧИТАЕМ НАСТРОЙКИ (Переменные окружения) ---
TOKEN = os.getenv("VK_COMMUNITY_TOKEN")
CONFIRM = os.getenv("CONFIRMATION_TOKEN")
SECRET = os.getenv("SECRET_KEY")
CHAT_ID = int(os.getenv("CHAT_PEER_ID", 0)) # Если пусто, будет 0

# --- СПИСОК ГРУПП ---
GROUPS = [
    "https://vk.ru/club241519834",
    "https://vk.ru/club241781796",
    # Добавь остальные группы сюда
]

app = FastAPI()

def get_group_id(url: str):
    if "/club" in url or "/public" in url:
        return url.split("/")[-1]
    return None

def send_vk_message(peer_id: int, message: str):
    if not TOKEN:
        print("ERROR: Токен не задан в переменных")
        return
    try:
        vk = VkApi(token=TOKEN)
        vk.method("messages.send", {
            "peer_id": peer_id,
            "message": message,
            "random_id": get_random_id(),
            "dont_parse_links": 1
        })
    except Exception as e:
        print(f"Error sending message: {e}")

# --- ГЛАВНАЯ ТОЧКА ВХОДА ---
@app.get("/")
def confirm():
    # Возвращаем код для подтверждения в ВК
    return CONFIRM if CONFIRM else "NO_CONFIRM_TOKEN"

@app.post("/")
async def handle(request: Request):
    # Если сервер упал и не может прочитать JSON
    try:
        data = await request.json()
    except Exception:
        return {"error": "invalid json"}

    # Проверка секретного ключа
    if data.get("secret") != SECRET:
        return {"error": "invalid secret"}

    # --- ОБРАБОТКА СОБЫТИЙ ---
    if data.get("type") == "confirmation":
        return CONFIRM if CONFIRM else "error"

    if data.get("type") == "message_new":
        obj = data.get("object", {})
        
        # Игнорируем всё, что не в нашем чате
        if obj.get("peer_id") != CHAT_ID:
            return {"status": "not our chat"}

        from_id = obj.get("from_id")
        text = obj.get("text", "").strip().lower()
        action = obj.get("action")

        # Если пользователя пригласили
        if action and action.get("type") == "chat_invite_user":
            member_id = action.get("member_id")
            welcome = (
                "🚪 ДОБРО ПОЖАЛОВАТЬ!\n\n"
                "📋 ШАГ 1: Подпишись на список участников.\n"
                "💬 ШАГ 2: Напиши кодовое слово: ГОТОВО"
            )
            send_vk_message(CHAT_ID, f"[id{member_id}|Новый] зашел!\n{welcome}")

        # Если написали "согласен"
        if text == "согласен":
            lst = "\n".join([f"{i+1}. {url}" for i, url in enumerate(GROUPS)])
            send_vk_message(CHAT_ID, f"[id{from_id}|Принято]\n{lst}")

        # Если написали "готово"
        if text == "готово":
            missing = []
            for url in GROUPS:
                gid = get_group_id(url)
                if not gid:
                    continue
                try:
                    vk = VkApi(token=TOKEN)
                    res = vk.method("groups.isMember", {"user_id": from_id, "group_id": gid})
                    if res not in [1, 2]:
                        missing.append(url)
                except Exception:
                    missing.append(url)

            if not missing:
                send_vk_message(CHAT_ID, f"[id{from_id}|✅] Проверка пройдена! Жди админа.")
            else:
                miss_text = "\n".join(missing[:5])
                send_vk_message(CHAT_ID, f"[id{from_id}|❌] Нет подписок:\n{miss_text}")

    return {"status": "ok"}