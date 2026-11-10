from fastapi import FastAPI, Request, Response
import os
import time
import threading
from typing import Optional, Dict, List
from vk_api import VkApi
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id
from dotenv import load_dotenv
import logging
import asyncio

load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

VK_TOKEN: str = os.getenv("VK_COMMUNITY_TOKEN", "")
CONFIRM_TOKEN: str = os.getenv("CONFIRMATION_TOKEN", "")
SECRET_KEY: str = os.getenv("SECRET_KEY", "")
CHAT_PEER_ID: int = int(os.getenv("CHAT_PEER_ID", "0"))
GROUP_ID: int = int(os.getenv("GROUP_ID", "0"))

app: FastAPI = FastAPI()
vk_session: VkApi = VkApi(token=VK_TOKEN)
longpoll: VkLongPoll = VkLongPoll(vk_session, GROUP_ID)

# Кэш имён пользователей: {user_id: {"name": str, "time": timestamp}}
user_cache: Dict[int, Dict[str, object]] = {}
WELCOME_SENT: Dict[int, int] = {}
LAST_CHECK_TIME: Dict[int, int] = {}
CACHE_TTL = 3600  # 1 час
CLEANUP_INTERVAL = 600  # 10 минут
memory_lock = threading.Lock()

GROUPS: List[str] = [
    "https://vk.ru/club241519834", "https://vk.ru/club241187158", "https://vk.ru/club242998896", 
    "https://vk.ru/feldberg.haos", "https://vk.ru/club242069966", "https://vk.ru/club241309196", 
    "https://vk.ru/krowka_lili", "https://vk.ru/club242398054", "https://vk.ru/club242182095",
    "https://vk.ru/kovbasyuk_family", "https://vk.ru/club242418956", "https://vk.ru/club211715075",
    "https://vk.ru/bedroomwriters", "https://vk.ru/club236044126","https://vk.com/irina_chitaet", 
    "https://vk.ru/ninaural11", "https://m.vk.ru/club241287678", "https://vk.ru/club241390956", 
    "https://vk.ru/club242069751",
]

WELCOME_TEXT: str = """🚪[id{uid}|{name}], ДОБРО ПОЖАЛОВАТЬ В ROYAL LOBBY!

Вы попали в приемную закрытого клуба взаимного продвижения Royal ADV. Сейчас в нашей команде только активные участники, которые ежедневно и честно продвигают друг друга в ВК.

Чтобы получить пропуск в основное премиум-сообщество Royal ADV | Актив, вам необходимо выполнить главное условие клуба — оформить подписку на всех действующих резидентов.

⚜️ Каналы админов (тоже подписка) 

1. Татьяна Ковбасюк - https://vk.ru/kovbasyuk_family
2. Олеся Тертишникова - https://vk.ru/club211715075
3. Bedroom Moder - https://vk.ru/bedroomwriters

✅ Действующие участники:
1. Александра Шлыкова — https://vk.ru/club241519834
2. Инна Р — https://vk.ru/club241187158
3. Мария Ивлева — https://vk.ru/club242998896
4. Елизавета Фельдберг — https://vk.ru/feldberg.haos
5. Ирина Кулочкина —https://vk.ru/club242069966
6. Саида Тихомирова — https://vk.ru/club241309196
7. Ирина Остробокова — https://vk.ru/krowka_lili
8. Алёна Андреева — https://vk.ru/club242398054 
9. Диана Каут — https://vk.ru/club236044126
10. Elena Karjala — https://vk.ru/club242182095
11. Татьяна Крявкина - https://vk.ru/club242418956
12. Ирина Кузьмичева - https://vk.com/irina_chitaet
13. Нина Юшкова  - https://vk.ru/ninaural11
14. Ulyana Ryzhkova  - https://m.vk.ru/club241287678
15. Alya Alya - https://vk.ru/club241390956
16. Любовь Абрамова — https://vk.ru/club242069751

📝 Что делать после подписки?
Как только вы подписались на все сообщества из списков выше — напишите в этот чат кодовое слово «ГОТОВО».
После проверки подписок администратор или бот одобрит вашу заявку на вход в главный чат активности

⚠️ Важно: Мы регулярно проверяем списки. Те, кто отписывается после входа, удаляются навсегда без права возврата. Давайте расти честно!"""

SUCCESS_TEXT: str = """[id{uid}|{name}], 🎉 Поздравляем! Проверка успешно пройдена! 👑

Вы отлично справились со стартовыми условиями и становитесь резидентом нашего закрытого клуба Royal ADV!

📋 ВАШИ СЛЕДУЮЩИЕ ШАГИ:

1️⃣ Ожидайте смс админа: В ближайшее время администратор отправит вам в личные сообщения все рабочие ссылки-доступы на чаты нашей экосистемы (Главный чат активности, Чат для взаимных репостов и Чат для общения и нетворкинга) [⚡️].

👉 Пожалуйста, прямо сейчас убедитесь, что у вас открыты сообщения в профиле, чтобы админ смог до вас дописаться!

2️⃣ Пришлите вашу ссылку на взаимность: Пока вы ждете сообщения от администратора, отправьте прямо сюда (в этот чат приемной) ссылку на вашу группу или страницу. Она необходима, чтобы внести вас в наш общий кликабельный список клуба, и все действующие участники смогли подписаться на вас в ответ!

📌 После перехода в главный чат обязательно изучите закрепленное сообщение — там подробно расписаны правила, дедлайны и лимиты. Пожалуйста, займите свое место в каждом чате, чтобы оставаться в едином рабочем ритме команды!

Рады видеть в команде! Включаем королевские охваты! 📈🔥"""

FAIL_TEXT: str = """[id{uid}|{name}], 🛑 Проверка не пройдена! 👑

Наш бот проверил ресурсы и обнаружил, что вы подписались не на все обязательные сообщества администрации. У нас в клубе действуют строгие правила и 100% честность с первых шагов!

📋 ЧТО НУЖНО СДЕЛАТЬ ПРЯМО СЕЙЧАС:

• Проверьте абсолютно все подписки ещё раз на наличие оформленной подписки на каждое сообщество участников и руководителей.

⏳ Как только внимательно всё перепроверите и убедитесь, что подписаны на каждую группу администрации — напишите сюда кодовое слово «ГОТОВО» еще раз.

Включайте королевскую скорость, мы ждем вас в основном составе Royal ADV! 🤍✨"""


def extract_group_id(url: str) -> Optional[int]:
    """Извлекает ID группы из ссылки."""
    for prefix in ("club", "public"):
        if prefix in url:
            try:
                return int(url.split(prefix)[-1].split("&")[0].split("/")[0])
            except ValueError:
                return None
    return None


def _cleanup_cache() -> None:
    """Очищает устаревшие записи из кэша."""
    now = int(time.time())
    with memory_lock:
        stale_ids = [
            uid for uid, data in user_cache.items()
            if now - data["time"] > CACHE_TTL * 2
        ]
        for uid in stale_ids:
            del user_cache[uid]
        
        expired_checks = [
            uid for uid, t in LAST_CHECK_TIME.items()
            if now - t > CACHE_TTL
        ]
        for uid in expired_checks:
            del LAST_CHECK_TIME[uid]
        
        expired_welcome = [
            uid for uid, ts in WELCOME_SENT.items()
            if now - ts > CACHE_TTL
        ]
        for uid in expired_welcome:
            del WELCOME_SENT[uid]


def get_user_name(user_id: int) -> str:
    """Получает имя пользователя с TTL-кэшированием."""
    now = int(time.time())
    with memory_lock:
        cached = user_cache.get(user_id)
        if cached and now - cached["time"] < CACHE_TTL:
            return cached["name"]
    
    try:
        response = vk_session.method("users.get", {
            "user_ids": user_id,
            "fields": "first_name,last_name"
        })
        if response:
            user = response[0]
            name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            name = name if name else "Участник"
            
            with memory_lock:
                user_cache[user_id] = {"name": name, "time": now}
            return name
    except Exception as e:
        logger.error(f"Ошибка получения имени пользователя {user_id}: {e}")
    
    return "Участник"


def delete_message(peer_id: int, message_id: int) -> None:
    try:
        vk_session.method("messages.delete", {
            "message_ids": message_id,
            "delete_for_all": 1
        })
    except Exception as e:
        logger.error(f"Delete error: {e}")


def send_message(peer_id: int, message: str) -> None:
    try:
        vk_session.method("messages.send", {
            "peer_id": peer_id,
            "message": message,
            "random_id": get_random_id(),
            "dont_parse_links": 1
        })
    except Exception as e:
        logger.error(f"Send error: {e}")


def check_group_membership(user_id: int, group_ids: List[int]) -> List[str]:
    """
    Проверяет подписку пользователя на группы через batch-запрос VK API.
    Возвращает список неподписанных групп.
    """
    missing = []
    
    # VK API batch limit is 100, we have ~17 groups so it's fine
    for group_id in group_ids:
        try:
            res = vk_session.method("groups.isMember", {
                "user_id": user_id,
                "group_id": group_id
            })
            
            # Handle private group (error 203)
            if isinstance(res, dict) and 'error' in res:
                if res['error']['error_code'] == 203:
                    continue  # Private group, assume subscribed
                elif res['error']['error_code'] == 8:
                    continue  # Rate limited, skip
            
            if res not in (1, 2):
                # Find the URL for this group ID
                url = next((u for u, gid in zip(GROUPS, GROUP_IDS) if gid == group_id), "unknown")
                missing.append(url)
                
        except Exception as e:
            logger.error(f"API error for group {group_id}: {e}")
            # On error, assume not subscribed to be safe
            url = next((u for u, gid in zip(GROUPS, GROUP_IDS) if gid == group_id), "unknown")
            missing.append(url)
    
    return missing


# Pre-extract group IDs once at startup
GROUP_IDS: List[int] = []
for url in GROUPS:
    gid = extract_group_id(url)
    GROUP_IDS.append(gid if gid is not None else 0)


@app.on_event("startup")
async def startup_event():
    """Запускает фоновую очистку кэша."""
    import asyncio
    
    async def cleanup_loop():
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL)
            try:
                _cleanup_cache()
                logger.info("Cache cleanup completed")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    asyncio.create_task(cleanup_loop())


@app.get("/")
async def confirmation() -> Response:
    return Response(content=CONFIRM_TOKEN, media_type="text/plain", status_code=200)


@app.post("/")
async def webhook(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"JSON parse error: {e}")
        return Response(content="ok", status_code=200)

    if data.get("secret") != SECRET_KEY:
        return Response(content="ok", status_code=200)
    
    # Обработка запроса
    async def process_request(data):
        update_id = data.get("update_id")
        if update_id is not None:
            with memory_lock:
                last_update_id = getattr(webhook, 'last_update_id', -1)
                if update_id == last_update_id:
                    return
                webhook.last_update_id = update_id

        msg = data.get("object", {}).get("message", {})
        action = msg.get("action")
        peer_id = msg.get("peer_id")
        from_id = msg.get("from_id")

        if not all([peer_id, from_id]):
            return

        text = msg.get("text", "").strip().lower()

        action_type = action.get("type") if action else None
        action_member_id = action.get("member_id") if action else None

        # --- КИК ИЗ ЧАТА ---
        if action_type == "chat_kick_user" and action_member_id and peer_id == CHAT_PEER_ID:
            with memory_lock:
                WELCOME_SENT.pop(action_member_id, None)
                LAST_CHECK_TIME.pop(action_member_id, None)
            name = get_user_name(action_member_id)
            send_message(CHAT_PEER_ID, f"[id{action_member_id}|{name}] был переведен в основную беседу✅")
            return

        # --- ПРИВЕТСТВИЕ (приглашение или вход по ссылке) ---
        if action_member_id and peer_id == CHAT_PEER_ID and action_type in ("chat_invite_user", "chat_join_user"):
            with memory_lock:
                if not WELCOME_SENT.get(action_member_id):
                    WELCOME_SENT[action_member_id] = int(time.time())

            name = get_user_name(action_member_id)
            logger.info(f"Sending welcome to ID={action_member_id}: {name}")
            send_message(CHAT_PEER_ID, WELCOME_TEXT.format(uid=action_member_id, name=name))
            return

        # --- ПРОВЕРКА ПОДПИСОК ---
        if text == "готово" and peer_id == CHAT_PEER_ID:
            now = int(time.time())
            
            with memory_lock:
                last_time = LAST_CHECK_TIME.get(from_id, 0)
            
            # Rate limiting: 5 секунд между проверками
            if now - last_time < 5:
                return
            
            with memory_lock:
                LAST_CHECK_TIME[from_id] = now

            name = get_user_name(from_id)
            
            # Фильтруем валидные group IDs
            valid_group_ids = [gid for gid in GROUP_IDS if gid > 0]
            missing_urls = check_group_membership(from_id, valid_group_ids)

            if not missing_urls:
                send_message(CHAT_PEER_ID, SUCCESS_TEXT.format(uid=from_id, name=name))
                logger.info(f"User {from_id} passed verification")
            else:
                miss_text = "\n".join(missing_urls[:5])
                send_message(CHAT_PEER_ID, FAIL_TEXT.format(uid=from_id, name=name))
                logger.info(f"User {from_id} failed verification, missing: {len(missing_urls)} groups")

    asyncio.create_task(process_request(data))
    return Response(content="ok", status_code=200)


def start_longpoll():
    """Запускает Longpoll сервер для отслеживания входа участников."""
    logger.info("Starting Longpoll server...")
    
    while True:
        try:
            for long_event in longpoll.longpoll():
                if long_event.type == VkEventType.CHAT_JOIN_USER:
                    user_id = long_event.user_id
                    logger.info(f"Longpoll: user {user_id} joined chat")
                    
                    with memory_lock:
                        if not WELCOME_SENT.get(user_id):
                            WELCOME_SENT[user_id] = int(time.time())
                    
                    name = get_user_name(user_id)
                    send_message(CHAT_PEER_ID, WELCOME_TEXT.format(uid=user_id, name=name))
        except Exception as e:
            logger.error(f"Longpoll error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    import uvicorn
    
    # Запускаем Longpoll в отдельном потоке
    longpoll_thread = threading.Thread(target=start_longpoll, daemon=True)
    longpoll_thread.start()
    logger.info("Longpoll thread started")
    
    uvicorn.run(app, host="0.0.0.0", port=3000, reload=False, workers=1)
