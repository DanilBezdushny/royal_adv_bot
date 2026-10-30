from fastapi import FastAPI, Request, Response
import os
import json
import time
from vk_api import VkApi
from vk_api.utils import get_random_id
from dotenv import load_dotenv

load_dotenv()

# --- Настройки ---
VK_TOKEN = os.getenv("VK_COMMUNITY_TOKEN")
CONFIRM_TOKEN = os.getenv("CONFIRMATION_TOKEN")
SECRET_KEY = os.getenv("SECRET_KEY")
CHAT_PEER_ID = int(os.getenv("CHAT_PEER_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))

app = FastAPI()
vk_session = VkApi(token=VK_TOKEN)

# --- Память бота ---
# Словарь для хранения ID тех, кого бот уже приветствовал в этой сессии
# Это временная защита. При перезапуске бота данные сбросятся.
greeted_users = set() 

member_names = {}
last_check_time = {}

# --- Список групп ---
GROUPS = [
    "https://vk.ru/club241519834",
    "https://vk.ru/club241781796",
    "https://vk.ru/club241187158",
    "https://vk.ru/maria_grechka",
    "https://vk.ru/feldberg.haos",
    "https://vk.ru/club242069966",
    "https://vk.ru/marinafinancelife",
    "https://vk.ru/club241309196",
    "https://vk.ru/mi.a.deko",
    "https://vk.ru/krowka_lili",
    "https://vk.ru/club242398054",
    "https://vk.ru/club236044126",
    "https://vk.ru/club242182095",
    "https://vk.ru/abramov_daily",
    "https://vk.ru/club225748917",
    "https://vk.ru/club238235885",
    "https://vk.ru/club242418956",
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

# --- ГЛАВНАЯ СТРАНИЦА ---
@app.get("/")
async def confirmation():
    return Response(content=CONFIRM_TOKEN, media_type="text/plain", status_code=200)

# --- ВЕБХУК ---
@app.post("/")
async def webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"error": "invalid json"}

    if data.get("secret") != SECRET_KEY:
        return {"error": "invalid secret"}

    if data.get("type") == "confirmation":
        return Response(content=CONFIRM_TOKEN, media_type="text/plain", status_code=200)

    if data.get("type") == "message_new":
        msg = data.get("object", {})
        
        # Фильтр только для нашего чата
        if msg.get("peer_id") != CHAT_PEER_ID:
            return {"status": "not our chat"}

        from_id = msg.get("from_id")
        text = msg.get("text", "").strip().lower()
        action = msg.get("action")

        # --- НОВОЕ: ПРИВЕТСТВИЕ ПРИ ВХОДЕ В БЕСЕДУ ---
        # Срабатывает, когда пользователя приглашают (action.type == chat_invite_user)
        # или когда он пишет первое сообщение, но его еще нет в памяти бота.
        if (action and action.get("type") == "chat_invite_user" and action.get("member_id") == from_id) or (from_id not in greeted_users and from_id not in member_names):
            
            # Ставим в память, чтобы не дублировать приветствие в рамках одной сессии
            greeted_users.add(from_id)
            member_names[from_id] = "loading" 
            
            try:
                response = vk_session.method("users.get", {"user_ids": from_id, "fields": "first_name, last_name"})
                if response:
                    user = response[0]
                    full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                    member_names[from_id] = full_name
                else:
                    member_names[from_id] = "Участник"
            except Exception:
                member_names[from_id] = "Участник"

            name = member_names[from_id]
            welcome_text = (
                f"🚪 [id{from_id}|{name}], ДОБРО ПОЖАЛОВАТЬ В ROYAL LOBBY!\n\n"
                "Вы попали в приемную закрытого клуба взаимного продвижения Royal ADV. Сейчас в нашей команде только активные участники, которые ежедневно и честно продвигают друг друга в ВК.\n\n"
                "Чтобы получить пропуск в главный чат активности, выполните обязательное условие:\n"
                "📋 ШАГ 1: Подпишитесь на действующий список участников (он находится в закрепленном сообщении этого чата 👆).\n"
                "💬 ШАГ 2: Как только подпишетесь на всех — напишите в этот чат кодовое слово: ГОТОВО\n\n"
                "После проверки подписок администратор одобрит вашу заявку и пришлет ссылку на главный чат активности! 🚀\n\n"
                "⚠️ Важно: Мы регулярно проверяем списки. Те, кто отписывается после входа, удаляются навсегда без права возврата. Давайте расти честно!"
            )
            send_message(CHAT_PEER_ID, welcome_text)
            # Если это было действие входа, дальше обрабатывать сообщение не нужно
            if action:
                return {"status": "ok"}

        # --- ПРОВЕРКА ПОДПИСОК (остается без изменений) ---
        if text == "готово":
            name = member_names[from_id]
            current_time = int(time.time())

            if (current_time - last_check_time.get(from_id, 0)) < 5:
                return {"status": "ok"}
            
            last_check_time[from_id] = current_time

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
                send_message(CHAT_PEER_ID, f"[id{from_id}|✅] {name}, проверка пройдена! Ожидайте админа.")
            else:
                miss_text = "\n".join(missing[:5])
                send_message(CHAT_PEER_ID, f"[id{from_id}|❌] {name}, проверка не пройдена. Вы не подписаны на:\n{miss_text}\n\nПодпишитесь и напишите «ГОТОВО» снова.")

    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)