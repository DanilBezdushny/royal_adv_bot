from fastapi import FastAPI, Request, Response
import os
import time
from typing import Optional, Dict, List
from vk_api import VkApi
from vk_api.utils import get_random_id
from dotenv import load_dotenv
import logging
import asyncio
import threading

load_dotenv()

from config import GROUPS, WELCOME_TEXT, SUCCESS_TEXT, FAIL_TEXT

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

VK_TOKEN: str = os.getenv("VK_COMMUNITY_TOKEN", "")
CONFIRM_TOKEN: str = os.getenv("CONFIRMATION_TOKEN", "")
SECRET_KEY: str = os.getenv("SECRET_KEY", "")
CHAT_PEER_ID: int = int(os.getenv("CHAT_PEER_ID", "0"))

app: FastAPI = FastAPI()
vk_session: VkApi = VkApi(token=VK_TOKEN)

# Кэш имён пользователей: {user_id: {"name": str, "time": timestamp}}
user_cache: Dict[int, Dict[str, object]] = {}
WELCOME_SENT: Dict[int, int] = {}
LAST_CHECK_TIME: Dict[int, int] = {}
CACHE_TTL = 3600  # 1 час
CLEANUP_INTERVAL = 600  # 10 минут
memory_lock = threading.Lock()


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000, reload=False, workers=1)
