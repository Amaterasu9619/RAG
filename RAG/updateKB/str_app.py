# streamlit_app.py (Improved UX: Always show chat input + welcome message for empty/new chats)
import streamlit as st
import requests
import uuid
import time
import hashlib
# Config
API_BASE = "http://localhost:8000"
SESSION_ID = "user_local_test"

st.set_page_config(page_title="RAG Companion", layout="wide")
st.title("RAG companion with KB")

# Initialize session state
if "current_conv_id" not in st.session_state:
    main_conv_id = str(uuid.uuid4())[:8]
    st.session_state.current_conv_id = main_conv_id
if "chat_histories" not in st.session_state:
    st.session_state.chat_histories = {st.session_state.current_conv_id: []}
if "conversations" not in st.session_state:
    st.session_state.conversations = [{"conversation_id": st.session_state.current_conv_id, "title": "Main Conversation", "last_updated": time.time()}]

def get_client_ip() -> str:
    """Get the real client IP, preferring X-Forwarded-For from ngrok."""
    headers = st.context.headers
    # ngrok sets X-Forwarded-For: <real-client-ip>[, <other-proxies>]
    xff = headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    # Fallback: st.context.ip_address (works for direct/local connections)
    if hasattr(st.context, "ip_address") and st.context.ip_address:
        return st.context.ip_address
    return "unknown"

def fetch_conversations():
    try:
        ip = get_client_ip()
        user_hash = hashlib.md5(ip.encode()).hexdigest()
        session_id = f"{user_hash}:{SESSION_ID}"
        resp = requests.get(f"{API_BASE}/conversations/{session_id}")
        if resp.status_code == 200:
            convs = resp.json()
            # Keep local new chats + sync server ones
            existing_ids = {c["conversation_id"] for c in st.session_state.conversations}
            for conv in convs:
                if conv["conversation_id"] not in existing_ids:
                    st.session_state.conversations.append(conv)
                    st.session_state.chat_histories[conv["conversation_id"]] = []
            # Update titles/timestamps
            server_map = {c["conversation_id"]: c for c in convs}
            for local_conv in st.session_state.conversations:
                if local_conv["conversation_id"] in server_map:
                    server_conv = server_map[local_conv["conversation_id"]]
                    local_conv["title"] = server_conv["title"]
                    local_conv["last_updated"] = server_conv["last_updated"]
            st.session_state.conversations.sort(key=lambda x: x["last_updated"], reverse=True)
    except Exception as e:
        st.sidebar.error(f"API issue: {e}")

def send_query(query, conv_id):
    print(conv_id)
    ip = get_client_ip()
    user_hash = hashlib.md5(ip.encode()).hexdigest()
    session_id = f"{user_hash}:{SESSION_ID}"
    payload = {
        "query": query,
        "session_id": session_id,
        "conversation_id": conv_id
    }

    try:
        resp = requests.post(f"{API_BASE}/query", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            return data["answer"], data.get("sources", [])
        else:
            return f"API Error: {resp.text}", []
    except Exception as e:
        return f"Connection error: {e}", []

# Sidebar
with st.sidebar:
    st.header("Conversations")
    
    col1, col2 = st.columns([2,1])
    with col1:
        if st.button("🆕 New Chat", use_container_width=True):
            new_conv_id = str(uuid.uuid4())[:8]
            st.session_state.current_conv_id = new_conv_id
            st.session_state.chat_histories[new_conv_id] = []
            # Immediate placeholder
            st.session_state.conversations.insert(0, {
                "conversation_id": new_conv_id,
                "title": "New Conversation",
                "last_updated": time.time()
            })
            st.rerun()
    with col2:
        if st.button("🔄", help="Refresh List"):
            fetch_conversations()
            st.rerun()

    fetch_conversations()

    st.markdown("**Your Chats:**")
    for conv in st.session_state.conversations:
        conv_id = conv["conversation_id"]
        title = conv["title"]
        is_active = (st.session_state.current_conv_id == conv_id)
        if st.button(
            f"{'➤ ' if is_active else ''}{title}",
            key=f"btn_{conv_id}",
            use_container_width=True,
            disabled=is_active
        ):
            st.session_state.current_conv_id = conv_id
            if conv_id not in st.session_state.chat_histories:
                st.session_state.chat_histories[conv_id] = []
            st.rerun()

# Main chat area
current_conv_id = st.session_state.current_conv_id
active_title = next((c["title"] for c in st.session_state.conversations if c["conversation_id"] == current_conv_id), "Conversation")
st.subheader(f"Thread: {current_conv_id} – {active_title}")

# Chat container
chat_container = st.container()

with chat_container:
    history = st.session_state.chat_histories.get(current_conv_id, [])
    
    if not history:
        st.info("👋 This is a new conversation. Type your question below to start chatting!")
    
    for msg in history:
        if msg["role"] == "user":
            st.chat_message("user").write(msg["content"])
        else:
            with st.chat_message("assistant"):
                st.write(msg["content"])
                if msg.get("sources"):
                    with st.expander("View Sources"):
                        for i, src in enumerate(msg["sources"], 1):
                            st.caption(f"Source {i}: {src[:500]}{'...' if len(src) > 500 else ''}")

# Always show input at bottom
prompt = st.chat_input("Type your question here... (hit Enter to send)")

if prompt:
    # Add user message immediately
    with chat_container:
        st.chat_message("user").write(prompt)

    # Call API
    with chat_container:
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer, sources = send_query(prompt, current_conv_id)
            st.write(answer)
            if sources:
                with st.expander("View Sources"):
                    for i, src in enumerate(sources, 1):
                        st.caption(f"Source {i}: {src[:500]}{'...' if len(src) > 500 else ''}")

    # Update history
    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": answer, "sources": sources})
    st.session_state.chat_histories[current_conv_id] = history
    
    # Update placeholder timestamp
    for conv in st.session_state.conversations:
        if conv["conversation_id"] == current_conv_id:
            conv["last_updated"] = time.time()
            break
    
    st.rerun()

st.caption("💡 Tip: Click 'New Chat' → type a question → it saves automatically. Use 'Refresh List' to sync titles.")