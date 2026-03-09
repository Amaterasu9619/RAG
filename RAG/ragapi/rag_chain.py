# AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
# AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
# EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
# CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-35-turbo")
# STORAGE_CONN = os.getenv("AZURE_STORAGE_CONNECTION")
# VECTOR_CONTAINER = os.getenv("VECTOR_CONTAINER", "vector-indices")
# VECTOR_INDEX_PATH = os.getenv("VECTOR_INDEX_PATH", "faiss_index")

# embeddings = AzureOpenAIEmbeddings(
#     azure_endpoint=AZURE_OPENAI_ENDPOINT,
#     api_key=AZURE_OPENAI_KEY,
#     azure_deployment=EMBEDDING_DEPLOYMENT,
# )

# llm = AzureChatOpenAI(
#     azure_endpoint=AZURE_OPENAI_ENDPOINT,
#     api_key=AZURE_OPENAI_KEY,
#     azure_deployment=CHAT_DEPLOYMENT,
#     temperature=0.3,
#     max_tokens=800,
# )

import os
import pickle
from typing import List
import faiss
from azure.storage.blob import BlobServiceClient
# from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI  # COMMENTED: Azure parts
from langchain_huggingface import HuggingFaceEmbeddings 
from langchain_groq import ChatGroq 
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from typing import TypedDict


# GROQ_API_KEY = os.getenv("GROQ_API_KEY")  
STORAGE_CONN = os.getenv("AZURE_STORAGE_CONNECTION")
VECTOR_CONTAINER = os.getenv("VECTOR_CONTAINER", "vector-indices")
VECTOR_INDEX_PATH = os.getenv("VECTOR_INDEX_PATH", "faiss_index")

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")  # Free local model

llm = ChatGroq(
    groq_api_key=GROQ_API_KEY,
    model_name="llama-3.3-70b-versatile", 
    temperature=0.3,
    max_tokens=800,
)

def load_vectorstore():
    local_folder = "../updateKB/local_faiss_index"
    
    if os.path.exists(local_folder):
        print("Loading FAISS index from local folder")
        try:
            return FAISS.load_local(local_folder, embeddings, allow_dangerous_deserialization=True)
        except Exception as e:
            print(f"Local FAISS load failed: {e}. Falling back to empty in-memory vectorstore.")
            index = faiss.IndexFlatL2(384)  
            return FAISS(
                embedding_function=embeddings.embed_query,
                index=index,
                docstore=InMemoryDocstore({}),
                index_to_docstore_id={},
            )
    
    if not STORAGE_CONN:
        print("No Azure storage - using empty in-memory vectorstore")
        index = faiss.IndexFlatL2(384)
        return FAISS(
            embedding_function=embeddings.embed_query,
            index=index,
            docstore=InMemoryDocstore({}),
            index_to_docstore_id={},
        )
    
    try:
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
    except Exception as e:
        print(f"Azure load failed: {e}. Falling back to local or empty.")
        if os.path.exists(local_folder):
            try:
                return FAISS.load_local(local_folder, embeddings, allow_dangerous_deserialization=True)
            except Exception as le:
                print(f"Local fallback also failed: {le}. Using empty in-memory vectorstore.")
        index = faiss.IndexFlatL2(384)
        return FAISS(
            embedding_function=embeddings.embed_query,
            index=index,
            docstore=InMemoryDocstore({}),
            index_to_docstore_id={},
        )

# def load_vectorstore():
#     local_folder = "../updateKB/local_faiss_index"
    
#     # Prefer local if exists (for testing without Azure)
#     if os.path.exists(local_folder):
#         print("Loading FAISS index from local folder")
#         return FAISS.load_local(local_folder, embeddings, allow_dangerous_deserialization=True)
    
#     if not STORAGE_CONN:
#         print("No Azure storage - using empty in-memory vectorstore")
#         index = faiss.IndexFlatL2(384)
#         return FAISS(
#             embedding_function=embeddings.embed_query,
#             index=index,
#             docstore=InMemoryDocstore({}),
#             index_to_docstore_id={},
#         )
    
#     try:
#         blob_client = BlobServiceClient.from_connection_string(STORAGE_CONN)
#         cont_client = blob_client.get_container_client(VECTOR_CONTAINER)
#         index_blob = cont_client.download_blob(f"{VECTOR_INDEX_PATH}.faiss")
#         docstore_blob = cont_client.download_blob(f"{VECTOR_INDEX_PATH}.pkl")

#         index_data = index_blob.readall()
#         docstore_data = docstore_blob.readall()

#         docstore = InMemoryDocstore(pickle.loads(docstore_data))

#         return FAISS(
#             embedding_function=embeddings.embed_query,
#             index=index_data,
#             docstore=docstore,
#             index_to_docstore_id={},
#         )
#     except Exception as e:
#         print(f"Azure load failed: {e}. Falling back to local or empty.")
#         if os.path.exists(local_folder):
#             return FAISS.load_local(local_folder, embeddings, allow_dangerous_deserialization=True)
#         index = faiss.IndexFlatL2(384)
#         return FAISS(
#             embedding_function=embeddings.embed_query,
#             index=index,
#             docstore=InMemoryDocstore({}),
#             index_to_docstore_id={},
#         )



# def load_vectorstore():
#     if not STORAGE_CONN:
#         print("No Azure storage connection - using empty in-memory vectorstore for testing")
#         return FAISS.from_texts([], embeddings)
    
#     try:
#         blob_client = BlobServiceClient.from_connection_string(STORAGE_CONN)
#         cont_client = blob_client.get_container_client(VECTOR_CONTAINER)
#         index_blob = cont_client.download_blob(f"{VECTOR_INDEX_PATH}.faiss")
#         docstore_blob = cont_client.download_blob(f"{VECTOR_INDEX_PATH}.pkl")

#         index_data = index_blob.readall()
#         docstore_data = docstore_blob.readall()

#         docstore = InMemoryDocstore(pickle.loads(docstore_data))

#         return FAISS(
#             embedding_function=embeddings.embed_query,
#             index=index_data,
#             docstore=docstore,
#             index_to_docstore_id={},
#         )
#     except Exception as e:
#         print(f"Failed to load FAISS index (normal for first test): {e}")
#         print("Creating empty in-memory vectorstore")
#         return FAISS.from_texts([], embeddings)

class GraphState(TypedDict):
    query: str
    chat_history: List[BaseMessage]
    context: List[str]
    response: str

# def retrieval_node(state: GraphState):
#     classify_prompt = ChatPromptTemplate.from_template(
#         "Classify the following user query as either 'generic' (broad, exploratory question needing more context) "
#         "or 'specific' (precise, targeted question needing focused info). "
#         "Respond with only 'generic' or 'specific' (no explanation).\n\nQuery: {query}"
#     )
#     classify_chain = classify_prompt | llm
#     classification_result = classify_chain.invoke({"query": state["query"]})
#     query_type = classification_result.content.strip().lower()
    
    
#     k = 40 if query_type == "generic" else 5 
    
#     print(f"Query classified as '{query_type}', retrieving top {k} chunks.")
    
#     vectorstore = load_vectorstore()
#     retriever = vectorstore.as_retriever(search_kwargs={"k": k})
#     docs = retriever.invoke(state["query"])
#     context = [doc.page_content for doc in docs]
#     return {"context": context}

def retrieval_node(state: GraphState):
    classify_prompt = ChatPromptTemplate.from_template(
        "Classify the following user query as either 'generic' (broad, exploratory question needing more context) "
        "or 'specific' (precise, targeted question needing focused info). "
        "Respond with only 'generic' or 'specific' (no explanation).\n\nQuery: {query}"
    )
    classify_chain = classify_prompt | llm
    classification_result = classify_chain.invoke({"query": state["query"]})
    query_type = classification_result.content.strip().lower()
    
    k = 40 if query_type == "generic" else 5 
    
    print(f"Query classified as '{query_type}', retrieving top {k} chunks with MMR.")
    
    vectorstore = load_vectorstore()
    
    # Use MMR instead of similarity search
    docs = vectorstore.max_marginal_relevance_search(
        state["query"],
        k=k,
        fetch_k=k * 3,  # Fetch more candidates for diversity
        lambda_mult=0.5  # Balance between relevance (1.0) and diversity (0.0)
    )
    
    context = [doc.page_content for doc in docs]
    return {"context": context}

def llm_node(state: GraphState):
    context_str = "\n\n".join(state.get("context", [])) if state.get("context") else "No relevant context found."

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a helpful website navigation assistant. Answer the user's question using the provided context if it is relevant. "
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