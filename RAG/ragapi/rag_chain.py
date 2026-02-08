from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.docstore.in_memory import InMemoryDocstore
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import pickle
import operator
from azure.storage.blob import BlobServiceClient

class State(TypedDict):
    query: str
    context: list
    response: str
    memory: str  # Serialized chat history

def load_vectorstore(blob_conn_str, container, index_path):
    blob_client = BlobServiceClient.from_connection_string(blob_conn_str)
    cont_client = blob_client.get_container_client(container)
    index_blob = cont_client.download_blob(f"{index_path}.faiss")
    docstore_blob = cont_client.download_blob(f"{index_path}.pkl")
    embeddings = AzureOpenAIEmbeddings(...)  # From config/env
    return FAISS(
        embeddings.embed_query,
        index=index_blob.readall(),
        docstore=InMemoryDocstore(pickle.loads(docstore_blob.readall())),
        index_to_docstore_id={},
    )

def retrieval_node(state):
    vectorstore = load_vectorstore(...)  # Load on-demand
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
    context = retriever.get_relevant_documents(state["query"])
    return {"context": [doc.page_content for doc in context]}

def llm_node(state):
    llm = AzureChatOpenAI(azure_endpoint=..., api_key=..., model="gpt-35-turbo")
    template = """Context: {context}\n\nQuestion: {query}\nAnswer:"""
    prompt = PromptTemplate(input_variables=["context", "query"], template=template)
    qa_chain = RetrievalQA.from_chain_type(llm, retriever=None, chain_type_kwargs={"prompt": prompt})
    # Use memory_handler.get_memory(state["session_id"]) for history
    response = qa_chain.run({"query": state["query"], "context": "\n".join(state["context"])})
    return {"response": response}

# LangGraph workflow
workflow = StateGraph(State)
workflow.add_node("retrieve", retrieval_node)
workflow.add_node("generate", llm_node)
workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", END)
rag_chain = workflow.compile()