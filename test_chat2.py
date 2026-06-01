import streamlit as st
st.set_page_config(page_title="Test", layout="wide")

st.title("Left/Right Test - 请发一条消息")

if "msgs" not in st.session_state:
    st.session_state.msgs = []

for m in st.session_state.msgs:
    with st.chat_message(m["role"]):
        st.write(m["text"])

if p := st.chat_input("随便输入..."):
    with st.chat_message("user"):
        st.write(p)
    st.session_state.msgs.append({"role": "user", "text": p})
    with st.chat_message("assistant"):
        st.write(f"收到: {p}")
    st.session_state.msgs.append({"role": "assistant", "text": f"收到: {p}"})
