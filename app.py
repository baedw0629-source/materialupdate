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
            
# [탭 2: 엑셀 업데이트]
with tab2:
    st.subheader(f"📤 {conf['name']} 엑셀 업로드")
    
    # 양식 다운로드 버튼 부분은 기존과 동일
    output_tmpl = io.BytesIO()
    with pd.ExcelWriter(output_tmpl, engine='xlsxwriter') as writer:
        pd.DataFrame(columns=conf["columns"]).to_excel(writer, index=False)
    st.download_button(f"📋 {conf['name']} 업로드 양식 받기", output_tmpl.getvalue(), f"{category}_template.xlsx")
    
    uploaded = st.file_uploader("수정할 엑셀 파일을 선택하세요", type=["xlsx"])
    
    if uploaded:
        # 1. 데이터 읽기 및 타입 통일
        df_new = pd.read_excel(uploaded).astype(object)
        df_new = df_new.where(pd.notnull(df_new), None)
        
        df_master = st.session_state.db[category].copy().astype(object)
        keys = conf["keys"]
        
        m_df = df_master.set_index(keys)
        n_df = df_new.set_index(keys)

        # --- 변경 및 추가 데이터 감지 ---
        added_rows = []
        changed_rows = []
        
        # 신규/변경 체크
        for idx in n_df.index:
            if idx not in m_df.index:
                # [추가] 기존에 없는 데이터
                row = n_df.loc[idx].to_dict()
                if isinstance(idx, tuple):
                    for i, k in enumerate(keys): row[k] = idx[i]
                else:
                    row[keys[0]] = idx
                added_rows.append(row)
            else:
                # [변경] 기존에 있는데 값이 다른 데이터
                is_changed = False
                for col in n_df.columns:
                    new_val = n_df.loc[idx, col]
                    old_val = m_df.loc[idx, col]
                    # 신규 값이 있고(빈칸 아님), 기존 값과 다를 때만 '변경'으로 간주
                    if pd.notnull(new_val) and new_val != "" and str(new_val) != str(old_val):
                        is_changed = True
                        break
                
                if is_changed:
                    row = n_df.loc[idx].to_dict()
                    if isinstance(idx, tuple):
                        for i, k in enumerate(keys): row[k] = idx[i]
                    else:
                        row[keys[0]] = idx
                    changed_rows.append(row)

        df_added_preview = pd.DataFrame(added_rows)
        df_changed_preview = pd.DataFrame(changed_rows)

        # --- 화면 표시 ---
        st.write("🔍 **업데이트 예정 내역 미리보기**")
        
        col_view1, col_view2 = st.columns(2)
        with col_view1:
            st.warning(f"⚠️ 단가/정보 변경: {len(df_changed_preview)}건")
            if not df_changed_preview.empty:
                st.dataframe(df_changed_preview[conf["columns"]], use_container_width=True)
        
        with col_view2:
            st.success(f"➕ 신규 항목 추가: {len(df_added_preview)}건")
            if not df_added_preview.empty:
                st.dataframe(df_added_preview[conf["columns"]], use_container_width=True)

        # --- 실제 반영용 전체 데이터 생성 (버튼 클릭 시 저장될 데이터) ---
        # 기존 마스터를 복사해서 업데이트 진행
        m_df_final = m_df.copy()
        for idx in n_df.index:
            if idx in m_df_final.index:
                for col in n_df.columns:
                    val = n_df.loc[idx, col]
                    if pd.notnull(val) and val != "":
                        m_df_final.at[idx, col] = val
        
        new_entries = n_df[~n_df.index.isin(m_df_final.index)]
        df_final_to_save = pd.concat([m_df_final, new_entries]).reset_index()[conf["columns"]]

        if st.button("🚀 위 변경 사항만 확인했습니다. 마스터 DB 반영!"):
            st.session_state.db[category] = df_final_to_save
            
            # 로그 기록 및 저장 로직은 기존과 동일...
            new_log = {
                "일시": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "카테고리": conf["name"],
                "변경건수": len(df_changed_preview),
                "추가건수": len(df_added_preview)
            }
            st.session_state.db["update_log"] = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
            
            success, msg = save_to_github(st.session_state.db, f"{conf['name']} 엑셀 업데이트")
            if success:
                st.toast("✅ 동기화 완료!", icon="🚀")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"❌ 저장 실패: {msg}")
                
def get_excel_bytes(db_dict):
    """현재 세션 상태의 모든 시트를 하나의 엑셀 파일로 변환"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for s_name, data in db_dict.items():
            # 데이터가 비어있지 않은 경우에만 시트 생성
            df = pd.DataFrame(data)
            df.to_excel(writer, sheet_name=s_name, index=False)
    return output.getvalue()

# [탭 2: 엑셀 업데이트] 내부의 if st.button("🚀 위 내용을 GitHub 마스터 DB에 반영"): 블록 내부
if success:
    st.toast("✅ 동기화 완료!", icon="🚀")
    # 반영 성공 후 즉시 다운로드 버튼 노출 (사용자 편의성)
    st.download_button(
        label="📥 업데이트된 결과 파일 즉시 받기",
        data=get_excel_bytes(st.session_state.db),
        file_name=f"updated_{category}_{datetime.now().strftime('%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_after_success"
    )
    time.sleep(2) # 메시지를 볼 시간을 조금 더 줌
    st.rerun()

# 사이드바 최하단에 배치
st.sidebar.divider()
st.sidebar.write("💾 **데이터 관리**")
if 'db' in st.session_state:
    st.sidebar.download_button(
        label="전체 데이터베이스 다운로드",
        data=get_excel_bytes(st.session_state.db),
        file_name=f"material_db_full_{datetime.now().strftime('%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
