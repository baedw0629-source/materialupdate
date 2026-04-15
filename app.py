import streamlit as st
import pandas as pd
import requests
import base64
import io
from datetime import datetime
import time

# --- 1. 설정 및 초기화 ---
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")
DB_FILE = "material_database.xlsx"
BRANCH = "main"

SHEET_CONFIG = {
    "material": {
        "name": "일반 자재",
        "keys": ["자재코드", "색상"],
        "price_col": "주거래단가",
        "columns": ["자재코드", "색상", "자재명", "규격상세", "규격구분", "주거래처", "주거래단가", "단위"]
    },
    "cover": {
        "name": "마감재",
        "keys": ["자재코드", "색상"],
        "price_col": "자재단가",
        "columns": ["거래처명", "자재코드", "색상", "자재명", "규격상세", "통화", "자재단가", "거래 구분", "구매 구분"]
    }
}

# --- 2. 함수 정의 ---
def load_from_github():
    if not GITHUB_TOKEN or not REPO_NAME:
        st.error("Secrets 설정을 확인해주세요.")
        return None
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_FILE}?ref={BRANCH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        content_b64 = res.json().get("content")
        return pd.read_excel(io.BytesIO(base64.b64decode(content_b64)), sheet_name=None, engine='openpyxl')
    return None

def save_to_github(all_data_dict, message):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for s_name, data in all_data_dict.items():
            data.to_excel(writer, sheet_name=s_name, index=False)
    
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    res = requests.get(url, headers=headers)
    sha = res.json().get("sha") if res.status_code == 200 else None
    
    payload = {
        "message": message,
        "content": base64.b64encode(output.getvalue()).decode("utf-8"),
        "branch": BRANCH
    }
    if sha: payload["sha"] = sha
    
    put_res = requests.put(url, headers=headers, json=payload)
    
    if put_res.status_code in [200, 201]:
        return True, "성공"
    else:
        return False, f"실패 (에러코드: {put_res.status_code})"

# --- 3. 앱 레이아웃 ---
st.set_page_config(page_title="자재/마감재 관리 시스템", layout="wide")
st.title("🏗️ 자재/마감재 통합 관리 시스템")

# 데이터 로드 (세션 상태 관리)
if 'db' not in st.session_state:
    loaded = load_from_github()
    if loaded:
        st.session_state.db = loaded
    else:
        st.session_state.db = {
            "material": pd.DataFrame(columns=SHEET_CONFIG["material"]["columns"]),
            "cover": pd.DataFrame(columns=SHEET_CONFIG["cover"]["columns"]),
            "update_log": pd.DataFrame(columns=["일시", "카테고리", "변경건수", "추가건수"])
        }

# 상단 로그 표시
log_df = st.session_state.db.get("update_log", pd.DataFrame(columns=["일시", "카테고리", "변경건수", "추가건수"]))
if not log_df.empty:
    st.write("🕒 **최근 업데이트 내역**")
    recent = log_df.sort_values(by="일시", ascending=False).head(4)
    cols = st.columns(4)
    for i, (_, row) in enumerate(recent.iterrows()):
        cols[i].info(f"**{row['카테고리']}**\n\n{row['일시']}\n\n변동:{row['변경건수']} / 신규:{row['추가건수']}")

st.divider()

# 사이드바 및 탭
category = st.sidebar.radio("카테고리 선택", ["material", "cover"], format_func=lambda x: SHEET_CONFIG[x]["name"])
conf = SHEET_CONFIG[category]
tab1, tab2 = st.tabs(["✏️ 직접 편집", "📤 엑셀 업데이트"])

# [직접 편집]
with tab1:
    st.subheader(f"📍 {conf['name']} 편집")
    edited = st.data_editor(st.session_state.db[category], use_container_width=True, num_rows="dynamic")
    
    if st.button("💾 변경사항 저장"):
        st.session_state.db[category] = edited
        success, msg = save_to_github(st.session_state.db, f"{conf['name']} 직접 편집")
        if success:
            st.toast("✅ GitHub에 저장되었습니다!", icon="🎉")
            time.sleep(1)
            st.rerun()
        else:
            st.error(f"❌ 저장 실패: {msg}")

# [엑셀 업데이트]
with tab2:
    st.subheader(f"📤 {conf['name']} 엑셀 업로드")
    uploaded = st.file_uploader("파일 선택", type=["xlsx"])
    
    if uploaded:
        df_new = pd.read_excel(uploaded).where(pd.notnull(pd.read_excel(uploaded)), None)
        df_master = st.session_state.db[category]
        keys = conf["keys"]
        
        m_df = df_master.set_index(keys)
        n_df = df_new.set_index(keys)
        
        c_count = len(n_df[n_df.index.isin(m_df.index)])
        a_count = len(n_df[~n_df.index.isin(m_df.index)])
        
        m_df.update(n_df)
        df_final = pd.concat([m_df, n_df[~n_df.index.isin(m_df.index)]]).reset_index()[conf["columns"]]
        
        st.dataframe(df_final, use_container_width=True)
        
        if st.button("🚀 GitHub 마스터 반영"):
            st.session_state.db[category] = df_final
            new_log = {"일시": datetime.now().strftime("%Y-%m-%d %H:%M"), "카테고리": conf["name"], "변경건수": c_count, "추가건수": a_count}
            st.session_state.db["update_log"] = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
            
            success, msg = save_to_github(st.session_state.db, f"{conf['name']} 엑셀 반영")
            if success:
                st.toast("✅ 동기화 완료!", icon="🚀")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"❌ 동기화 실패: {msg}")
