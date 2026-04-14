import streamlit as st
import pandas as pd
import requests
import base64
import io
from datetime import datetime

# --- 1. 설정 ---
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME") # "baedw0629-source/materialupdate"
DB_FILE = "material_database.xlsx"
BRANCH = "main"

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
