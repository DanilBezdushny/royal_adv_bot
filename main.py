from fastapi import FastAPI, Request, Response
import os
import time
import threading
from typing import Optional, Dict, List
from vk_api import VkApi
from vk_api.utils import get_random_id
from dotenv import load_dotenv

load_dotenv()

VK_TOKEN = os.getenv("VK_COMMUNITY_TOKEN", "")
CONFIRM_TOKEN = os.getenv("CONFIRMATION_TOKEN", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")
CHAT_PEER_ID = int(os.getenv("CHAT_PEER_ID", "0"))

app: FastAPI = FastAPI()
vk_session = VkApi(token=VK_TOKEN)

member_names: Dict[int, str] = {}
welcome_sent: Dict[int, bool] = {}
last_check_time: Dict[int, int] = {}
memory_lock = threading.Lock()

# Инициализируем переменную прямо после определения функции 

GROUPS = [
    # ... список групп здесь ...
]

WELCOME_TEXT = """... [твой текст приветствия] ..."""
SUCCESS_TEXT = "[id{uid}|{name}], проверка пройдена! ✅ Ожидайте админа."
FAIL_TEXT = "[id{uid}|{name}], проверка не пройдена. ❌ Вы не подписаны на:\n{groups}\n\nПодпишитесь и напишите «ГОТОВО» снова."

def extract_group_id(url: str):
    if "/club" in url or "/public" in url:
        return url.split("/")[-1].split("#")[0]
    elif "/id" in url:
        return url.split("/")[-1].split("#")[0]
    else:
        return None

def delete_message(peer_id: int, message_id: int) -> None:
    try:
        vk_session.method("messages.delete", {
            "message_ids": message_id,
            "delete_for_all": 1  
        })
    except Exception as e:
        print(f"[ERROR] Delete: {e}")

def send_message(peer_id: int, message: str) -> None:
    try:
        vk_session.method("messages.send", {"peer_id": peer_id, "message": message, "random_id": get_random_id(), "dont_parse_links": 1})
    except Exception as e:
        print(f"[ERROR] Send: {e}")

def get_user_name(user_id: int) -> str:
    try:
        response = vk_session.method("users.get", {"user_ids": user_id, "fields": "first_name,last_name"})
        if response and isinstance(response, list) and len(response) > 0:
            user = response[0]
            name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            return name if name else "Участник"
    except Exception:
        pass
    return "Участник"

@app.get("/")
async def confirmation() -> Response:
    return Response(content=CONFIRM_TOKEN, media_type="text/plain", status_code=200)

@app.post("/")
async def webhook(request: Request):
    try:
        data = await request.json()
        
        # Полный вывод объекта данных (для отладки)
        print(f"\n[DEBUG] ПОЛУЧЕННЫЙ ОБЪЕКТ DATA:\n{data}\n")
    
    except Exception as e:
        print(f"[ERROR] JSON parse error: {e}")
        return {"error": "invalid json"}

    if data.get("secret") != SECRET_KEY:
        return {"error": "invalid secret"}
    
    # Сразу отвечаем ВК!
    response = Response(content="ok", status_code=200)  
    
    async def process_request(data):  
        with memory_lock:
            last_update_id = getattr(webhook, 'last_update_id', -1)
        
        update_id = data.get('update_id')
        if update_id is not None and update_id == last_update_id:
            print("[DEBUG] Дубликат события")
            return
        if update_id is not None:
            setattr(webhook, 'last_update_id', update_id)

        msg = data.get("object").get("message", {})
        
        action = data.get("object", {}).get("action")
        peer_id = data.get("object", {}).get("peer_id")
        from_id = data.get("object", {}).get("from_id")
        
        # --- ПРИВЕТСТВИЕ ---
        if action and action.get("type") == "chat_invite_user":
            invited_id = action.get("member_id")
            
            # Приветствуем того, кого добавили, если это наш чат
            if invited_id is not None and peer_id == CHAT_PEER_ID:
                with memory_lock:
                    if not welcome_sent.get(invited_id, False):
                        welcome_sent[invited_id] = True

                        member_names[invited_id] = get_user_name(invited_id)
                        name = member_names[invited_id]
                        
                        print(f"[INFO] Отправляем приветствие пользователю ID={invited_id}: {name}")
                        send_message(CHAT_PEER_ID, WELCOME_TEXT.format(uid=invited_id, name=name))
            return {"status": "ok"}
    import asyncio
    asyncio.create_task(process_request(data))  # Запускаем долгую задачу параллельно

    return response # Быстро отвечаем ВК!

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000, reload=False, workers=1)