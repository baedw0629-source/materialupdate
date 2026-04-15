import streamlit as st
import pandas as pd
import requests
import base64
import io
import os
from datetime import datetime
import time

# --- 1. GitHub 설정 (Streamlit Secrets에서 가져옴) ---
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")
DB_FILE = "material_database.xlsx"
BRANCH = "main"

# 시트별 설정: 거래처 정보를 포함한 3중 키 적용
SHEET_CONFIG = {
    "material": {
        "name": "일반 자재",
        "keys": ["주거래처", "자재코드", "색상"],
        "price_col": "주거래단가",
        "columns": ["자재코드", "색상", "자재명", "규격상세", "규격구분", "주거래처", "주거래단가", "단위"]
    },
    "cover": {
        "name": "마감재",
        "keys": ["거래처명", "자재코드", "색상"],
        "price_col": "자재단가",
        "columns": ["거래처명", "자재코드", "색상", "자재명", "규격상세", "통화", "자재단가", "거래 구분", "구매 구분"]
    }
}

# --- 2. 핵심 함수 정의 ---

def load_from_github():
    """GitHub API를 통해 엑셀 데이터를 가져옵니다."""
    if not GITHUB_TOKEN or not REPO_NAME:
        st.error("Secrets 설정(GITHUB_TOKEN, REPO_NAME)을 확인해주세요.")
        return None
    
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_FILE}?ref={BRANCH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        content_b64 = res.json().get("content")
        file_data = base64.b64decode(content_b64)
        return pd.read_excel(io.BytesIO(file_data), sheet_name=None, engine='openpyxl')
    return None

def save_to_github(all_data_dict, message):
    """모든 시트 데이터를 GitHub에 영구 저장합니다."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for s_name, data in all_data_dict.items():
            pd.DataFrame(data).to_excel(writer, sheet_name=s_name, index=False)
    
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    # 기존 파일의 SHA 값 확인 (덮어쓰기 필수 단계)
    res = requests.get(url, headers=headers)
    sha = res.json().get("sha") if res.status_code == 200 else None
    
    payload = {
        "message": message,
        "content": base64.b64encode(output.getvalue()).decode("utf-8"),
        "branch": BRANCH
    }
    if sha: payload["sha"] = sha
    
    put_res = requests.put(url, headers=headers, json=payload)
    return put_res.status_code in [200, 201], put_res.status_code

def get_excel_bytes(db_dict):
    """현재 세션의 데이터베이스를 엑셀 파일 형식으로 변환합니다."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for s_name, data in db_dict.items():
            pd.DataFrame(data).to_excel(writer, sheet_name=s_name, index=False)
    return output.getvalue()

# --- 3. 앱 레이아웃 및 로직 시작 ---

st.set_page_config(page_title="자재/마감재 통합 관리 시스템", layout="wide")
st.title("🏗️ 자재/마감재 통합 관리 시스템")

# 데이터 로딩 (세션 상태 관리)
if 'db' not in st.session_state:
    with st.spinner('GitHub에서 최신 정보를 불러오고 있습니다...'):
        loaded = load_from_github()
        if loaded:
            st.session_state.db = loaded
        else:
            # 초기 파일이 없는 경우 빈 구조 생성
            st.session_state.db = {
                "material": pd.DataFrame(columns=SHEET_CONFIG["material"]["columns"]),
                "cover": pd.DataFrame(columns=SHEET_CONFIG["cover"]["columns"]),
                "update_log": pd.DataFrame(columns=["일시", "카테고리", "변경건수", "추가건수"])
            }

# 상단: 최근 업데이트 로그 (최대 4개)
log_df = st.session_state.db.get("update_log", pd.DataFrame(columns=["일시", "카테고리", "변경건수", "추가건수"]))
if not log_df.empty:
    st.write("🕒 **최근 업데이트 내역**")
    recent = log_df.sort_values(by="일시", ascending=False).head(4)
    log_cols = st.columns(4)
    for i, (_, row) in enumerate(recent.iterrows()):
        log_cols[i].info(f"**{row['카테고리']}**\n{row['일시']}\n변동:{row['변경건수']} / 신규:{row['추가건수']}")

st.divider()

# 사이드바: 카테고리 선택 및 백업 다운로드
category = st.sidebar.radio("카테고리 선택", ["material", "cover"], format_func=lambda x: SHEET_CONFIG[x]["name"])
conf = SHEET_CONFIG[category]

st.sidebar.divider()
st.sidebar.write("💾 **데이터 백업**")
st.sidebar.download_button(
    label="전체 데이터 백업 (Excel)",
    data=get_excel_bytes(st.session_state.db),
    file_name=f"material_db_backup_{datetime.now().strftime('%m%d')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# 메인 기능 탭 구성
tab1, tab2 = st.tabs(["✏️ 직접 편집 및 확인", "📤 엑셀 일괄 업데이트"])

# --- [탭 1: 직접 편집] ---
with tab1:
    st.subheader(f"📍 {conf['name']} 기준 데이터")
    # astype(object) 처리로 타입 에러 방지
    current_df = st.session_state.db[category].astype(object)
    edited_df = st.data_editor(current_df, use_container_width=True, num_rows="dynamic", key=f"editor_{category}")
    
    if st.button(f"💾 {conf['name']} 수정사항 저장"):
        st.session_state.db[category] = edited_df
        success, code = save_to_github(st.session_state.db, f"{conf['name']} 수동 편집 저장")
        if success:
            st.toast("✅ GitHub 동기화 완료!", icon="🎉")
            time.sleep(1)
            st.rerun()
        else:
            st.error(f"❌ 저장 실패 (에러코드: {code})")

# --- [탭 2: 엑셀 업데이트] ---
with tab2:
    st.subheader(f"📤 {conf['name']} 엑셀 업로드 업데이트")
    
    # 1. 양식 다운로드
    tmpl_bytes = io.BytesIO()
    with pd.ExcelWriter(tmpl_bytes, engine='xlsxwriter') as writer:
        pd.DataFrame(columns=conf["columns"]).to_excel(writer, sheet_name="Sheet1", index=False)
    st.download_button(f"📋 {conf['name']} 업로드 양식 받기", tmpl_bytes.getvalue(), f"{category}_template.xlsx")
    
    # 2. 파일 업로드 (탭 이동 시 충돌 방지를 위한 고유 키 부여)
    uploaded = st.file_uploader("수정할 엑셀 파일을 선택하세요", type=["xlsx"], key=f"uploader_{category}")
    
    if uploaded:
        # 데이터 타입 고정 및 전처리
        df_new_raw = pd.read_excel(uploaded).astype(object)
        keys = conf["keys"]
        
        # [방어 로직] 탭 이동 시 이전 탭의 파일이 남아있는 경우 에러 방지
        if not all(k in df_new_raw.columns for k in keys):
            st.warning(f"⚠️ 업로드된 파일이 현재 선택된 '{conf['name']}' 양식과 일치하지 않습니다.")
            st.stop()

        # 필요한 컬럼만 추출 및 중복 제거
        available_cols = [c for c in conf["columns"] if c in df_new_raw.columns]
        df_new = df_new_raw[available_cols].where(pd.notnull(df_new_raw[available_cols]), None).drop_duplicates(subset=keys, keep='first')
        
        # 마스터 데이터 로드 및 인덱스 설정
        df_master = st.session_state.db[category].copy().astype(object)
        m_df = df_master.set_index(keys)
        n_df = df_new.set_index(keys)

        # 3. 변경/신규 내역 감지 루프
        added_rows = []
        changed_rows = []
        compare_cols = [c for c in n_df.columns if c in m_df.columns]

        for idx in n_df.index:
            if idx not in m_df.index:
                # [신규 추가 건]
                row = n_df.loc[idx].to_dict()
                if isinstance(idx, tuple):
                    for i, k in enumerate(keys): row[k] = idx[i]
                else: row[keys[0]] = idx
                added_rows.append(row)
            else:
                # [단가/정보 변경 건]
                is_changed = False
                for col in compare_cols:
                    # 중복 데이터 존재 시 첫 번째 값 추출 (안전장치)
                    ov_raw = m_df.loc[[idx], col]
                    ov = ov_raw.values[0] if len(ov_raw) > 0 else None
                    nv_raw = n_df.loc[[idx], col]
                    nv = nv_raw.values[0] if len(nv_raw) > 0 else None
                    
                    if pd.notnull(nv) and str(nv).strip() != "" and str(nv).strip() != str(ov).strip():
                        is_changed = True
                        break
                if is_changed:
                    row = n_df.loc[idx].to_dict()
                    if isinstance(idx, tuple):
                        for i, k in enumerate(keys): row[k] = idx[i]
                    else: row[keys[0]] = idx
                    changed_rows.append(row)

        # 4. 미리보기 표시
        st.write("🔍 **업데이트 예정 내역 미리보기**")
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            st.warning(f"⚠️ 정보 변경: {len(changed_rows)}건")
            if changed_rows: st.dataframe(pd.DataFrame(changed_rows), use_container_width=True)
        with p_col2:
            st.success(f"➕ 신규 추가: {len(added_rows)}건")
            if added_rows: st.dataframe(pd.DataFrame(added_rows), use_container_width=True)

        # 5. 최종 반영 및 저장
        if st.button("🚀 위 변경 사항을 마스터 DB에 최종 반영"):
            # 마스터 중복 인덱스 정리
            m_df_final = m_df[~m_df.index.duplicated(keep='first')].copy()
            
            # 지능형 업데이트 (신규 값 있을 때만 교체)
            for idx in n_df.index:
                if idx in m_df_final.index:
                    for col in compare_cols:
                        val_raw = n_df.loc[[idx], col]
                        val = val_raw.values[0] if len(val_raw) > 0 else None
                        if pd.notnull(val) and str(val).strip() != "":
                            m_df_final.at[idx, col] = val
            
            # 최종 데이터 결합
            final_df = pd.concat([m_df_final, n_df[~n_df.index.isin(m_df_final.index)]]).reset_index()
            final_df = final_df[[c for c in conf["columns"] if c in final_df.columns]]
            
            # 세션 상태 업데이트 및 로그 기록
            st.session_state.db[category] = final_df
            new_log = {
                "일시": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "카테고리": conf["name"],
                "변경건수": len(changed_rows),
                "추가건수": len(added_rows)
            }
            st.session_state.db["update_log"] = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
            
            # GitHub 저장
            success, code = save_to_github(st.session_state.db, f"{conf['name']} 엑셀 업데이트 반영")
            if success:
                st.toast("✅ 동기화 완료!", icon="🚀")
                # 성공 시 즉시 다운로드 버튼 노출
                st.download_button(
                    label="📥 업데이트 결과 엑셀 받기",
                    data=get_excel_bytes(st.session_state.db),
                    file_name=f"updated_{category}_{datetime.now().strftime('%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                time.sleep(2)
                st.rerun()
            else:
                st.error(f"❌ 저장 실패 (에러코드: {code})")
