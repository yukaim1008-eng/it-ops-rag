import streamlit as st
st.set_page_config(page_title="Chat Test")
st.title("Chat Alignment Test")

if "msgs" not in st.session_state:
    st.session_state.msgs = []

for m in st.session_state.msgs:
    with st.chat_message(m["role"]):
        st.write(m["text"])

if p := st.chat_input("Say something..."):
    with st.chat_message("user"):
        st.write(p)
    st.session_state.msgs.append({"role": "user", "text": p})
    
    with st.chat_message("assistant"):
        st.write(f"Echo: {p}")
    st.session_state.msgs.append({"role": "assistant", "text": f"Echo: {p}"})
