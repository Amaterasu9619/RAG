from fastapi import FastAPI, Depends
from pydantic import BaseModel
from rag_chain import rag_chain
from memory_handler import MemoryHandler
import os

app = FastAPI(title="RAG Chatbot API")

class QueryRequest(BaseModel):
    query: str
    session_id: str = "default"

memory_handler = MemoryHandler(os.getenv("COSMOS_ENDPOINT"), os.getenv("COSMOS_KEY"))

@app.post("/query")
def query_endpoint(req: QueryRequest):
    memory = memory_handler.get_memory(req.session_id)
    state = {"query": req.query, "session_id": req.session_id}
    result = rag_chain.invoke(state)
    response = apply_guardrails(req.query, result["response"])
    memory.save_context({"input": req.query}, {"output": response})
    memory_handler.save_memory(req.session_id)
    return {"answer": response, "sources": result["context"]}

@app.get("/health")
def health():
    return {"status": "healthy"}