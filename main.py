"""
IT-Ops-RAG — Clean Light Dashboard, Two-Column Layout
"""
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import subprocess, json, atexit, hashlib, time, re, base64
import markdown as md_lib
import concurrent.futures
import streamlit as st

st.set_page_config(page_title="IT-Ops-RAG", page_icon="◈", layout="wide", initial_sidebar_state="collapsed")

# ═══════════════════ Design Tokens ═══════════════════
BG       = "#FFFFFF"
SURF     = "#F8F9FA"
ELEV     = "#F3F4F6"
BORDER   = "#E1E4E8"
TEXT     = "#111827"
TEXT_S   = "#6B7280"
TEXT_T   = "#9CA3AF"
BLUE     = "#4F46E5"
BLUE_S   = "#EEF2FF"
GREEN    = "#059669"
GREEN_S  = "#ECFDF5"
AMBER    = "#D97706"
RED      = "#DC2626"
SHADOW   = "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)"

# ═══════════════════ CSS ═══════════════════

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

* { font-family: 'Inter', sans-serif; }
code, pre, .mono { font-family: 'JetBrains Mono', monospace; }

header[data-testid="stHeader"] { display: none !important; }
footer[data-testid="stFooter"] { display: none !important; }
.stApp { background: __BG__; }
::selection { background: rgba(79,70,229,0.15); }

input, textarea, select {
    background: __BG__ !important; border: 1px solid __BORDER__ !important;
    border-radius: 8px !important; color: __TEXT__ !important; font-size: 0.9rem !important;
}
input:focus, textarea:focus, select:focus {
    border-color: __BLUE__ !important; box-shadow: 0 0 0 3px rgba(79,70,229,0.1) !important;
}

.stButton > button {
    border-radius: 8px; font-weight: 500; font-size: 0.85rem;
    transition: all 0.12s ease; border: 1px solid __BORDER__;
    background: __BG__; color: __TEXT__;
}
.stButton > button:hover { background: __ELEV__ !important; border-color: __BLUE__ !important; }
.stButton > button[kind="primary"] { background: __BLUE__ !important; border-color: __BLUE__ !important; color: #fff !important; }

details[data-testid="stExpander"] { border: 1px solid __BORDER__; border-radius: 8px; background: __BG__; margin-top: 6px; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 10px; border: 1px solid __BORDER__; padding: 1rem; background: __BG__; }

.stTabs [data-baseweb="tab-list"] { gap: 0; border-bottom: 1px solid __BORDER__; }
.stTabs [data-baseweb="tab"] { color: __TEXT_S__; padding: 0.4rem 0.8rem; border-radius: 8px 8px 0 0; font-weight: 500; font-size: 0.85rem; }
.stTabs [aria-selected="true"] { color: __BLUE__ !important; }

.stSpinner > div { border-color: __BLUE__ transparent transparent transparent !important; }
.stMetric { color: __TEXT__; }
.stMetric [data-testid="stMetricValue"] { color: __TEXT__; font-weight: 600; }
div[role="radiogroup"] label { color: __TEXT_S__; }
div[role="radiogroup"] label:hover { color: __TEXT__; }

/* Bubble content */
.bubble p { margin: 0.25rem 0; }
.bubble p:first-child { margin-top: 0; }
.bubble p:last-child { margin-bottom: 0; }
.bubble ul, .bubble ol { margin: 0.25rem 0; padding-left: 1.25rem; }
.bubble li { margin: 0.06rem 0; }
.bubble code {
    background: __ELEV__; padding: 0.1rem 0.35rem;
    border-radius: 4px; font-size: 0.83rem; font-family: 'JetBrains Mono', monospace; color: __BLUE__;
}
.bubble pre {
    background: #F1F5F9; color: #1E293B; padding: 0.7rem 0.9rem; border-radius: 8px;
    overflow-x: auto; margin: 0.4rem 0; font-size: 0.79rem; line-height: 1.5; border: 1px solid #E2E8F0;
}
.bubble pre code { background: none; padding: 0; color: inherit; font-size: inherit; }
.bubble table { border-collapse: collapse; margin: 0.4rem 0; font-size: 0.84rem; width: 100%; }
.bubble th, .bubble td { border: 1px solid __BORDER__; padding: 0.35rem 0.55rem; text-align: left; }
.bubble th { background: __ELEV__; font-weight: 600; color: __TEXT__; }
.bubble td { color: __TEXT_S__; }
.bubble blockquote { border-left: 2px solid __BLUE__; padding-left: 0.7rem; margin: 0.4rem 0; color: __TEXT_S__; }
.bubble a { color: __BLUE__; text-decoration: none; }
.bubble a:hover { text-decoration: underline; }
.bubble h2,.bubble h3,.bubble h4 { margin: 0.4rem 0 0.2rem; font-weight: 600; color: __TEXT__; }
.bubble h2 { font-size: 1rem; }
.bubble h3 { font-size: 0.92rem; }
.bubble strong { color: __TEXT__; font-weight: 600; }

h1 { font-size: 1.1rem !important; font-weight: 600 !important; color: __TEXT__ !important; }
h3 { font-size: 0.95rem !important; font-weight: 600 !important; color: __TEXT__ !important; }

[data-testid="stChatMessage"] { display: none; }
.stDeployButton { display: none; }
.stAppToolbar { display: none; }
#MainMenu { display: none; }
section[data-testid="stSidebar"] { display: none; }

::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: __BORDER__; border-radius: 3px; }

/* Chips */
.chip {
    display:inline-block;padding:2px 10px;border-radius:14px;font-size:0.73rem;font-weight:500;
    border:1px solid __BLUE__;color:__BLUE__;background:__BLUE_S__;margin:1px 3px;
}
.chip-green { border-color:__GREEN__;color:__GREEN__;background:__GREEN_S__; }

/* Conversation list scroll */
.conv-scroll { max-height: calc(100vh - 180px); overflow-y: auto; }
</style>
"""

CSS = CSS.replace("__BG__",BG).replace("__ELEV__",ELEV).replace("__BORDER__",BORDER)
CSS = CSS.replace("__TEXT__",TEXT).replace("__TEXT_S__",TEXT_S).replace("__TEXT_T__",TEXT_T)
CSS = CSS.replace("__BLUE__",BLUE).replace("__BLUE_S__",BLUE_S)
CSS = CSS.replace("__GREEN__",GREEN).replace("__GREEN_S__",GREEN_S)

def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ═══════════════════ Icons ═══════════════════

def icon(name, size=16):
    s=str(size)
    sw=' stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
    s2='width="'+s+'" height="'+s+'"'
    I={
        "bot":'<svg '+s2+' viewBox="0 0 24 24" fill="none" stroke="'+BLUE+'"'+sw+'><rect x="3" y="8" width="18" height="13" rx="2"/><path d="M8 3h8l1 5H7z"/><circle cx="9" cy="14" r="1.5" fill="'+BLUE+'"/><circle cx="15" cy="14" r="1.5" fill="'+BLUE+'"/></svg>',
        "cpu":'<svg '+s2+' viewBox="0 0 24 24" fill="none" stroke="'+BLUE+'"'+sw+'><rect x="3" y="3" width="18" height="18" rx="2"/><rect x="8" y="8" width="8" height="8"/><line x1="8" y1="1" x2="8" y2="3"/><line x1="16" y1="1" x2="16" y2="3"/><line x1="8" y1="21" x2="8" y2="23"/><line x1="16" y1="21" x2="16" y2="23"/><line x1="21" y1="8" x2="23" y2="8"/><line x1="21" y1="16" x2="23" y2="16"/><line x1="1" y1="8" x2="3" y2="8"/><line x1="1" y1="16" x2="3" y2="16"/></svg>',
        "bolt":'<svg '+s2+' viewBox="0 0 24 24" fill="none" stroke="'+GREEN+'"'+sw+'><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
        "doc":'<svg '+s2+' viewBox="0 0 24 24" fill="none" stroke="currentColor"'+sw+'><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    }
    return I.get(name,"")


# ═══════════════════ Avatar ═══════════════════

AVATAR_DIR = os.path.join(os.path.dirname(__file__), "data", "avatars")

def _avatar_html(user, size=32):
    img = user.get("avatar_image","")
    if img and os.path.exists(img):
        try:
            with open(img,"rb") as f: b64=base64.b64encode(f.read()).decode()
            return '<img src="data:image/png;base64,'+b64+'" style="width:'+str(size)+'px;height:'+str(size)+'px;border-radius:8px;object-fit:cover;flex-shrink:0;" />'
        except: pass
    e=user.get("avatar_emoji","") or user["display_name"][0]
    c=user.get("avatar_color","#4F46E5")
    return '<div style="width:'+str(size)+'px;height:'+str(size)+'px;border-radius:8px;background:'+c+';display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:'+str(int(size*0.45))+'px;flex-shrink:0;">'+e+'</div>'


# ═══════════════════ Chat Cards ═══════════════════

def user_card(content, user):
    html = md_lib.markdown(content, extensions=["fenced_code","tables"])
    av=_avatar_html(user,30)
    st.markdown(
        '<div style="display:flex;justify-content:flex-end;margin:18px 0;">'
        '<div style="max-width:70%;background:#fff;border:1px solid '+BORDER+';border-radius:12px;'
        'padding:12px 16px;box-shadow:'+SHADOW+';border-right:3px solid '+BLUE+';">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;justify-content:flex-end;">'
        '<span style="font-size:0.78rem;font-weight:500;color:'+TEXT+';">'+user["display_name"]+'</span>'+av
        +'</div><div class="bubble" style="color:'+TEXT+';font-size:0.9rem;line-height:1.6;">'+html+'</div></div></div>',
        unsafe_allow_html=True)


def _cite_block(citations):
    if not citations: return ""
    items=""
    for i,c in enumerate(citations):
        items+='<div style="margin-bottom:4px;padding-bottom:4px;border-bottom:1px solid '+BORDER+';">'
        items+='<div style="font-weight:600;font-size:0.76rem;color:'+TEXT+';">'+str(i+1)+'. '+c["source_file"]+' · 第'+str(c["chunk_index"])+'段</div>'
        items+='<div style="font-size:0.74rem;color:'+TEXT_S+';margin-top:2px;">'+c["text"][:150]+'</div></div>'
    return ('<details style="margin-top:8px;font-size:0.82rem;"><summary style="cursor:pointer;color:'+BLUE+';">'+icon("doc",13)+' 引用（'+str(len(citations))+' 条）</summary><div style="margin-top:6px;">'+items+'</div></details>')


def assistant_card(content, citations=None):
    html = md_lib.markdown(content, extensions=["fenced_code","tables"])
    st.markdown(
        '<div style="display:flex;justify-content:flex-start;margin:18px 0;">'
        '<div style="max-width:70%;background:#fff;border:1px solid '+BORDER+';border-radius:12px;'
        'padding:12px 16px;box-shadow:'+SHADOW+';">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">'
        '<div style="width:26px;height:26px;border-radius:7px;background:'+BLUE_S+';display:flex;align-items:center;justify-content:center;">'+icon("bot",14)+'</div>'
        '<span style="font-weight:600;font-size:0.82rem;color:'+BLUE+';">小智</span>'
        '<span style="font-size:0.72rem;color:'+TEXT_S+';">IT 运维助手</span>'
        +'</div><div class="bubble" style="color:'+TEXT+';font-size:0.9rem;line-height:1.6;">'+html+_cite_block(citations)+'</div></div></div>',
        unsafe_allow_html=True)


# ═══════════════════ Conversation System ═══════════════════

CHAT_BASE = os.path.join(os.path.dirname(__file__),"data","chat_history")

def _cdir(u): d=os.path.join(CHAT_BASE,u); os.makedirs(d,exist_ok=True); return d
def _ipath(u): return os.path.join(_cdir(u),"_index.json")
def load_index(u):
    p=_ipath(u)
    if os.path.exists(p):
        try: return json.load(open(p,"r",encoding="utf-8"))
        except: pass
    return []
def save_index(u,idx): json.dump(idx,open(_ipath(u),"w",encoding="utf-8"),ensure_ascii=False,indent=2)

def repair_index(u):
    """扫描对话目录，补全并刷新索引"""
    idx = load_index(u)
    indexed = {e["id"]: e for e in idx}
    d = _cdir(u)
    for fname in os.listdir(d):
        if fname.endswith(".json") and not fname.startswith("_"):
            cid = fname[:-5]
            msgs = load_conversation(u, cid)
            if not msgs: continue
            title = extract_keywords(msgs)
            if cid in indexed:
                indexed[cid].update(title=title, message_count=len(msgs), has_content=_has_substance(msgs))
            else:
                idx.insert(0, {"id":cid,"title":title,"message_count":len(msgs),
                               "has_content":_has_substance(msgs),"created_at":"","updated_at":""})
    save_index(u, idx)

def create_conversation(u):
    cid=time.strftime("%Y%m%d_%H%M%S")+"_"+str(int(time.time()*1000)%10000).zfill(4)
    json.dump([],open(os.path.join(_cdir(u),cid+".json"),"w",encoding="utf-8"))
    return cid

def load_conversation(u,cid):
    p=os.path.join(_cdir(u),cid+".json")
    if os.path.exists(p):
        try: return json.load(open(p,"r",encoding="utf-8"))
        except: pass
    return []

def save_conversation(u,cid,msgs):
    json.dump(msgs,open(os.path.join(_cdir(u),cid+".json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)

def _has_substance(msgs):
    return len(msgs)>=2 and any(m["role"]=="assistant" and len(m.get("content",""))>80 for m in msgs)

def extract_keywords(msgs):
    """提取对话关键词，过滤代码和 markdown 格式"""
    if not msgs: return "新对话"
    um=[m["content"] for m in msgs if m["role"]=="user"]
    if not um: return "新对话"
    kw=[]
    for m in um[:3]:
        clean = re.sub(r'```.*?```', '', m, flags=re.DOTALL)
        clean = re.sub(r'`[^`]+`', '', clean)
        clean = re.sub(r'[#*>\-|\[\]()]', '', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        clean = re.sub(r'[^\w一-鿿]', '', clean)
        kw.append(clean[:20]+("…" if len(clean)>20 else "") if clean else "…")
    return " · ".join(kw[:3])

def finalize_conversation(u,cid,msgs):
    if not msgs: return
    save_conversation(u,cid,msgs)
    idx=load_index(u)
    for e in idx:
        if e["id"]==cid:
            e.update(title=extract_keywords(msgs),message_count=len(msgs),
                     has_content=_has_substance(msgs),updated_at=time.strftime("%m-%d %H:%M"))
            save_index(u,idx); return
    idx.insert(0,{"id":cid,"title":extract_keywords(msgs),"message_count":len(msgs),
                  "has_content":_has_substance(msgs),"created_at":time.strftime("%m-%d %H:%M"),
                  "updated_at":time.strftime("%m-%d %H:%M")})
    save_index(u,idx)

def delete_conversation(u,cid):
    p=os.path.join(_cdir(u),cid+".json")
    if os.path.exists(p): os.remove(p)
    save_index(u,[e for e in load_index(u) if e["id"]!=cid])


# ═══════════════════ User System ═══════════════════

USERS_FILE = os.path.join(os.path.dirname(__file__),"data","users.json")
DU={
    "admin":{"password_hash":hashlib.sha256("admin123".encode()).hexdigest(),"display_name":"张工","role":"二线专家","department":"基础架构部","avatar_emoji":"ZG","avatar_color":"#4F46E5"},
    "operator":{"password_hash":hashlib.sha256("ops123".encode()).hexdigest(),"display_name":"李运维","role":"一线运维","department":"运维中心","avatar_emoji":"LY","avatar_color":"#059669"},
    "security":{"password_hash":hashlib.sha256("sec123".encode()).hexdigest(),"display_name":"王审计","role":"安全审计员","department":"信息安全部","avatar_emoji":"WS","avatar_color":"#D97706"},
}
RF={"一线运维":None,"二线专家":{"severity":"L2"},"安全审计员":{"system_name":"安全"}}
SYS=["服务器","网络","数据库","应用","安全","监控"]
ROLES=["一线运维","二线专家","安全审计员"]
DEPTS=["运维中心","基础架构部","信息安全部","研发部","测试部","产品部"]
AC=["#4F46E5","#059669","#D97706","#DC2626","#A371F7","#DB61A2","#39D2C0","#F97316","#6366F1","#0891B2","#059669","#7C3AED"]
CN=["靛蓝","绿","琥珀","红","紫","粉","青","橙","靛蓝","深青","翡翠","紫晶"]

def load_users():
    os.makedirs(os.path.dirname(USERS_FILE),exist_ok=True)
    if os.path.exists(USERS_FILE):
        try: return json.load(open(USERS_FILE,"r",encoding="utf-8"))
        except: pass
    save_users(DU.copy()); return DU.copy()
def save_users(u): os.makedirs(os.path.dirname(USERS_FILE),exist_ok=True); json.dump(u,open(USERS_FILE,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
def verify_login(u,p):
    users=load_users(); user=users.get(u)
    if not user or hashlib.sha256(p.encode()).hexdigest()!=user["password_hash"]: return None
    return {"username":u,"display_name":user["display_name"],"role":user["role"],"department":user["department"],"avatar_emoji":user.get("avatar_emoji",""),"avatar_color":user.get("avatar_color","#4F46E5"),"avatar_image":user.get("avatar_image","")}
def register_user(u,p,dn,role,dept):
    users=load_users()
    if not u or len(u.strip())<3: return False,"用户名至少3个字符"
    if u.strip() in users: return False,"用户名已存在"
    if len(p)<4: return False,"密码至少4个字符"
    if not dn or not dn.strip(): return False,"显示名称不能为空"
    users[u.strip()]={"password_hash":hashlib.sha256(p.encode()).hexdigest(),"display_name":dn.strip(),"role":role,"department":dept,"avatar_emoji":dn.strip()[:2],"avatar_color":"#4F46E5"}
    save_users(users); return True,""
def update_user_profile(uname,ups):
    users=load_users()
    if uname not in users: return False
    for f in ["display_name","avatar_emoji","avatar_color","avatar_image","role","department"]:
        if f in ups: users[uname][f]=ups[f]
    if "new_password" in ups: users[uname]["password_hash"]=hashlib.sha256(ups["new_password"].encode()).hexdigest()
    save_users(users); return True


# ═══════════════════ Backend ═══════════════════

@st.cache_resource
def get_backend():
    proc=subprocess.Popen(
        [os.path.join(os.path.dirname(__file__),".venv","Scripts","python.exe"),os.path.join(os.path.dirname(__file__),"backend.py")],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",bufsize=1)
    if proc.stdout.readline().strip()!="READY": st.error("后端启动异常"); proc.kill(); st.stop()
    atexit.register(lambda: proc.kill() if proc.poll() is None else None)
    return proc

def kill_backend():
    try:
        p=get_backend()
        if p.poll() is None: p.kill()
    except: pass
    get_backend.clear()

def query_backend(proc,query,mode,mf,timeout=180):
    fj=json.dumps(mf,ensure_ascii=False) if mf else "null"
    req=json.dumps({"query":query,"mode":mode,"filter_json":fj},ensure_ascii=False)
    def _do():
        proc.stdin.write(req+"\n"); proc.stdin.flush()
        line=proc.stdout.readline().strip()
        if not line: raise RuntimeError("后端无响应")
        return json.loads(line)
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        f=ex.submit(_do)
        try: return f.result(timeout=timeout)
        except concurrent.futures.TimeoutError: kill_backend(); raise RuntimeError("查询超时，后端已重启，请重试")


# ═══════════════════ Login ═══════════════════

def render_login_page():
    _,c,_=st.columns([1,1.5,1])
    with c:
        st.markdown("<br>"*3,unsafe_allow_html=True)
        st.markdown(
            '<div style="text-align:center;margin-bottom:2.5rem;">'
            '<div style="display:inline-flex;align-items:center;justify-content:center;width:60px;height:60px;'
            'border-radius:16px;background:linear-gradient(135deg,'+BLUE+',#6366F1);margin-bottom:1.2rem;">'+icon("cpu",30)+'</div>'
            '<h2 style="color:'+TEXT+';margin:0;font-weight:700;">IT-Ops-RAG</h2>'
            '<p style="color:'+TEXT_S+';font-size:0.85rem;margin-top:0.3rem;">智能 IT 运维知识库 · 企业级 RAG 问答系统</p></div>',
            unsafe_allow_html=True)
        t1,t2=st.tabs(["账号登录","注册账号"])
        with t1:
            with st.container(border=True):
                u=st.text_input("用户名",placeholder="请输入用户名",label_visibility="collapsed",key="li_u")
                p=st.text_input("密码",type="password",placeholder="请输入密码",label_visibility="collapsed",key="li_p")
                if st.button("登 录",type="primary",use_container_width=True):
                    if not u or not p: st.error("请输入用户名和密码")
                    else:
                        user=verify_login(u.strip(),p)
                        if user:
                            st.session_state.logged_in=True; st.session_state.current_user=user
                            repair_index(user["username"])
                            st.session_state.current_conv_id=create_conversation(user["username"]); st.rerun()
                        else: st.error("用户名或密码错误")
        with t2:
            with st.container(border=True):
                ru=st.text_input("用户名",placeholder="3个字符以上",label_visibility="collapsed",key="ru")
                rd=st.text_input("显示名称",placeholder="例如：张工",label_visibility="collapsed",key="rd")
                rp=st.text_input("密码",type="password",placeholder="4个字符以上",label_visibility="collapsed",key="rp")
                rp2=st.text_input("确认密码",type="password",placeholder="再次输入",label_visibility="collapsed",key="rp2")
                cr1,cr2=st.columns(2)
                with cr1: rr=st.selectbox("角色",ROLES,key="r_role")
                with cr2: rd2=st.selectbox("部门",DEPTS,key="r_dept")
                if st.button("注册账号",type="primary",use_container_width=True):
                    if not ru or not rd or not rp: st.error("请填写所有必填项")
                    elif rp!=rp2: st.error("两次密码不一致")
                    else:
                        ok,err=register_user(ru.strip(),rp,rd.strip(),rr,rd2)
                        st.success("注册成功！请切换到登录页") if ok else st.error(err)
        st.markdown('<div style="text-align:center;margin-top:2rem;"><p style="color:'+TEXT_T+';font-size:0.68rem;">IT Operations RAG System v1.0</p></div>',unsafe_allow_html=True)


# ═══════════════════ Personal Center ═══════════════════

def render_personal_center(user):
    st.markdown("<h3 style='color:"+TEXT+";margin-bottom:1rem;'>个人中心</h3>",unsafe_allow_html=True)
    users=load_users(); cur=users.get(user["username"],{})
    t1,t2,t3=st.tabs(["资料","偏好","统计"])
    with t1:
        ca,cf=st.columns([1,2])
        with ca:
            st.markdown(_avatar_html(st.session_state.current_user,64),unsafe_allow_html=True)
            upf=st.file_uploader("上传照片",type=["png","jpg","jpeg"],label_visibility="collapsed",key="pc_up")
            if upf:
                os.makedirs(AVATAR_DIR,exist_ok=True)
                ip=os.path.join(AVATAR_DIR,user["username"]+".png")
                with open(ip,"wb") as f: f.write(upf.getbuffer())
                st.session_state.current_user["avatar_image"]=ip
                update_user_profile(user["username"],{"avatar_image":ip}); st.rerun()
            if st.session_state.current_user.get("avatar_image"):
                if st.button("删除照片",key="pc_dp"):
                    img=st.session_state.current_user.pop("avatar_image",None)
                    if img and os.path.exists(img): os.remove(img)
                    update_user_profile(user["username"],{"avatar_image":""}); st.rerun()
        with cf:
            nd=st.text_input("显示名称",value=cur.get("display_name",""),key="pc_nd")
            c1,c2=st.columns(2)
            with c1:
                ri=ROLES.index(cur.get("role",ROLES[0])) if cur.get("role","") in ROLES else 0
                nr=st.selectbox("角色",ROLES,index=ri,key="pc_r")
            with c2:
                di=DEPTS.index(cur.get("department",DEPTS[0])) if cur.get("department","") in DEPTS else 0
                nd2=st.selectbox("部门",DEPTS,index=di,key="pc_d")
        with st.container(border=True):
            op=st.text_input("当前密码",type="password",placeholder="修改密码需验证",key="pc_op")
            np=st.text_input("新密码",type="password",placeholder="留空不修改",key="pc_np")
        cb1,cb2=st.columns(2)
        with cb1:
            if st.button("保存设置",type="primary",use_container_width=True):
                if np:
                    if hashlib.sha256(op.encode()).hexdigest()!=cur.get("password_hash",""): st.error("当前密码错误"); st.stop()
                    if len(np)<4: st.error("新密码至少4个字符"); st.stop()
                ups={"display_name":nd,"role":nr,"department":nd2}
                if np: ups["new_password"]=np
                if update_user_profile(user["username"],ups):
                    for k,v in ups.items():
                        if k!="new_password": st.session_state.current_user[k]=v
                    st.success("已保存"); st.rerun()
        with cb2:
            if st.button("← 返回",use_container_width=True): st.session_state.show_pc=False; st.rerun()
    with t2:
        with st.container(border=True):
            st.radio("检索模式",["quick","deep"],format_func=lambda x:"快速检索" if x=="quick" else "深度推理",label_visibility="collapsed",key="pc_mode")
        with st.container(border=True):
            st.multiselect("系统模块过滤",SYS,default=[],placeholder="全部模块",label_visibility="collapsed",key="pc_sys")
    with t3:
        idx=load_index(user["username"])
        st.metric("历史对话",len(idx)); st.metric("总消息数",sum(e.get("message_count",0) for e in idx))
        if st.button("退出登录",use_container_width=True): _do_logout(user)

def _do_logout(user):
    cid=st.session_state.get("current_conv_id"); msgs=st.session_state.get("messages",[])
    if cid and msgs: finalize_conversation(user["username"],cid,msgs)
    st.session_state.logged_in=False; st.session_state.current_user=None
    st.session_state.messages=[]; st.session_state.current_conv_id=None
    st.session_state.show_pc=False; st.rerun()


# ═══════════════════ Main App ═══════════════════

def build_filter(role,ss):
    f={}; rf=RF.get(role)
    if rf: f.update(rf)
    if ss: f["system_name"]=ss[0]
    return f if f else None

def render_main_app(user):
    # ── Top nav bar ──
    mode=st.session_state.get("pc_mode","quick"); ss=st.session_state.get("pc_sys",[])
    mode_label="深度推理" if mode=="deep" else "快速检索"
    mode_cls="chip-green" if mode=="deep" else ""
    chips='<span class="chip '+mode_cls+'">'+icon("bolt",12)+' '+mode_label+'</span>'
    for s in (ss or []): chips+='<span class="chip">'+s+'</span>'

    nav_left, nav_right = st.columns([6,1])
    with nav_left:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:12px;padding:8px 0 12px 0;border-bottom:1px solid '+BORDER+';margin-bottom:4px;">'
            +icon("cpu",24)+
            '<span style="font-weight:700;font-size:1rem;color:'+TEXT+';letter-spacing:-0.01em;">IT-Ops-RAG</span>'
            +chips+
            '</div>',unsafe_allow_html=True)
    with nav_right:
        st.markdown(
            '<div style="display:flex;align-items:center;justify-content:flex-end;gap:8px;padding:8px 0 12px 0;border-bottom:1px solid '+BORDER+';margin-bottom:4px;">'
            +_avatar_html(user,32)+
            '<span style="font-size:0.82rem;font-weight:500;color:'+TEXT+';">'+user["display_name"]+'</span>'
            '</div>',unsafe_allow_html=True)
        col_settings, _ = st.columns([1,3])
        with col_settings:
            if st.button("⚙ 设置",key="top_settings",use_container_width=True):
                st.session_state.show_pc=True; st.rerun()

    if st.session_state.get("show_pc"): render_personal_center(user); return

    # ── Two-column body ──
    left, right = st.columns([1, 3])

    with left:
        st.markdown('<div class="conv-scroll" style="padding-right:8px;">',unsafe_allow_html=True)
        if st.button("+ 新建对话",use_container_width=True,type="primary"):
            cid=st.session_state.get("current_conv_id"); msgs=st.session_state.get("messages",[])
            if cid and msgs: finalize_conversation(user["username"],cid,msgs)
            st.session_state.current_conv_id=create_conversation(user["username"]); st.session_state.messages=[]; st.rerun()

        st.markdown('<div style="margin:10px 0;"></div>',unsafe_allow_html=True)
        idx=load_index(user["username"]); cur_cid=st.session_state.get("current_conv_id","")
        st.caption("历史对话（"+str(len(idx))+"）")

        for entry in sorted(idx,key=lambda e:e.get("created_at",""),reverse=True):
            active=entry["id"]==cur_cid
            has=entry.get("has_content",entry.get("message_count",0)>=2)
            dot='● ' if has else '○ '
            cc,cd=st.columns([4.5,1])
            with cc:
                label=entry["title"][:20]+("…" if len(entry["title"])>20 else "")
                t="primary" if active else "secondary"
                if st.button(dot+label,key="c_"+entry["id"],use_container_width=True,type=t):
                    if not active:
                        oid=st.session_state.get("current_conv_id"); oms=st.session_state.get("messages",[])
                        if oid and oms: finalize_conversation(user["username"],oid,oms)
                        st.session_state.current_conv_id=entry["id"]
                        st.session_state.messages=load_conversation(user["username"],entry["id"]); st.rerun()
            with cd:
                if st.button("×", key="d_"+entry["id"]):
                    delete_conversation(user["username"],entry["id"])
                    if entry["id"]==cur_cid: st.session_state.current_conv_id=create_conversation(user["username"]); st.session_state.messages=[]
                    st.rerun()

        st.divider()
        if st.button("清空所有对话",use_container_width=True):
            for e in load_index(user["username"]): delete_conversation(user["username"],e["id"])
            st.session_state.current_conv_id=create_conversation(user["username"]); st.session_state.messages=[]; st.rerun()
        st.markdown('</div>',unsafe_allow_html=True)

    with right:
        if "messages" not in st.session_state: st.session_state.messages=[]
        if "current_conv_id" not in st.session_state: st.session_state.current_conv_id=create_conversation(user["username"])

        if not st.session_state.messages:
            assistant_card(
                '嗨，**'+user['display_name']+'**，我是 **小智**，你的 IT 运维助手。\n\n'
                '有什么运维问题尽管问我，比如：\n\n'
                '| 类别 | 示例 |\n|------|------|\n'
                '| 故障排查 | 服务器 CPU 飙高、内存泄漏、502 错误 |\n'
                '| 性能优化 | 慢查询分析、系统调优建议 |\n'
                '| 安全审计 | SSL 证书检查、安全配置核查 |\n'
                '| 监控告警 | Prometheus 查询、告警规则配置 |\n'
                '| 容器运维 | Docker 故障诊断、镜像管理 |\n\n'
                '每次回答都会标注来源。')

        for msg in st.session_state.messages:
            if msg["role"]=="user": user_card(msg["content"],user)
            else: assistant_card(msg["content"],msg.get("citations"))

    # ── Input: st.chat_input (Streamlit native fixed-bottom) + stop ──
    if "is_processing" not in st.session_state: st.session_state.is_processing = False

    # Stop/send row right above chat_input
    if st.session_state.is_processing:
        _, cs1, cs2 = st.columns([20, 1, 1])
        with cs1:
            st.caption("AI 正在生成回复...")
        with cs2:
            if st.button("⏹ 停止", key="stop_inline", type="secondary"):
                kill_backend()
                st.session_state.is_processing = False
                st.rerun()

    if prompt := st.chat_input("输入运维问题，例如：服务器 CPU 使用率过高如何处理？"):
        user_card(prompt, user)
        st.session_state.messages.append({"role":"user","content":prompt})
        st.session_state.is_processing = True
        mode=st.session_state.get("pc_mode","quick"); ss=st.session_state.get("pc_sys",[])
        mf=build_filter(user["role"],ss)
        with st.spinner(""):
            try:
                r=query_backend(backend,prompt,mode,mf); at,ct2=r["answer"],r.get("citations",[])
            except Exception as e:
                at="系统处理请求时出错："+str(e); ct2=[]
        assistant_card(at,ct2)
        st.session_state.messages.append({"role":"assistant","content":at,"citations":ct2})
        cid=st.session_state.get("current_conv_id")
        if cid:
            save_conversation(user["username"],cid,st.session_state.messages)
            finalize_conversation(user["username"],cid,st.session_state.messages)
        st.session_state.is_processing = False
        st.rerun()


# ═══════════════════ Entry ═══════════════════

inject_css()
if not st.session_state.get("logged_in"): render_login_page()
else: backend=get_backend(); render_main_app(st.session_state.current_user)
