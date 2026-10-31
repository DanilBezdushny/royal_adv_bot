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
        
        # *** КРИТИЧЕСКАЯ ПРОВЕРКА ***
        if not all([
            msg,
            msg.get('peer_id'),
            msg.get('from_id'), 
            msg.get('text'), 
            msg.get('id') is not None   # Важно для сообщений с id = 0
        ]):
            print("[DEBUG] Получен неполный объект сообщения. Игнорируем.")
            return  # Выходим из обработчика, ничего не делаем

        from_id = msg.get("from_id")
        text = msg.get("text", "").strip().lower()
        action = msg.get("action")
        peer_id = msg.get("peer_id")

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

        # --- ПРОВЕРКА ПОДПИСОК ---
        elif text == "готово" and peer_id == CHAT_PEER_ID:
            current_time = int(time.time())
            
            with memory_lock:
                last_time = last_check_time.get(from_id, 0)
            if current_time - last_time < 5:
                print(f"[DEBUG] Слишком частая попытка проверки ({current_time-last_time}) сек., пропускаем.")
                return {"status": "ok"}
            
            with memory_lock:
                last_check_time[from_id] = current_time

            name = member_names.get(from_id, get_user_name(from_id))
            
            missing = []
            for url in GROUPS:
                gid_str = extract_group_id(url)
                if not gid_str:
                    continue
                
                try:
                    group_id_int = int(gid_str)
                    res = vk_session.method("groups.isMember", {"user_id": from_id, "group_id": group_id_int})
                    
                    print(f"[DEBUG] Проверка {url} (ID: {group_id_int}) -> Ответ API: {res}")
                    
                    # Обработка закрытых/недоступных групп
                    if isinstance(res, dict) and 'error' in res and res['error']['error_code'] == 203:
                        print(f"[DEBUG] Пропускаем закрытую группу {url}, считаем пользователя подписанным.")
                        continue
                        
                    if res not in [1, 2]:
                        missing.append(url)
                except Exception as e:
                    print(f"[DEBUG] Ошибка API для {url}: {e}")
                    missing.append(url)
            
            print(f"[DEBUG] --- РЕЗУЛЬТАТ: Бот считает, что не хватает: {missing} ---")

            if not missing:
                send_message(CHAT_PEER_ID, SUCCESS_TEXT.format(uid=from_id, name=name))
            else:
                miss_text = "\n".join(missing[:5])
                send_message(CHAT_PEER_ID, FAIL_TEXT.format(uid=from_id, name=name, groups=miss_text))

    import asyncio
    asyncio.create_task(process_request(data))  # Запускаем долгую задачу параллельно

    return response # Быстро отвечаем ВК!

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000, reload=False, workers=1)