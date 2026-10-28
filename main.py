import logging
from bot_logic import RoyalADVBot
from config import VK_COMMUNITY_TOKEN, CHAT_PEER_ID, ADMIN_IDS

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s]: %(message)s')

if __name__ == "__main__":
    bot = RoyalADVBot()
    bot.init_vk(VK_COMMUNITY_TOKEN, CHAT_PEER_ID, ADMIN_IDS)
    print("Royal ADV Bot started!")
    bot.run_polling()