import os
from typing import Optional, List

from fastapi import FastAPI
from pydantic import BaseModel

from rag_chain import rag_chain
from memory_handler import MemoryHandler, apply_guardrails

app = FastAPI(title="RAG Chatbot API")

class QueryRequest(BaseModel):
    query: str
    session_id: str = "default"
    conversation_id: Optional[str] = None

class ConversationInfo(BaseModel):
    conversation_id: Optional[str]
    title: str
    last_updated: int

memory_handler = MemoryHandler(
    cosmos_endpoint=os.getenv("COSMOS_ENDPOINT"),
    cosmos_key=os.getenv("COSMOS_KEY"),
)

@app.post("/query")
async def query_endpoint(req: QueryRequest):
    effective_session_id = req.session_id
    if req.conversation_id is not None:
        effective_session_id = f"{req.session_id}:{req.conversation_id}"

    memory = memory_handler.get_memory(effective_session_id)
    chat_history = memory.chat_memory.messages

    initial_state = {
        "query": req.query,
        "chat_history": chat_history,
    }

    result = rag_chain.invoke(initial_state)

    response = apply_guardrails(req.query, result["response"])

    memory.save_context(
        {"input": req.query},
        {"output": response}
    )

    memory_handler.save_memory(effective_session_id)

    sources = result.get("context", [])

    return {
        "answer": response,
        "sources": sources
    }

@app.get("/conversations/{session_id}", response_model=List[ConversationInfo])
def list_conversations(session_id: str):
    return memory_handler.list_conversations(session_id)

@app.get("/health")
def health():
    return {"status": "healthy"}