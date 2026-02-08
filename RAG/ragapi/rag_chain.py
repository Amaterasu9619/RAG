import os
import pickle
from typing import List

from azure.storage.blob import BlobServiceClient
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from typing import TypedDict

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-35-turbo")
STORAGE_CONN = os.getenv("AZURE_STORAGE_CONNECTION")
VECTOR_CONTAINER = os.getenv("VECTOR_CONTAINER", "vector-indices")
VECTOR_INDEX_PATH = os.getenv("VECTOR_INDEX_PATH", "faiss_index")

embeddings = AzureOpenAIEmbeddings(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    azure_deployment=EMBEDDING_DEPLOYMENT,
)

llm = AzureChatOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    azure_deployment=CHAT_DEPLOYMENT,
    temperature=0.3,
    max_tokens=800,
)

def load_vectorstore():
    blob_client = BlobServiceClient.from_connection_string(STORAGE_CONN)
    cont_client = blob_client.get_container_client(VECTOR_CONTAINER)
    index_blob = cont_client.download_blob(f"{VECTOR_INDEX_PATH}.faiss")
    docstore_blob = cont_client.download_blob(f"{VECTOR_INDEX_PATH}.pkl")

    index_data = index_blob.readall()
    docstore_data = docstore_blob.readall()

    docstore = InMemoryDocstore(pickle.loads(docstore_data))

    return FAISS(
        embedding_function=embeddings.embed_query,
        index=index_data,
        docstore=docstore,
        index_to_docstore_id={},
    )

class GraphState(TypedDict):
    query: str
    chat_history: List[BaseMessage]
    context: List[str]
    response: str

def retrieval_node(state: GraphState):
    vectorstore = load_vectorstore()
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
    docs = retriever.invoke(state["query"])
    context = [doc.page_content for doc in docs]
    return {"context": context}

def llm_node(state: GraphState):
    context_str = "\n\n".join(state.get("context", [])) if state.get("context") else "No relevant context found."

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a helpful assistant. Answer the user's question using the provided context if it is relevant. "
            "If the context does not help or you don't know the answer, say so honestly.\n\n"
            "Context:\n{context}"
        ),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{query}"),
    ])

    chain = prompt | llm

    response_msg = chain.invoke({
        "context": context_str,
        "chat_history": state["chat_history"],
        "query": state["query"],
    })

    return {"response": response_msg.content}

workflow = StateGraph(GraphState)
workflow.add_node("retrieve", retrieval_node)
workflow.add_node("generate", llm_node)
workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", END)

rag_chain = workflow.compile()