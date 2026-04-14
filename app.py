import streamlit as st
import pandas as pd
import os
import base64
import requests
from datetime import datetime
import io

# --- 1. GitHub 연동 설정 (Secrets에서 가져오기) ---
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")
DB_FILE = "material_database.xlsx"
BRANCH = "main"

def save_to_github(file_content, message):
    """GitHub API를 통해 파일을 저장소에 푸시합니다."""
    url = f"https://api.github.com/repos/baedw0629-source/materialupdate/contents/material_database.xlsx"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    
    # 기존 파일의 SHA 값 가져오기 (덮어쓰기 위해 필요)
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

def load_from_github():
    """GitHub에서 최신 엑셀 파일을 불러옵니다."""
    url = f"https://raw.githubusercontent.com/{REPO_NAME}/{BRANCH}/{DB_FILE}"
    res = requests.get(url)
    if res.status_code == 200:
        return pd.read_excel(io.BytesIO(res.content), sheet_name=None)
    return None

# --- 2. 앱 초기화 및 데이터 로드 ---
st.set_page_config(page_title="자재/마감재 관리 시스템", layout="wide")
st.title("🏗️ 자재/마감재 통합 관리 시스템 (GitHub 동기화)")

if 'db' not in st.session_state:
    loaded_db = load_from_github()
    if loaded_db:
        st.session_state.db = loaded_db
    else:
        # 파일이 없을 경우 초기화
        st.session_state.db = {
            "material": pd.DataFrame(columns=["자재코드", "색상", "자재명", "규격상세", "규격구분", "주거래처", "주거래단가", "단위"]),
            "cover": pd.DataFrame(columns=["거래처명", "자재코드", "색상", "자재명", "규격상세", "통화", "자재단가", "거래 구분", "구매 구분"]),
            "update_log": pd.DataFrame(columns=["일시", "카테고리", "내용"])
        }

# --- 3. 화면 구성 (탭 활용) ---
tab1, tab2 = st.tabs(["✏️ 직접 편집 (화면 수정)", "📤 엑셀 대량 업데이트"])

# 공통 설정
category = st.sidebar.radio("카테고리 선택", ["material", "cover"])
conf = {"material": "일반 자재", "cover": "마감재"}[category]

# [탭 1] 직접 편집 페이지
with tab1:
    st.subheader(f"📍 {conf} 데이터 직접 수정")
    st.info("💡 표 안의 숫자를 클릭해서 바로 수정할 수 있습니다. 수정 후 반드시 하단 '변경사항 저장'을 눌러주세요.")
    
    # 직접 편집기 (st.data_editor)
    edited_df = st.data_editor(
        st.session_state.db[category], 
        use_container_width=True, 
        num_rows="dynamic",
        key=f"editor_{category}"
    )
    
    if st.button(f"💾 {conf} 변경사항 GitHub에 저장"):
        # 데이터 업데이트
        st.session_state.db[category] = edited_df
        
        # 엑셀 파일 생성
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for s_name, data in st.session_state.db.items():
                data.to_excel(writer, sheet_name=s_name, index=False)
        
        # GitHub 전송
        success = save_to_github(output.getvalue(), f"{conf} 수동 편집 저장 ({datetime.now()})")
        if success:
            st.success("GitHub 저장 성공! 이제 새로고침해도 데이터가 유지됩니다.")
            st.rerun()
        else:
            st.error("GitHub 저장 실패. Secrets 설정을 확인하세요.")

# [탭 2] 엑셀 대량 업데이트 (기존 로직)
with tab2:
    st.subheader("📤 엑셀 파일로 일괄 업데이트")
    uploaded_file = st.file_uploader("신규 분기 데이터를 올려주세요", type=["xlsx"])
    
    if uploaded_file:
        df_new = pd.read_excel(uploaded_file).where(pd.notnull(pd.read_excel(uploaded_file)), None)
        df_master = st.session_state.db[category]
        keys = ["자재코드", "색상"]
        
        # 덮어쓰기 로직 (신규 데이터에 값이 있는 경우만)
        m_df = df_master.set_index(keys)
        n_df = df_new.set_index(keys)
        m_df.update(n_df)
        new_entries = n_df[~n_df.index.isin(m_df.index)]
        df_final = pd.concat([m_df, new_entries]).reset_index()
        
        st.write("✅ 업데이트 결과 미리보기")
        st.dataframe(df_final, use_container_width=True)
        
        if st.button("🚀 이 결과로 GitHub 마스터 DB 갱신"):
            st.session_state.db[category] = df_final
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                for s_name, data in st.session_state.db.items():
                    data.to_excel(writer, sheet_name=s_name, index=False)
            
            if save_to_github(output.getvalue(), f"{conf} 엑셀 업데이트"):
                st.success("업데이트 및 GitHub 동기화 완료!")
                st.rerun()
