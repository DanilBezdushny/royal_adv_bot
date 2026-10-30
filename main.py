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
greeted_users = set()  # ID тех, кого уже приветствовали (чтобы не дублировать при перезапуске)
member_names = {}
last_check_time = {}   # Для предотвращения мгновенного повторного ответа "Готово"

def extract_group_id(url: str):
    if "/club" in url or "/public" in url:
        return url.split("/")[-1]
    elif url.startswith("https://vk.com/id"):
        # Извлекаем id пользователя из ссылок вида https://vk.com/id...
        return url.split("/id")[1].split()[0]  # Берём всё после /id до первого пробела
    else:
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
    return Response(content=CONFIRM_TOKEN, media_type="text/plain", status_code=200)

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
        
        if msg.get("peer_id") != CHAT_PEER_ID:
            return {"status": "not our chat"}

        from_id = msg.get("from_id")
        text = msg.get("text", "").strip().lower()
        action = msg.get("action")

        # --- НОВОЕ: ЕДИНОЕ ПРИВЕТСТВИЕ И ССЫЛКИ В ОДНОМ СООБЩЕНИИ ---
        # Приветствуем ТОЛЬКО если пользователь вошёл или его нет в памяти
        if (action and action.get("type") == "chat_invite_user" and action.get("member_id") == from_id) or (from_id not in greeted_users and from_id not in member_names):
            
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
                "Чтобы получить пропуск в основное премиум-сообщество Royal ADV | Актив, вам необходимо выполнить главное условие клуба — оформить подписку на всех действующих резидентов.\n\n"
                "📋 ШАГ 1: Подпишитесь на действующий список участников:\n\n"
                "✅ Действующие участники\n\n"
                "1. Александра Шлыкова — https://vk.ru/club241519834\n"
                "2. Мария Макарова — https://vk.ru/club241781796\n"
                "3. Инна Р — https://vk.ru/club241187158\n"
                "4. Мария Ивлева — https://vk.ru/maria_grechka\n"
                "5. Елизавета Фельдберг — https://vk.ru/feldberg.haos\n"
                "6. Ирина Кулочкина —https://vk.ru/club242069966\n"
                "7. Марина Нефёдова — https://vk.ru/marinafinancelife\n"
                "8. Саида Тихомирова — https://vk.ru/club241309196\n"
                "9. Ирина Остробокова — https://vk.ru/krowka_lili\n"
                "10. Алёна Андреева — https://vk.ru/club242399654\n"
                "11. Диана Каут — https://vk.ru/club236044126\n"
                "12. Elena Karjala — https://vk.ru/club242182095\n"
                "13. Marla Singer — https://vk.ru/club225748917\n"
                "14. Татьяна Крявкина - https://vk.ru/club242418956\n"
                "15. Татьяна Воронцова - https://vk.com/id200006469384\n"
                "16. Ирина Кузьмичева - https://vk.com/irina_chitaet\n"
                "17. Нина Юшкова - https://vk.ru/ninaural11\n"
                "18. Наталья Рахимовна - https://vk.ru/club242266727\n\n"
                "📝 Что делать после подписки?\n\n"
                "Как только вы подписались на все сообщества из списков выше — напишите в этот чат кодовое слово «ГОТОВО».\n"
                "После проверки подписок администратор или бот одобрит вашу заявку на вход в главный чат активности.\n\n"
                "🛡 Важно:\n\n"
                "Мы регулярно проверяем списки. Те, кто отпишется после входа в чат, будут забанены навсегда без права возврата!"
            )
            send_message(CHAT_PEER_ID, welcome_text)
            if action:
                return {"status": "ok"}  # Выходим сразу, если это было действие приглашения

        # --- ПРОВЕРКА ПОДПИСОК ---
        # Теперь берём группы прямо из текста приветствия!
        GROUPS = []
        for line in welcome_text.split("\n"):
            if "—" in line:
                parts = line.strip().split("—")
                link = parts[-1].strip()
                gid = extract_group_id(link)
                if gid:
                    GROUPS.append(gid)

        if text == "готово":
            name = member_names[from_id]

            # Проверка на повторное нажатие кнопки "Готово". Если прошло меньше секунды с прошлого раза — игнорируем.
            if time.time() - last_check_time.get(from_id, 0) < 1:
                return {"status": "ok"}

            last_check_time[from_id] = time.time()

            missing = []
            for gid in GROUPS:
                try:
                    res = vk_session.method("groups.isMember", {"user_id": from_id, "group_id": gid})
                    if res not in [1, 2]:
                        missing.append(gid)
                except Exception:
                    missing.append(gid)
            
            if not missing:
                success_text = (
                    "🎉 Поздравляем! Проверка успешно пройдена! 👑\n\n"
                    "Вы отлично справились со стартовыми условиями и становитесь резидентом нашего закрытого клуба Royal ADV!\n\n"
                    "📋 ВАШИ СЛЕДУЮЩИЕ ШАГИ:\n\n"
                    "1️⃣ Ожидайте смс админа: В ближайшее время администратор отправит вам в личные сообщения все рабочие ссылки-доступы на чаты нашей экосистемы (Главный чат активности, Чат для взаимных репостов и Чат для общения и нетворкинга) [⚡️].\n\n"
                    "👉 Пожалуйста, прямо сейчас убедитесь, что у вас открыты сообщения в профиле, чтобы админ смог до вас дописаться!\n\n"
                    "2️⃣ Пришлите вашу ссылку на взаимность: Пока вы ждете сообщения от администратора, отправьте прямо сюда (в этот чат приемной) ссылку на вашу группу или страницу. Она необходима, чтобы внести вас в наш общий кликабельный список клуба, и все действующие участники смогли подписаться на вас в ответ!\n\n"
                    "📌 После перехода в главный чат обязательно изучите закрепленное сообщение — там подробно расписаны правила, дедлайны и лимиты. Пожалуйста, займите свое место в каждом чате, чтобы оставаться в едином рабочем ритме команды!\n\n"
                    "Рады видеть в команде! Включаем королевские охваты! 📈🔥"
                )
                send_message(CHAT_PEER_ID, success_text)
            else:
                fail_text = (
                    "🛑 Проверка не пройдена! 👑\n\n"
                    "Наш бот проверил ресурсы и обнаружил, что вы подписались не на все обязательные сообщества администрации. У нас в клубе действуют строгие правила и 100% честность с первых шагов!\n\n"
                    "📋 ЧТО НУЖНО СДЕЛАТЬ ПРЯМО СЕЙЧАС:\n\n"
                    "• Проверьте абсолютно все подписки ещё раз на наличие оформленной подписки на каждое сообщество участников и руководителей.\n\n"
                    "⏳ Как только внимательно всё перепроверите и убедитесь, что подписаны на каждую группу администрации — напишите сюда кодовое слово «ГОТОВО» еще раз.\n\n"
                    "Включайте королевскую скорость, мы ждем вас в основном составе Royal ADV! 🤍✨"
                )
                final_message = f"[id{from_id}|❌] {name}, вот список групп, где обнаружена проблема:\n" + "\n".join(missing[:5]) + f"\n\n{fail_text}"
                send_message(CHAT_PEER_ID, final_message)

    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)