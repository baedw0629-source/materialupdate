import streamlit as st
import pandas as pd
import requests
import base64
import io
import os
from datetime import datetime

# --- 1. GitHub 연동 설정 (Streamlit Secrets 필수) ---
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")
DB_FILE = "material_database.xlsx"
BRANCH = "main"  # 저장소 기본 브랜치명이 master라면 master로 수정하세요.

# --- 2. 시트 구성 정의 ---
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

def load_from_github():
    """GitHub API를 통해 파일 데이터를 직접 가져옵니다."""
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_FILE}?ref={BRANCH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    res = requests.get(url, headers=headers)
    
    if res.status_code == 200:
        # GitHub API는 파일 내용을 base64로 인코딩해서 줍니다.
        content_b64 = res.json().get("content")
        file_data = base64.b64decode(content_b64)
        
        # 엑셀 읽기 시도
        try:
            db_dict = pd.read_excel(io.BytesIO(file_data), sheet_name=None, engine='openpyxl')
            return db_dict
        except Exception as e:
            st.error(f"❌ 엑셀 파일 형식이 잘못되었습니다: {e}")
            return None
    else:
        # 에러 상태를 화면에 출력 (디버깅용)
        st.sidebar.error(f"❌ 데이터 로드 실패 (Status: {res.status_code})")
        return None

# --- 2. 앱 실행 ---
st.set_page_config(page_title="자재/마감재 통합 관리 시스템", layout="wide")
st.title("🏗️ 자재/마감재 통합 관리 시스템")

# 데이터 로딩 및 강제 새로고침 기능
if st.sidebar.button("🔄 데이터 강제 새로고침"):
    st.session_state.db = load_from_github()
    st.rerun()

if 'db' not in st.session_state:
    with st.spinner('GitHub에서 최신 데이터를 가져오는 중...'):
        st.session_state.db = load_from_github()

# 데이터가 여전히 비어있을 때의 안내
if st.session_state.db is None:
    st.error("데이터를 불러올 수 없습니다. 사이드바의 에러 메시지나 Secrets 설정을 다시 확인해주세요.")
    st.stop()

# --- 3. 데이터 표시 및 편집 로직 (이전과 동일) ---
# ... (생략된 뒷부분 로직은 이전과 같게 유지하시면 됩니다)

def save_to_github(all_data_dict, message):
    """모든 시트 데이터를 GitHub에 저장합니다."""
    # 엑셀 파일 바이너리 생성
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for s_name, data in all_data_dict.items():
            data.to_excel(writer, sheet_name=s_name, index=False)
    file_content = output.getvalue()

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    # 기존 파일 SHA 확인
    res = requests.get(url, headers=headers)
    sha = res.json().get("sha") if res.status_code == 200 else None
    
    payload = {
        "message": message,
        "content": base64.b64encode(file_content).decode("utf-8"),
        "branch": BRANCH
    }
    if sha: payload["sha"] = sha
    
    put_res = requests.put(url, headers=headers, json=payload)
    return put_res.status_code in [200, 201]

# --- 4. 앱 메인 로직 ---
st.set_page_config(page_title="자재/마감재 관리 시스템", layout="wide")
st.title("🏗️ 자재/마감재 통합 관리 시스템")

# 데이터 로드
if 'db' not in st.session_state:
    loaded_db = load_from_github()
    if loaded_db:
        st.session_state.db = loaded_db
    else:
        # 파일이 없을 경우 초기 빈 구조 생성
        st.session_state.db = {
            "material": pd.DataFrame(columns=SHEET_CONFIG["material"]["columns"]),
            "cover": pd.DataFrame(columns=SHEET_CONFIG["cover"]["columns"]),
            "update_log": pd.DataFrame(columns=["일시", "카테고리", "변경건수", "추가건수"])
        }

# 최근 업데이트 내역 표시 (상단 4개)
log_df = st.session_state.db.get("update_log", pd.DataFrame(columns=["일시", "카테고리", "변경건수", "추가건수"]))
if not log_df.empty:
    st.write("🕒 **최근 업데이트 내역**")
    recent_logs = log_df.sort_values(by="일시", ascending=False).head(4)
    log_cols = st.columns(4)
    for i, (_, row) in enumerate(recent_logs.iterrows()):
        with log_cols[i]:
            st.info(f"**{row['카테고리']}** ({row['일시']})\n\n변동: {row['변경건수']} / 신규: {row['추가건수']}")

st.divider()

# 사이드바 설정
category = st.sidebar.radio("카테고리 선택", ["material", "cover"], format_func=lambda x: SHEET_CONFIG[x]["name"])
conf = SHEET_CONFIG[category]

# 탭 구성
tab1, tab2 = st.tabs(["✏️ 데이터 확인 및 직접 편집", "📤 엑셀 일괄 업데이트"])

# [탭 1: 직접 편집]
with tab1:
    st.subheader(f"📍 {conf['name']} 기준 데이터")
    edited_df = st.data_editor(st.session_state.db[category], use_container_width=True, num_rows="dynamic")
    
    if st.button(f"💾 {conf['name']} 수정사항 저장 (GitHub 동기화)"):
        st.session_state.db[category] = edited_df
        if save_to_github(st.session_state.db, f"{conf['name']} 직접 편집 저장"):
            st.success("GitHub에 성공적으로 저장되었습니다!")
            st.rerun()

# [탭 2: 엑셀 업데이트]
with tab2:
    st.subheader(f"📤 신규 {conf['name']} 데이터 업로드")
    
    # 양식 다운로드
    output_tmpl = io.BytesIO()
    with pd.ExcelWriter(output_tmpl, engine='xlsxwriter') as writer:
        pd.DataFrame(columns=conf["columns"]).to_excel(writer, index=False)
    st.download_button(f"📋 {conf['name']} 업로드 양식 받기", output_tmpl.getvalue(), f"{category}_template.xlsx")
    
    uploaded_file = st.file_uploader("수정할 엑셀 파일을 선택하세요", type=["xlsx"])
    
    if uploaded_file:
        df_new = pd.read_excel(uploaded_file).where(pd.notnull(pd.read_excel(uploaded_file)), None)
        df_master = st.session_state.db[category]
        keys = conf["keys"]
        price_col = conf["price_col"]
        
        # 데이터 비교 로직 (Update)
        m_df = df_master.set_index(keys)
        n_df = df_new.set_index(keys)
        
        # 변경/추가 건수 계산
        changed_count = len(n_df[n_df.index.isin(m_df.index)])
        added_count = len(n_df[~n_df.index.isin(m_df.index)])
        
        # 덮어쓰기 로직: 신규 데이터에 값이 있는 것만 업데이트
        m_df.update(n_df)
        new_entries = n_df[~n_df.index.isin(m_df.index)]
        df_final = pd.concat([m_df, new_entries]).reset_index()[conf["columns"]]
        
        st.write("✅ 업데이트 미리보기 (최종 반영 버튼을 눌러야 저장됩니다)")
        st.dataframe(df_final, use_container_width=True)
        
        if st.button("🚀 위 내용을 GitHub 마스터 DB에 반영"):
            st.session_state.db[category] = df_final
            
            # 로그 기록
            new_log = {
                "일시": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "카테고리": conf["name"],
                "변경건수": changed_count,
                "추가건수": added_count
            }
            st.session_state.db["update_log"] = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
            
            if save_to_github(st.session_state.db, f"{conf['name']} 엑셀 업데이트 반영"):
                st.success("GitHub 동기화 완료!")
                st.rerun()
