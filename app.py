import streamlit as st
import pandas as pd
import requests
import base64
import io
import os
from datetime import datetime
import time

# --- 1. GitHub 설정 ---
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")
DB_FILE = "material_database.xlsx"
BRANCH = "main"

# --- 2. 시트별 설정 (3중 키 유지) ---
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

# --- 3. 필수 함수 ---

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
            pd.DataFrame(data).to_excel(writer, sheet_name=s_name, index=False)
    
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
    return put_res.status_code in [200, 201], put_res.status_code

def get_excel_bytes(db_dict):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for s_name, data in db_dict.items():
            pd.DataFrame(data).to_excel(writer, sheet_name=s_name, index=False)
    return output.getvalue()

# --- 4. 메인 UI ---

st.set_page_config(page_title="자재/마감재 통합 관리 시스템", layout="wide")
st.title("🏗️ 자재/마감재 통합 관리 시스템")

if 'db' not in st.session_state:
    loaded = load_from_github()
    if loaded: st.session_state.db = loaded
    else:
        st.session_state.db = {
            "material": pd.DataFrame(columns=SHEET_CONFIG["material"]["columns"]),
            "cover": pd.DataFrame(columns=SHEET_CONFIG["cover"]["columns"]),
            "update_log": pd.DataFrame(columns=["일시", "카테고리", "변경건수", "추가건수"])
        }

log_df = st.session_state.db.get("update_log", pd.DataFrame(columns=["일시", "카테고리", "변경건수", "추가건수"]))
if not log_df.empty:
    st.write("🕒 **최근 업데이트 내역**")
    recent = log_df.sort_values(by="일시", ascending=False).head(4)
    cols = st.columns(4)
    for i, (_, row) in enumerate(recent.iterrows()):
        cols[i].info(f"**{row['카테고리']}**\n{row['일시']}\n변동:{row['변경건수']} / 신규:{row['추가건수']}")

st.divider()

category = st.sidebar.radio("카테고리 선택", ["material", "cover"], format_func=lambda x: SHEET_CONFIG[x]["name"])
conf = SHEET_CONFIG[category]

st.sidebar.divider()
st.sidebar.download_button("💾 전체 데이터 백업 (Excel)", get_excel_bytes(st.session_state.db), f"full_db_{datetime.now().strftime('%m%d')}.xlsx")

tab1, tab2 = st.tabs(["✏️ 직접 편집", "📤 엑셀 업데이트"])

# [탭 1: 직접 편집]
with tab1:
    st.subheader(f"📍 {conf['name']} 기준 데이터")
    # 중복 행이 있을 경우 시각적으로 경고
    if st.session_state.db[category].duplicated(subset=conf["keys"]).any():
        st.warning("⚠️ 현재 데이터에 [거래처+코드+색상]이 중복된 행이 있습니다. 수정 시 주의하세요.")
    
    edited_df = st.data_editor(st.session_state.db[category].astype(object), use_container_width=True, num_rows="dynamic")
    if st.button(f"💾 {conf['name']} 수정사항 저장"):
        st.session_state.db[category] = edited_df
        success, code = save_to_github(st.session_state.db, f"{conf['name']} 직접 편집")
        if success:
            st.toast("GitHub 저장 완료!"); time.sleep(1); st.rerun()
        else: st.error(f"저장 실패 (코드: {code})")

# [탭 2: 엑셀 업데이트]
with tab2:
    st.subheader(f"📤 {conf['name']} 엑셀 업로드")
    
    # 양식 받기 (기본 코드 유지)
    tmpl_bytes = io.BytesIO()
    with pd.ExcelWriter(tmpl_bytes, engine='xlsxwriter') as writer:
        pd.DataFrame(columns=conf["columns"]).to_excel(writer, sheet_name=6, index=False)
    st.download_button(f"📋 {conf['name']} 양식 받기", tmpl_bytes.getvalue(), f"{category}_template.xlsx")
    
    uploaded = st.file_uploader("파일 선택", type=["xlsx"])
    if uploaded:
        # 1. 데이터 클리닝 및 중복 제거 (핵심!)
        df_new_raw = pd.read_excel(uploaded).astype(object)
        available_cols = [c for c in conf["columns"] if c in df_new_raw.columns]
        df_new = df_new_raw[available_cols].where(pd.notnull(df_new_raw[available_cols]), None)
        
        # 업로드된 파일 자체에 중복이 있을 경우 첫 번째 것만 남김
        keys = conf["keys"]
        df_new = df_new.drop_duplicates(subset=keys, keep='first')
        
        df_master = st.session_state.db[category].copy().astype(object)
        
        # 2. 인덱스 설정 (비교를 위해)
        m_df = df_master.set_index(keys)
        n_df = df_new.set_index(keys)

        added_rows, changed_rows = [], []
        compare_cols = [c for c in n_df.columns if c in m_df.columns]

        # 3. 데이터 비교 루프 (에러 방지 강화)
        for idx in n_df.index:
            if idx not in m_df.index:
                # [신규 추가]
                row = n_df.loc[idx].to_dict()
                if isinstance(idx, tuple):
                    for i, k in enumerate(keys): row[k] = idx[i]
                added_rows.append(row)
            else:
                # [변경 체크] 
                is_changed = False
                for col in compare_cols:
                    # 마스터에서 값 추출 (여러 개일 경우 첫 번째 값만 scalar로 추출)
                    ov_raw = m_df.loc[[idx], col]
                    ov = ov_raw.values[0] if len(ov_raw) > 0 else None
                    
                    # 신규 데이터에서 값 추출
                    nv_raw = n_df.loc[[idx], col]
                    nv = nv_raw.values[0] if len(nv_raw) > 0 else None
                    
                    # 비교 로직 (단일 값임을 보장한 후 비교)
                    if pd.notnull(nv) and str(nv).strip() != "":
                        if str(nv).strip() != str(ov).strip():
                            is_changed = True
                            break
                
                if is_changed:
                    row = n_df.loc[idx].to_dict()
                    if isinstance(idx, tuple):
                        for i, k in enumerate(keys): row[k] = idx[i]
                    changed_rows.append(row)

        # 4. 화면 표시
        c1, c2 = st.columns(2)
        c1.warning(f"⚠️ 변경: {len(changed_rows)}건")
        c1.dataframe(pd.DataFrame(changed_rows), use_container_width=True)
        c2.success(f"➕ 신규: {len(added_rows)}건")
        c2.dataframe(pd.DataFrame(added_rows), use_container_width=True)

        # 5. 최종 반영 버튼
        if st.button("🚀 마스터 DB 최종 반영"):
            # 마스터 중복 정리
            m_df_final = m_df[~m_df.index.duplicated(keep='first')].copy()
            
            for idx in n_df.index:
                if idx in m_df_final.index:
                    for col in compare_cols:
                        # 신규 값 추출
                        val_raw = n_df.loc[[idx], col]
                        val = val_raw.values[0] if len(val_raw) > 0 else None
                        
                        if pd.notnull(val) and str(val).strip() != "":
                            m_df_final.at[idx, col] = val
            
            # 최종 결합 및 컬럼 순서 복구
            final_df = pd.concat([m_df_final, n_df[~n_df.index.isin(m_df_final.index)]]).reset_index()
            final_df = final_df[[c for c in conf["columns"] if c in final_df.columns]]
            
            st.session_state.db[category] = final_df
            
            # 로그 기록
            new_log = {
                "일시": datetime.now().strftime("%Y-%m-%d %H:%M"), 
                "카테고리": conf["name"], 
                "변경건수": len(changed_rows), 
                "추가건수": len(added_rows)
            }
            st.session_state.db["update_log"] = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
            
            success, code = save_to_github(st.session_state.db, f"{conf['name']} 엑셀 업데이트")
            if success:
                st.toast("✅ 동기화 완료!")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"❌ 저장 실패 (코드: {code})")
        
