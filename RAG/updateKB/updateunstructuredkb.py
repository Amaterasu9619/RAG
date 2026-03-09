import argparse
import os
import pickle
import sys
import faiss 
import io  # Added for potential BytesIO usage, but using deserialize_index directly

from azure.storage.blob import BlobServiceClient
from langchain_community.document_loaders import UnstructuredWordDocumentLoader
# from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_community.document_loaders import PyPDFLoader

# Remove this line:
# from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore

STORAGE_CONN = os.getenv("AZURE_STORAGE_CONNECTION")
VECTOR_CONTAINER = os.getenv("VECTOR_CONTAINER", "vector-indices")
VECTOR_INDEX_PATH = os.getenv("VECTOR_INDEX_PATH", "faiss_index")

# Fixed dimension for all-MiniLM-L6-v2
EMBEDDING_DIM = 384

# Embeddings model
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# def load_existing_vectorstore():
#     """Load existing FAISS index from Azure Blob or create empty one"""
#     if not STORAGE_CONN:
#         print("AZURE_STORAGE_CONNECTION not set - starting with empty in-memory vectorstore")
#         index = faiss.IndexFlatL2(EMBEDDING_DIM)
#         return FAISS(
#             embedding_function=embeddings.embed_query,
#             index=index,
#             docstore=InMemoryDocstore({}),
#             index_to_docstore_id={},
#         )

#     try:
#         blob_client = BlobServiceClient.from_connection_string(STORAGE_CONN)
#         cont_client = blob_client.get_container_client(VECTOR_CONTAINER)

#         # Download all three components
#         index_blob = cont_client.download_blob(f"{VECTOR_INDEX_PATH}.faiss")
#         docstore_blob = cont_client.download_blob(f"{VECTOR_INDEX_PATH}.docstore.pkl")
#         idmap_blob = cont_client.download_blob(f"{VECTOR_INDEX_PATH}.idmap.pkl")

#         index_data = index_blob.readall()
#         docstore_data = docstore_blob.readall()
#         idmap_data = idmap_blob.readall()

#         # Deserialize properly
#         index = faiss.deserialize_index(index_data)
#         docstore = InMemoryDocstore(pickle.loads(docstore_data))
#         index_to_docstore_id = pickle.loads(idmap_data)

#         print("Successfully loaded existing FAISS index from Azure Blob")
#         return FAISS(
#             embedding_function=embeddings.embed_query,
#             index=index,
#             docstore=docstore,
#             index_to_docstore_id=index_to_docstore_id,
#         )
#     except Exception as e:
#         print(f"Could not load existing index (starting fresh): {e}")
#         print("Creating empty in-memory vectorstore")
#         index = faiss.IndexFlatL2(EMBEDDING_DIM)
#         return FAISS(
#             embedding_function=embeddings.embed_query,
#             index=index,
#             docstore=InMemoryDocstore({}),
#             index_to_docstore_id={},
#         )

def load_existing_vectorstore():
    """Load existing FAISS index: Prefer Azure Blob → Local folder → Create new empty"""
    LOCAL_FOLDER = "./local_faiss_index"
    
    # Always try Azure first if connection available
    if STORAGE_CONN:
        try:
            blob_client = BlobServiceClient.from_connection_string(STORAGE_CONN)
            cont_client = blob_client.get_container_client(VECTOR_CONTAINER)

            # Download all three components (new format)
            index_blob = cont_client.download_blob(f"{VECTOR_INDEX_PATH}.faiss")
            docstore_blob = cont_client.download_blob(f"{VECTOR_INDEX_PATH}.docstore.pkl")
            idmap_blob = cont_client.download_blob(f"{VECTOR_INDEX_PATH}.idmap.pkl")

            index_data = index_blob.readall()
            docstore_data = docstore_blob.readall()
            idmap_data = idmap_blob.readall()

            # Deserialize properly
            index = faiss.deserialize_index(index_data)
            docstore = InMemoryDocstore(pickle.loads(docstore_data))
            index_to_docstore_id = pickle.loads(idmap_data)

            print(f"Successfully loaded existing FAISS index from Azure Blob (ntotal before add: {index.ntotal})")
            return FAISS(
                embedding=embeddings,  # Correct param
                index=index,
                docstore=docstore,
                index_to_docstore_id=index_to_docstore_id,
            )
        except Exception as e:
            print(f"Could not load from Azure Blob (trying local): {e}")

    # If Azure failed or no conn, try local load
    if os.path.exists(LOCAL_FOLDER):
        try:
            vectorstore = FAISS.load_local(
                LOCAL_FOLDER, 
                embeddings, 
                allow_dangerous_deserialization=True  # Required for pickle unserialization
            )
            print(f"Successfully loaded existing FAISS index from local folder '{LOCAL_FOLDER}' (ntotal before add: {vectorstore.index.ntotal})")
            return vectorstore
        except Exception as e:
            print(f"Could not load from local folder (starting fresh): {e}")
    else:
        print(f"Local folder '{LOCAL_FOLDER}' not found (will create new if needed)")

    # Fallback: Create empty in-memory vectorstore
    print("Creating empty in-memory vectorstore")
    index = faiss.IndexFlatL2(EMBEDDING_DIM)
    return FAISS(
        embedding_function=embeddings.embed_query,  
        index=index,
        docstore=InMemoryDocstore({}),
        index_to_docstore_id={},
    )

def save_vectorstore(vectorstore):
    """Save FAISS index to Azure Blob (or locally if no connection)"""
    if not STORAGE_CONN:
        local_folder = "./local_faiss_index"
        os.makedirs(local_folder, exist_ok=True)
        vectorstore.save_local(local_folder)
        print(f"Saved FAISS index locally to {local_folder}")
        return

    try:
        blob_client = BlobServiceClient.from_connection_string(STORAGE_CONN)
        cont_client = blob_client.get_container_client(VECTOR_CONTAINER)

        # Serialize all components
        index_bytes = vectorstore.index.tobytes()
        docstore_bytes = pickle.dumps(vectorstore.docstore._dict)
        idmap_bytes = pickle.dumps(vectorstore.index_to_docstore_id)

        # Upload all three
        cont_client.upload_blob(f"{VECTOR_INDEX_PATH}.faiss", index_bytes, overwrite=True)
        cont_client.upload_blob(f"{VECTOR_INDEX_PATH}.docstore.pkl", docstore_bytes, overwrite=True)
        cont_client.upload_blob(f"{VECTOR_INDEX_PATH}.idmap.pkl", idmap_bytes, overwrite=True)

        print("Successfully uploaded updated FAISS index to Azure Blob")
    except Exception as e:
        print(f"Failed to upload to Azure Blob: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Update knowledge base: Load a .doc/.docx file, vectorize, and merge into FAISS index in Azure Blob"
    )
    parser.add_argument("file_path", help="Path to the .doc or .docx file")
    args = parser.parse_args()

    file_path = args.file_path
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        sys.exit(1)

    if not file_path.lower().endswith(('.doc', '.docx','.pdf','.PDF')):
        print("Only .doc, .docx, .pdf, and .PDF files are supported")
        sys.exit(1)

    print(f"Loading document: {file_path}")
    if file_path.lower().endswith(('.doc', '.docx')):
        loader = UnstructuredWordDocumentLoader(file_path)
    elif file_path.lower().endswith(('.pdf', '.PDF')):
        # loader = UnstructuredPDFLoader(file_path)
        loader = PyPDFLoader(file_path)
    docs = loader.load()

    print(f"Loaded {len(docs)} document(s). Splitting into chunks...")
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = splitter.split_documents(docs)
    print(f"Created {len(splits)} chunks")

    print("Loading existing vectorstore (or creating new)...")
    vectorstore = load_existing_vectorstore()

    print("Adding new chunks to vectorstore...")
    vectorstore.add_documents(splits)
    print(f"Vectorstore now has {vectorstore.index.ntotal} vectors")

    print("Saving updated vectorstore...")
    save_vectorstore(vectorstore)

    print("Knowledge base update complete!")

if __name__ == "__main__":
    main()