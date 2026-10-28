import time
import random
import logging
from typing import List, Dict, Optional
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id


class RoyalADVBot:
    def __init__(self):
        self.vk_session = None
        self.longpoll = None
        self.chat_peer_id = None
        self.admin_ids = []
        self.required_groups = [
            "https://vk.ru/club241519834",
            "https://vk.ru/club241781796",
            # ... остальные группы из твоего списка ...
            "https://vk.ru/club242640706"
        ]
        self.logger = logging.getLogger(__name__)
    
    def init_vk(self, token: str, chat_peer_id: int, admin_ids: List[int]):
        self.vk_session = VkApi(token=token)
        self.longpoll = VkBotLongPoll(self.vk_session, group_id=self.vk_session.token["group_id"])
        self.chat_peer_id = chat_peer_id
        self.admin_ids = admin_ids
    
    @staticmethod
    def extract_group_id(url: str) -> Optional[str]:
        if "/club" in url or "/public" in url:
            return url.split("/")[-1]
        elif "/" not in url and url.startswith("vk"):
            return url.replace("vk.", "")
        else:
            return None
    
    def is_user_subscribed_to_all(self, user_id: int) -> bool:
        for group_url in self.required_groups:
            group_id = self.extract_group_id(group_url)
            try:
                result = self.vk_session.method(
                    "groups.isMember",
                    {"user_id": user_id, "group_id": group_id}
                )
                if not result:
                    return False
            except Exception as e:
                self.logger.warning(f"Error checking subscription {group_url}: {e}")
                continue
        return True
    
    def send_message(self, peer_id: int, message: str):
        try:
            self.vk_session.method(
                "messages.send",
                {
                    "peer_id": peer_id,
                    "message": message,
                    "random_id": get_random_id(),
                    "dont_parse_links": 1
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
    
    def handle_new_member(self, member_id: int):
        welcome_text = (
            "🚪 ДОБРО ПОЖАЛОВАТЬ В ROYAL LOBBY!\n\n"
            "Вы попали в приемную закрытого клуба взаимного продвижения Royal ADV.\n"
            "Сейчас в нашей команде только активные участники, которые ежедневно и честно продвигают друг друга в ВК.\n"
            "Чтобы получить пропуск в главный чат активности, выполните обязательное условие:\n"
            "📋 ШАГ 1: Подпишитесь на действующий список участников.\n"
            "💬 ШАГ 2: Как только подпишетесь на всех — напишите в этот чат кодовое слово: ГОТОВО\n"
            "После проверки подписок администратор одобрит вашу заявку и пришлет ссылку на главный чат активности! 🚀\n"
            "⚠️ Важно: Мы регулярно проверяем списки. Те, кто отписывается после входа, удаляются навсегда без права возврата. Давайте расти честно!"
        )
        self.send_message(peer_id=self.chat_peer_id, message=f"[id{member_id}|Новый участник], добро пожаловать!\n{welcome_text}")
    
    def handle_user_message(self, from_id: int, text: str):
        if text.lower() == "согласен":
            groups_list = "\n".join([f"{i+1}. {url}" for i, url in enumerate(self.required_groups)])
            
            instructions = (
                "Чтобы получить пропуск в основное премиум-сообщество Royal ADV | Актив, вам необходимо выполнить главное условие клуба — оформить подписку на всех действующих резидентов.\n\n"
                "🔹 Каналы админов:\n"
                "- Татьяна Ковбасюк\n"
                "- Олеся Тертишникова\n"
                "- Bedroom Moder \n\n"
                "✅ Действующие участники:\n"
                f"{groups_list}\n\n"
                "📝 Что делать после подписки?\n"
                "Как только вы подписались на все сообщества из списков выше — напишите в этот чат кодовое слово «ГОТОВО».\n"
                "После проверки подписок администратор или бот одобрит вашу заявку на вход в главный чат активности.\n"
                "🛡 Важно: Мы регулярно проверяем списки. Те, кто отпишется после входа в чат, будут забанены навсегда без право возврата!"
            )
            self.send_message(peer_id=self.chat_peer_id, message=f"[id{from_id}|Участник], спасибо за согласие!\n{instructions}")
        
        elif text.strip().lower() == "готово":
            missing_groups = []
            for group_url in self.required_groups:
                group_id = self.extract_group_id(group_url)
                subscribed = self.vk_session.method(
                    "groups.isMember",
                    {"user_id": from_id, "group_id": group_id}
                )
                if not subscribed:
                    missing_groups.append(group_url)
            
            if not missing_groups:
                self.send_message(peer_id=self.chat_peer_id, message=f"[id{from_id}|Отлично]! Проверка пройдена успешно, пожалуйста ожидайте пока Администратор добавит Вас в беседу.")
                # Здесь можно добавить логику уведомления администратора
            else:
                missing_list = "\n".join(missing_groups[:5])
                self.send_message(peer_id=self.chat_peer_id, message=f"[id{from_id}|Внимание]!\nПроверка не пройдена. Пожалуйста, подпишитесь на следующие сообщества:\n{missing_list}")
    
    def run(self):
        while True:
            try:
                for event in self.longpoll.listen():
                    if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                        if event.obj.message.get('action') and event.obj.message['action'].get('type') == 'chat_invite_user':
                            invited_user_id = event.obj.message['action']['member_id']
                            self.handle_new_member(invited_user_id)
                        
                        elif event.obj.message.get('text'):
                            self.handle_user_message(event.obj.message['from_id'], event.obj.message['text'])
            except Exception as e:
                self.logger.exception("Main loop error:")
                time.sleep(random.randint(5, 15))