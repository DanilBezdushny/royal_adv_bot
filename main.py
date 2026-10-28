from fastapi import FastAPI, Request, Response
import os
import json
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

# --- База данных в памяти (чтобы не спамить приветствием) ---
# Словарь: {user_id: True} — значит, приветствие уже отправлено.
user_welcomed = {}

# --- ОБНОВЛЕННЫЙ СПИСОК ГРУПП (скопировал из твоего сообщения) ---
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
        msg = data.get("object", {}).get("message", {})
        
        if msg.get("peer_id") != CHAT_PEER_ID:
            return {"status": "not our chat"}

        from_id = msg.get("from_id")
        text = msg.get("text", "").strip().lower()
        action = msg.get("action")

        # --- 1. ПРИВЕТСТВИЕ НОВОГО ЧЕЛОВЕКА ---
        if action and action.get("type") == "chat_invite_user":
            member_id = action.get("member_id")
            
            # Проверяем, здоровались ли мы уже с ним
            if member_id not in user_welcomed:
                # Запоминаем, что поздоровались
                user_welcomed[member_id] = True
                
                welcome_text = (
                    "👑 ДОБРО ПОЖАЛОВАТЬ В ROYAL LOBBY | ВХОД В ЧАТ АКТИВНОСТИ\n\n"
                    "Чтобы получить пропуск в основное премиум-сообщество Royal ADV | Актив, вам необходимо выполнить главное условие клуба — оформить подписку на всех действующих резидентов.\n\n"
                    "⚜️ Каналы админов:\n"
                    "1. Татьяна Ковбасюк\n"
                    "2. Олеся Тертишникова\n"
                    "3. Bedroom Moder \n\n"
                    "✅ Действующие участники:\n"
                    "1. Александра Шлыкова — https://vk.ru/club241519834\n"
                    "2. Мария Макарова — https://vk.ru/club241781796\n"
                    "3. Инна Р — https://vk.ru/club241187158\n"
                    "4. Мария Ивлева — https://vk.ru/maria_grechka\n"
                    "5. Елизавета Фельдберг — https://vk.ru/feldberg.haos\n"
                    "6. Ирина Кулочкина — https://vk.ru/club242069966\n"
                    "7. Марина Нефёдова — https://vk.ru/marinafinancelife\n"
                    "8. Саида Тихомирова — https://vk.ru/club241309196\n"
                    "9. Миля Риклановна — https://vk.ru/mi.a.deko\n"
                    "10. Ирина Остробокова — https://vk.ru/krowka_lili\n"
                    "11. Алёна Андреева — https://vk.ru/club242398054\n"
                    "12. Диана Каут — https://vk.ru/club236044126\n"
                    "13. Elena Karjala — https://vk.ru/club242182095\n"
                    "14. Алексей Абрамов — https://vk.ru/abramov_daily\n"
                    "15. Marla Singer — https://vk.ru/club225748917\n"
                    "16. Анастасия Лопатина — https://vk.ru/club238235885\n"
                    "17. Татьяна Крявкина — https://vk.ru/club242418956\n\n"
                    "📝 Что делать после подписки?\n"
                    "Как только вы подписались на все сообщества из списков выше — напишите в этот чат кодовое слово «ГОТОВО».\n"
                    "После проверки подписок администратор или бот одобрит вашу заявку на вход в главный чат активности.\n\n"
                    "🛡 Важно:\n"
                    "Мы регулярно проверяем списки. Те, кто отпишется после входа в чат, будут забанены навсегда без права возврата!"
                )
                send_message(CHAT_PEER_ID, f"[id{member_id}|Участник]\n{welcome_text}")

        # --- 2. ПРОВЕРКА ПОДПИСОК (только слово ГОТОВО) ---
        if text == "готово":
            # Защита от тех, кто зашел, но мы их еще не приветствовали (на всякий случай)
            if from_id not in user_welcomed:
                send_message(CHAT_PEER_ID, f"[id{from_id}|Ошибка] Сначала бот должен вас поприветствовать. Если этого не произошло — напишите админу.")
                return {"status": "ok"}

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
                send_message(CHAT_PEER_ID, f"[id{from_id}|✅] Проверка пройдена! Ожидайте, пока админ добавит вас в основной чат.")
            else:
                miss_text = "\n".join(missing[:5])
                send_message(CHAT_PEER_ID, f"[id{from_id}|❌] Проверка не пройдена. Вы не подписаны на:\n{miss_text}\n\nПодпишитесь и напишите «ГОТОВО» снова.")

    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)