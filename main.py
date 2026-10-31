from fastapi import FastAPI, Request, Response
import os
import time
import threading
from typing import Optional, Dict, List
from vk_api import VkApi
from vk_api.utils import get_random_id
from dotenv import load_dotenv

load_dotenv()

VK_TOKEN: str = os.getenv("VK_COMMUNITY_TOKEN", "")
CONFIRM_TOKEN: str = os.getenv("CONFIRMATION_TOKEN", "")
SECRET_KEY: str = os.getenv("SECRET_KEY", "")
CHAT_PEER_ID: int = int(os.getenv("CHAT_PEER_ID", "0"))

app: FastAPI = FastAPI()
vk_session: VkApi = VkApi(token=VK_TOKEN)

member_names: Dict[int, str] = {}
welcome_sent: Dict[int, bool] = {}
last_check_time: Dict[int, int] = {}
memory_lock = threading.Lock()

GROUPS: List[str] = [
    "https://vk.ru/club241519834", "https://vk.ru/club241781796", "https://vk.ru/club241187158",
    "https://vk.ru/maria_grechka", "https://vk.ru/feldberg.haos", "https://vk.ru/club242069966",
    "https://vk.ru/marinafinancelife", "https://vk.ru/club241309196", "https://vk.ru/krowka_lili",
    "https://vk.ru/club242398054", "https://vk.ru/club242182095",
    "https://vk.ru/abramov_daily", "https://vk.ru/club225748917", "https://vk.ru/club238235885",
    "https://vk.ru/club242418956",
]

WELCOME_TEXT: str = """🚪 ДОБРО ПОЖАЛОВАТЬ В ROYAL LOBBY!
Вы попали в приёмную закрытого клуба взаимного продвижения Royal ADV. Сейчас в нашей команде только активные участники, которые ежедневно и честно продвигают друг друга в ВК.
Чтобы получить пропуск в основное премиум-сообщество Royal ADV | Актив, вам необходимо выполнить главное условие клуба — оформить подписку на всех действующих резидентов.
✅ Действующие участники:
1. Александра Шлыкова — https://vk.ru/club241519834
2. Мария Макарова — https://vk.ru/club241781796
3. Инна Р — https://vk.ru/club241187158
4. Мария Ивлева — https://vk.ru/maria_grechka
5. Елизавета Фельдберг — https://vk.ru/feldberg.haos
6. Ирина Кулочкина — https://vk.ru/club242069966
7. Марина Нефёдова — https://vk.ru/marinafinancelife
8. Саида Тихомирова — https://vk.ru/club241309196
9. Ирина Остробокова — https://vk.ru/krowka_lili
10. Алёна Андреева — https://vk.ru/club242398054
12. Elena Karjala — https://vk.ru/club242182095
13. Marla Singer — https://vk.ru/club225748917
14. Татьяна Крявкина - https://vk.ru/club242418956
15. Татьяна Воронцова - https://vk.ru/id200006469384
16. Ирина Кузьмичева - https://vk.com/irina_chitaet
17. Нина Юшкова - https://vk.ru/ninaural11
18. Наталья Рахимовна - https://vk.ru/club242266727
📝 Что делать после подписки?
Как только вы подписались на все сообщества из списков выше — напишите в этот чат кодовое слово «ГОТОВО».
После проверки подписок администратор или бот одобрит вашу заявку на вход в главный чат активности.
🛡 Важно: Мы регулярно проверяем списки. Те, кто отпишется после входа в чат, будут забанены навсегда без права возврата!"""

SUCCESS_TEXT: str = "[id{uid}|{name}], проверка пройдена! ✅ Ожидайте админа."
FAIL_TEXT: str = "[id{uid}|{name}], проверка не пройдена. ❌ Вы не подписаны на:\n{groups}\n\nПодпишитесь и напишите «ГОТОВО» снова."

def extract_group_id(url: str):
    # Если в ссылке есть /club или /public, возвращаем всё после этого слова
    if "/club" in url:
        return url.split("club")[-1]   # Оставляем только цифры
    elif "/public" in url:
        return url.split("public")[-1] # Оставляем только цифры
    else:
        return None

def delete_message(peer_id: int, message_id: int) -> None:
    try:
        vk_session.method("messages.delete", {
            "message_ids": message_id,
            "delete_for_all": 1  # Удаляет для всех участников чата
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
        if response:
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

    async def process_request():
        with memory_lock:
            last_update_id = getattr(webhook, 'last_update_id', -1)
        
        update_id = data.get('update_id')
        if update_id is not None and update_id == last_update_id:
            print("[DEBUG] Дубликат события")
            return
        if update_id is not None:
            setattr(webhook, 'last_update_id', update_id)

        # *** ПРАВИЛЬНОЕ ПОЛУЧЕНИЕ СООБЩЕНИЯ ***
            msg = data.get("object", {}).get("message", {})
        
        # Для диагностики выводим ВСЁ содержимое сообщения
        print(f"[DEBUG] Полный объект сообщения: {data}")
        
        # *** КРИТИЧЕСКАЯ ПРОВЕРКА ***
        if not all([msg, msg.get('peer_id'), msg.get('from_id'), msg.get('text'), msg.get('id')]):
            print("[DEBUG] Получен неполный объект сообщения. Игнорируем.")
            return  # Выходим из обработчика, ничего не делаем

        if msg.get("peer_id") != CHAT_PEER_ID:
            return {"status": "not our chat"}

        from_id = msg.get("from_id")
        text = msg.get("text", "").strip().lower()
        action = msg.get("action")

        # --- ПРИВЕТСТВИЕ ---
        if action and action.get("type") == "chat_invite_user" and action.get("member_id") == from_id:
            with memory_lock:
                if not welcome_sent.get(from_id, False):
                    welcome_sent[from_id] = True
                    member_names[from_id] = get_user_name(from_id)
                    send_message(CHAT_PEER_ID, f"[id{from_id}|{member_names[from_id]}], {WELCOME_TEXT}")
            return {"status": "ok"}

        # --- ПРОВЕРКА ПОДПИСОК ---
        elif text == "готово":
            name = member_names.get(from_id, get_user_name(from_id))
            current_time = int(time.time())
            
            with memory_lock:
                last_time = last_check_time.get(from_id, 0)
            if current_time - last_time < 5:
                return {"status": "ok"}
            
            with memory_lock:
                last_check_time[from_id] = current_time

            # Мгновенно отвечаем пользователю
            send_message(CHAT_PEER_ID, f"[id{from_id}|{name}], пожалуйста ожидайте, идёт проверка...")

            # Убираем команду пользователя из общего чата
            msg_id = msg.get('id')
            if msg_id is not None:
                delete_message(CHAT_PEER_ID, msg_id)

            missing = []
            for url in GROUPS:
                gid_str = extract_group_id(url)
                if not gid_str:
                    continue
                
                try:
                    group_id_int = int(gid_str)
                    res = vk_session.method("groups.isMember", {"user_id": from_id, "group_id": group_id_int})
                    print(f"[DEBUG] Проверка {url} (ID: {group_id_int}) -> Ответ API: {res}")
                    
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
    asyncio.create_task(process_request())  # Запускаем долгую задачу параллельно

    return {"status": "ok"}  # Быстро отвечаем ВК!

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000, reload=False, workers=1)