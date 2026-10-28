import os
from dotenv import load_dotenv

load_dotenv()

VK_COMMUNITY_TOKEN = os.getenv("VK_COMMUNITY_TOKEN")
CHAT_PEER_ID = int(os.getenv("CHAT_PEER_ID"))
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))