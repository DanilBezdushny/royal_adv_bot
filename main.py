import os
import json
from vk_api import VkApi
from vk_api.utils import get_random_id

# --- Чтение настроек ---
TOKEN = os.getenv("VK_COMMUNITY_TOKEN")
CONFIRM = os.getenv("CONFIRMATION_TOKEN")
SECRET = os.getenv("SECRET_KEY")
CHAT_ID = int(os.getenv("CHAT_PEER_ID"))

GROUPS = [
    "https://vk.ru/club241519834",
    "https://vk.ru/club241781796",
]

def get_id(url):
    if "/club" in url:
        return url.split("/")[-1]
    return None

def send(peer_id, text):
    vk = VkApi(token=TOKEN)
    try:
        vk.method("messages.send", {"peer_id": peer_id, "message": text, "random_id": get_random_id()})
    except Exception as e:
        print(f"Error: {e}")

def app(request):
    # --- Обработка подтверждения (когда ВК нажимает "Подтвердить") ---
    if request.method == "GET":
        return CONFIRM, 200

    # --- Обработка сообщений из чата ---
    if request.method == "POST":
        try:
            data = json.loads(request.data)
        except Exception:
            return "Bad JSON", 400

        if data.get("secret") != SECRET:
            return "Invalid secret", 403

        if data.get("type") == "message_new":
            obj = data.get("object", {})
            
            # Проверяем, что сообщение пришло именно в наш чат
            if obj.get("peer_id") != CHAT_ID:
                return "ok", 200

            from_id = obj.get("from_id")
            text = obj.get("text", "")
            
            # Если пользователя пригласили
            action = obj.get("action")
            if action and action.get("type") == "chat_invite_user":
                send(CHAT_ID, f"[id{action.get('member_id')}|Новый] зашел в чат!")
            
            # Если написали "согласен"
            if text.lower() == "согласен":
                lst = "\n".join([f"{i+1}. {u}" for i, u in enumerate(GROUPS)])
                send(CHAT_ID, f"[id{from_id}|Принято]\n{lst}")
            
            # Если написали "готово"
            if text.strip().lower() == "готово":
                miss = []
                for u in GROUPS:
                    gid = get_id(u)
                    try:
                        res = VkApi(token=TOKEN).method("groups.isMember", {"user_id": from_id, "group_id": gid})
                        if res not in [1, 2]:
                            miss.append(u)
                    except Exception:
                        miss.append(u)
                
                if not miss:
                    send(CHAT_ID, f"[id{from_id}|✅] Всё верно!")
                else:
                    send(CHAT_ID, f"[id{from_id}|❌] Нет подписок:\n" + "\n".join(miss[:3]))
                    
        return "ok", 200

    return "Method Not Allowed", 405