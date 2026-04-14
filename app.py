import streamlit as st
import pandas as pd
import requests
import base64
import io
from datetime import datetime

# --- 1. 설정 (Secrets 확인) ---
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")
DB_FILE = "material_database.xlsx"
BRANCH = "main" # 본인의 GitHub 기본 브랜치 확인 (main 또는 master)

def load_from_github():
    """GitHub에서 최신 엑셀 파일을 불러옵니다."""
    if not GITHUB_TOKEN or not REPO_NAME:
        st.error("❌ Streamlit Secrets에 GITHUB_TOKEN 또는 REPO_NAME이 설정되지 않았습니다.")
        return None

    # 캐시 방지를 위해 시간값을 쿼리로 추가
    url = f"https://raw.githubusercontent.com/{REPO_NAME}/{BRANCH}/{DB_FILE}?nocache={datetime.now().timestamp()}"
    res = requests.get(url)
    
    if res.status_code == 200:
        return pd.read_excel(io.BytesIO(res.content), sheet_name=None, engine='openpyxl')
    else:
        st.warning(f"⚠️ GitHub에서 파일을 찾을 수 없습니다. (Status: {res.status_code})")
        st.info("💡 첫 번째 마스터 파일을 '엑셀 업데이트' 탭에서 업로드하여 저장소에 생성해주세요.")
        return None

def save_to_github(file_content, message):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
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

# --- 2. 앱 실행 로직 ---
st.set_page_config(page_title="자재/마감재 관리 시스템", layout="wide")
st.title("🏗️ 자재/마감재 통합 관리 시스템")

# 세션 상태에 데이터 로드
if 'db' not in st.session_state:
    loaded_db = load_from_github()
    if loaded_db:
        st.session_state.db = loaded_db
        st.success("✅ GitHub에서 최신 데이터를 불러왔습니다.")
    else:
        # 파일이 없을 경우 빈 구조 생성
        st.session_state.db = {
            "material": pd.DataFrame(columns=["자재코드", "색상", "자재명", "규격상세", "규격구분", "주거래처", "주거래단가", "단위"]),
            "cover": pd.DataFrame(columns=["거래처명", "자재코드", "색상", "자재명", "규격상세", "통화", "자재단가", "거래 구분", "구매 구분"]),
            "update_log": pd.DataFrame(columns=["일시", "카테고리", "내용"])
        }

# --- 3. UI 구성 (탭) ---
tab1, tab2 = st.tabs(["✏️ 직접 편집 및 확인", "📤 엑셀 일괄 업데이트"])

category = st.sidebar.radio("카테고리 선택", ["material", "cover"])
conf_name = "일반 자재" if category == "material" else "마감재"

with tab1:
    st.subheader(f"📍 {conf_name} 현재 데이터")
    
    # 데이터 에디터 (표시 및 수정 가능)
    edited_df = st.data_editor(
        st.session_state.db[category], 
        use_container_width=True, 
        num_rows="dynamic",
        key=f"editor_{category}"
    )
    
    if st.button(f"💾 {conf_name} 수정사항 GitHub에 영구 저장"):
        st.session_state.db[category] = edited_df
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for s_name, data in st.session_state.db.items():
                data.to_excel(writer, sheet_name=s_name, index=False)
        
        if save_to_github(output.getvalue(), f"{conf_name} 수동 편집"):
            st.success("🎉 GitHub 저장 성공! 이제 새로고침해도 유지됩니다.")
            st.rerun()

with tab2:
    st.subheader("📤 마스터 파일 최초 등록 및 일괄 업데이트")
    st.write("기존에 쓰시던 엑셀 파일을 여기에 올리고 '저장'을 누르면 GitHub에 마스터 파일이 생성됩니다.")
    
    uploaded_file = st.file_uploader("엑셀 파일 선택", type=["xlsx"])
    if uploaded_file:
        # 업로드 로직 동일... (생략)
