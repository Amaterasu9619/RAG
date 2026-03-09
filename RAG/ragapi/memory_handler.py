import json
from typing import Dict, List, Optional
import time

from langchain.memory import ConversationBufferWindowMemory
from azure.cosmos import CosmosClient

class MemoryHandler:
    def __init__(self, cosmos_endpoint: str, cosmos_key: str, db_name: str = "chatbot", container_name: str = "sessions"):
        self.use_cosmos = bool(cosmos_endpoint and cosmos_key)
        if self.use_cosmos:
            self.client = CosmosClient(cosmos_endpoint, cosmos_key)
            self.db = self.client.get_database_client(db_name)
            self.container = self.db.get_container_client(container_name)
        else:
            self.client = None
            self.db = None
            self.container = None
        self.short_memories: Dict[str, ConversationBufferWindowMemory] = {}
        self.last_updated: Dict[str, int] = {}  # Only used when not using Cosmos

    def get_memory(self, session_id: str) -> ConversationBufferWindowMemory:
        if session_id not in self.short_memories:
            if self.use_cosmos:
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
            else:
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

        # Compute title from first human message
        first_human = next(
            (m["content"] for m in history_list if m["role"] == "human"),
            None
        )
        if first_human:
            title = first_human[:100]
            if len(first_human) > 100:
                title += "..."
        else:
            title = "New Conversation"

        if self.use_cosmos:
            item = {
                "id": session_id,
                "history": json.dumps(history_list),
                "title": title
            }
            self.container.upsert_item(item)
        else:
            self.last_updated[session_id] = int(time.time())

    def list_conversations(self, session_id: str) -> List[dict]:
        if self.use_cosmos:
            prefix = f"{session_id}:"
            query = """
            SELECT c.id, c.title, c._ts 
            FROM c 
            WHERE STARTSWITH(c.id, @prefix) OR c.id = @session_id
            """
            params = [
                {"name": "@prefix", "value": prefix},
                {"name": "@session_id", "value": session_id}
            ]
            items = list(self.container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True
            ))
        else:
            prefix = f"{session_id}:"
            items = []
            for sid in list(self.short_memories.keys()):
                if sid == session_id or sid.startswith(prefix):
                    # Compute title
                    mem = self.short_memories[sid]
                    hlist = [{"role": m.type, "content": m.content} for m in mem.chat_memory.messages]
                    first_h = next((m["content"] for m in hlist if m["role"] == "human"), None)
                    t = (first_h[:100] + ("..." if len(first_h or "") > 100 else "")) if first_h else "New Conversation"
                    items.append({
                        "id": sid,
                        "title": t,
                        "_ts": self.last_updated.get(sid, 0)
                    })

        conversations = []
        for itm in items:
            full_id = itm["id"]
            if ":" in full_id:
                conv_id = full_id.split(":", 1)[1]
                title = itm.get("title", "Untitled Thread")
            else:
                conv_id = None
                title = itm.get("title", "Main Conversation")

            conversations.append({
                "conversation_id": conv_id,
                "title": title,
                "last_updated": itm.get("_ts", 0)
            })
        conversations.sort(key=lambda x: x["last_updated"], reverse=True)

        return conversations

def apply_guardrails(query: str, response: str) -> str:
    if "harmful" in query.lower():
        return "I'm sorry, but I can't assist with that request."
    return response