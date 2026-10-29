"""Streamlit chat frontend for the Order Support Agent.

Run:
    streamlit run chatbot.py

Requires the FastAPI backend running on port 8000:
    uvicorn order_support_agent:app --port 8000
"""

import streamlit as st
import requests

API_URL = "http://localhost:8000/stream"

st.set_page_config(page_title="Order Support Chat", page_icon="🛒")
st.title("Order Support Chat")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Handle new user input
if prompt := st.chat_input("Ask about your order..."):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Stream assistant response
    with st.chat_message("assistant"):
        try:
            response = requests.post(
                API_URL,
                json={"prompt": prompt},
                stream=True,
                timeout=120,
            )
            response.raise_for_status()

            def stream_chunks():
                for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk:
                        yield chunk

            full_response = st.write_stream(stream_chunks())
        except requests.ConnectionError:
            full_response = "Could not connect to the backend. Make sure the FastAPI server is running on port 8000."
            st.error(full_response)
        except requests.HTTPError as e:
            full_response = f"Backend error: {e.response.status_code}"
            st.error(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})
