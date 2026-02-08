from langchain.memory import ConversationBufferWindowMemory
from azure.cosmos import CosmosClient, PartitionKey
from typing import Dict, Optional
import json

class MemoryHandler:
    def __init__(self, cosmos_endpoint, cosmos_key, db_name="chatbot", container_name="sessions"):
        self.client = CosmosClient(cosmos_endpoint, cosmos_key)
        self.db = self.client.get_database_client(db_name)
        self.container = self.db.get_container_client(container_name)
        self.short_memories: Dict[str, ConversationBufferWindowMemory] = {}  # session_id -> memory

    def get_memory(self, session_id: str) -> ConversationBufferWindowMemory:
        if session_id not in self.short_memories:
            # Load long-term
            query = "SELECT * FROM c WHERE c.id = @id"
            params = [{"name": "@id", "value": session_id}]
            item = list(self.container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
            history = json.loads(item[0]["history"]) if item else []
            memory = ConversationBufferWindowMemory(k=5)
            for msg in history:
                memory.chat_memory.add_user_message(msg["user"])
                memory.chat_memory.add_ai_message(msg["ai"])
            self.short_memories[session_id] = memory
        return self.short_memories[session_id]

    def save_memory(self, session_id: str):
        memory = self.get_memory(session_id)
        history = [{"user": msg["content"], "ai": memory.chat_memory.messages[-1]["content"]} for msg in memory.chat_memory.messages if msg["type"] == "human"]
        item = {"id": session_id, "history": json.dumps(history)}
        self.container.upsert_item(item)

# Guardrails placeholder
def apply_guardrails(query: str, response: str) -> str:
    # Future: Integrate NeMo Guardrails
    # e.g., from nemoguardrails import RailsConfig, LLMRails
    # config = RailsConfig.from_path("guardrails_config")
    # rails = LLMRails(config)
    # response = rails.generate(messages=[{"role": "user", "content": query}])
    if "harmful" in query.lower():  # Simple check
        return "Response blocked for safety."
    return response