import json
from typing import Dict

from langchain.memory import ConversationBufferWindowMemory
from azure.cosmos import CosmosClient

class MemoryHandler:
    def __init__(self, cosmos_endpoint: str, cosmos_key: str, db_name: str = "chatbot", container_name: str = "sessions"):
        self.client = CosmosClient(cosmos_endpoint, cosmos_key)
        self.db = self.client.get_database_client(db_name)
        self.container = self.db.get_container_client(container_name)
        self.short_memories: Dict[str, ConversationBufferWindowMemory] = {}

    def get_memory(self, session_id: str) -> ConversationBufferWindowMemory:
        if session_id not in self.short_memories:
            try:
                query = "SELECT * FROM c WHERE c.id = @id"
                params = [{"name": "@id", "value": session_id}]
                items = list(self.container.query_items(
                    query=query,
                    parameters=params,
                    enable_cross_partition_query=True
                ))
                history_list = json.loads(items[0]["history"]) if items else []
            except Exception:
                history_list = []

            memory = ConversationBufferWindowMemory(k=10)
            for msg in history_list:
                if msg["role"] == "human":
                    memory.chat_memory.add_user_message(msg["content"])
                elif msg["role"] == "ai":
                    memory.chat_memory.add_ai_message(msg["content"])

            self.short_memories[session_id] = memory

        return self.short_memories[session_id]

    def save_memory(self, session_id: str):
        memory = self.get_memory(session_id)
        history_list = [
            {"role": m.type, "content": m.content}
            for m in memory.chat_memory.messages
        ]
        item = {
            "id": session_id,
            "history": json.dumps(history_list)
        }
        self.container.upsert_item(item)

def apply_guardrails(query: str, response: str) -> str:
    if "harmful" in query.lower():
        return "I'm sorry, but I can't assist with that request."
    return response