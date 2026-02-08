import yaml
from langchain_openai import AzureOpenAIEmbeddings
from langchain_community.document_loaders import SharePointLoader  # Custom if needed
from atlassian import Confluence
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.docstore.in_memory import InMemoryDocstore
from azure.storage.blob import BlobServiceClient
import pickle
import os

def load_config():
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    # Override with env vars if needed
    return config

def ingest_sharepoint(config):
    loader = SharePointLoader(
        site=config['sources']['sharepoint']['site_url'],
        client_id=config['sources']['sharepoint']['client_id'],
        client_secret=config['sources']['sharepoint']['client_secret']
    )
    docs = loader.load()
    return docs

def ingest_confluence(config):
    confluence = Confluence(url=config['sources']['confluence']['base_url'],
                            username=config['sources']['confluence']['username'],
                            password=config['sources']['confluence']['api_token'])
    pages = confluence.get_all_pages_from_space(config['sources']['confluence']['space_key'], expand='body.storage')
    docs = [confluence.get_page_by_id(page['id'], expand='body.storage')['body']['storage']['value'] for page in pages]
    from langchain.docstore.document import Document
    return [Document(page_content=doc, metadata={'source': 'confluence'}) for doc in docs]

def update_vector_db(docs, config):
    embeddings = AzureOpenAIEmbeddings(
        azure_endpoint=config['azure']['openai']['endpoint'],
        api_key=config['azure']['openai']['api_key'],
        model=config['azure']['openai']['model']
    )
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = splitter.split_documents(docs)
    
    # Load existing FAISS or create new
    blob_client = BlobServiceClient.from_connection_string(config['azure']['blob']['connection_string'])
    container = blob_client.get_container_client(config['azure']['blob']['container'])
    try:
        # Download existing index
        index_blob = container.download_blob(f"{config['azure']['blob']['index_path']}.faiss")
        docstore_blob = container.download_blob(f"{config['azure']['blob']['index_path']}.pkl")
        vectorstore = FAISS.from_embeddings(embeddings, [], index=index_blob.readall(), docstore=InMemoryDocstore(pickle.loads(docstore_blob.readall())))
    except:
        vectorstore = FAISS.from_documents([], embeddings)
    
    # Add new docs
    vectorstore.add_documents(splits)
    
    # Save back
    index_bytes = vectorstore.index.tobytes()
    docstore_bytes = pickle.dumps(vectorstore.docstore)
    container.upload_blob(f"{config['azure']['blob']['index_path']}.faiss", index_bytes, overwrite=True)
    container.upload_blob(f"{config['azure']['blob']['index_path']}.pkl", docstore_bytes, overwrite=True)

def poll_and_update(config):
    all_docs = ingest_sharepoint(config) + ingest_confluence(config)
    update_vector_db(all_docs, config)