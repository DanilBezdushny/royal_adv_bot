import os
import json
from fastapi import FastAPI, Request
from vk_api import VkApi
from vk_api.utils import get_random_id
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# Читаем настройки
VK_TOKEN = os.getenv("VK_COMMUNITY_TOKEN")
CONFIRM_TOKEN = os.getenv("CONFIRMATION_TOKEN")
SECRET_KEY = os.getenv("SECRET_KEY")
CHAT_PEER_ID = int(os.getenv("CHAT_PEER_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

# Список групп, на которые нужно подписаться (заполни своими ссылками)
REQUIRED_GROUPS = [
    "https://vk.ru/club241519834",
    "https://vk.ru/club241781796",
    # "https://vk.ru/club242640706"
]

app = FastAPI()
vk_session = VkApi(token=VK_TOKEN)

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
        print(f"[ERROR] Не удалось отправить сообщение: {e}")

def handle_new_member(member_id: int):
    welcome_text = (
        "🚪 ДОБРО ПОЖАЛОВАТЬ В ROYAL LOBBY!\n\n"
        "Вы попали в приемную закрытого клуба.\n"
        "📋 ШАГ 1: Подпишитесь на список участников.\n"
        "💬 ШАГ 2: Напишите кодовое слово: ГОТОВО\n"
        "⚠️ Те, кто отписывается после входа, удаляются навсегда."
    )
    send_message(CHAT_PEER_ID, f"[id{member_id}|Новый участник], добро пожаловать!\n{welcome_text}")

def handle_user_message(from_id: int, text: str):
    text = text.strip().lower()
    
    if text == "согласен":
        groups_list = "\n".join([f"{i+1}. {url}" for i, url in enumerate(REQUIRED_GROUPS)])
        instructions = (
            "Чтобы получить пропуск, подпишитесь на резидентов.\n\n"
            "✅ Участники:\n"
            f"{groups_list}\n\n"
            "После подписки напишите «ГОТОВО»."
        )
        send_message(CHAT_PEER_ID, f"[id{from_id}|Участник], спасибо за согласие!\n{instructions}")

    elif text == "готово":
        missing_groups = []
        for group_url in REQUIRED_GROUPS:
            group_id = extract_group_id(group_url)
            try:
                result = vk_session.method("groups.isMember", {"user_id": from_id, "group_id": group_id})
                if result not in [1, 2]:
                    missing_groups.append(group_url)
            except Exception:
                missing_groups.append(group_url)

        if not missing_groups:
            send_message(CHAT_PEER_ID, f"[id{from_id}|✅] Проверка пройдена! Ожидайте админа.")
        else:
            miss_text = "\n".join(missing_groups[:5])
            send_message(CHAT_PEER_ID, f"[id{from_id}|❌] Не подписаны на:\n{miss_text}")

# --- ТОЧКИ ВХОДА ---
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
        text = obj.get("text", "")
        action = obj.get("action")

        if action and action.get("type") == "chat_invite_user":
            member_id = action.get("member_id")
            handle_new_member(member_id)
        
        if from_id and text:
            handle_user_message(from_id, text)

    return {"status": "ok"}
@app.get("/test") 
def test_page(): 
    return "SERVER IS ALIVE AND WORKING"