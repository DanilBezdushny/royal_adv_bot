import os
import json
from vk_api import VkApi
from vk_api.utils import get_random_id

# --- Настройки ---
VK_COMMUNITY_TOKEN = os.getenv("VK_COMMUNITY_TOKEN")
CONFIRMATION_TOKEN = os.getenv("CONFIRMATION_TOKEN")
SECRET_KEY = os.getenv("SECRET_KEY")
CHAT_PEER_ID = int(os.getenv("CHAT_PEER_ID"))

required_groups = [
    "https://vk.ru/club241519834",
    "https://vk.ru/club241781796",
]

def extract_group_id(url: str):
    if "/club" in url or "/public" in url:
        return url.split("/")[-1]
    return None

def send_message(peer_id: int, message: str):
    vk_session = VkApi(token=VK_COMMUNITY_TOKEN)
    try:
        vk_session.method("messages.send", {
            "peer_id": peer_id,
            "message": message,
            "random_id": get_random_id(),
            "dont_parse_links": 1
        })
    except Exception as e:
        print(f"[ERROR] Failed to send message: {e}")

def handle_new_member(member_id: int):
    text = (
        "🚪 ДОБРО ПОЖАЛОВАТЬ!\n\n"
        "📋 ШАГ 1: Подпишитесь на список участников.\n"
        "💬 ШАГ 2: Напишите кодовое слово: ГОТОВО"
    )
    send_message(CHAT_PEER_ID, f"[id{member_id}|Участник] зашел!\n{text}")

def handle_user_message(from_id: int, text: str):
    if text.lower() == "согласен":
        groups_list = "\n".join([f"{i+1}. {url}" for i, url in enumerate(required_groups)])
        send_message(CHAT_PEER_ID, f"[id{from_id}|Принято]\n{groups_list}\n\nНапишите ГОТОВО")
    
    elif text.strip().lower() == "готово":
        missing = []
        for url in required_groups:
            gid = extract_group_id(url)
            try:
                res = VkApi(token=VK_COMMUNITY_TOKEN).method("groups.isMember", {"user_id": from_id, "group_id": gid})
                if res not in [1, 2]:
                    missing.append(url)
            except Exception:
                missing.append(url)
        
        if not missing:
            send_message(CHAT_PEER_ID, f"[id{from_id}|✅] Проверка пройдена!")
        else:
            miss_text = "\n".join(missing[:5])
            send_message(CHAT_PEER_ID, f"[id{from_id}|❌] Нет подписок:\n{miss_text}")

# --- Главный вход Bothost ---
def app(request):
    if request.method == 'GET':
        return os.getenv("CONFIRMATION_TOKEN"), 200
    
    if request.method == 'POST':
        try:
            data = json.loads(request.data)
        except Exception:
            return "Bad JSON", 400

        if data.get('secret') != os.getenv("SECRET_KEY"):
            return "Invalid secret", 403

        if data.get('type') == 'message_new':
            obj = data.get('object', {})
            if obj.get('peer_id') != int(os.getenv("CHAT_PEER_ID")):
                return "ok", 200

            from_id = obj.get('from_id')
            text = obj.get('text', '')
            
            action = obj.get('action')
            if action and action.get('type') == 'chat_invite_user':
                handle_new_member(action.get('member_id'))
        
            if text and from_id and from_id > 0:
                handle_user_message(from_id, text)
                
        return "ok", 200
    
    return "Method Not Allowed", 405