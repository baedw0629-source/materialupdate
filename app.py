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
    
    # 양식 받기
    tmpl_bytes = io.BytesIO()
    with pd.ExcelWriter(tmpl_bytes, engine='xlsxwriter') as writer:
        pd.DataFrame(columns=conf["columns"]).to_excel(writer, index=False)
    st.download_button(f"📋 {conf['name']} 양식 받기", tmpl_bytes.getvalue(), f"{category}_template.xlsx")
    
    uploaded = st.file_uploader("파일 선택", type=["xlsx"])
    if uploaded:
        # 데이터 클리닝
        df_new_raw = pd.read_excel(uploaded).astype(object)
        # 양식에 있는 컬럼만 남기기 (KeyError 방지 핵심)
        available_cols = [c for c in conf["columns"] if c in df_new_raw.columns]
        df_new = df_new_raw[available_cols].where(pd.notnull(df_new_raw[available_cols]), None)
        
        df_master = st.session_state.db[category].copy().astype(object)
        keys = conf["keys"]
        
        # 인덱스 설정 전 중복 제거 (m_df_final에서 수행)
        m_df = df_master.set_index(keys)
        n_df = df_new.set_index(keys)

        added_rows, changed_rows = [], []
        
        # 비교용 컬럼 (인덱스 제외)
        compare_cols = [c for c in n_df.columns if c in m_df.columns]

        for idx in n_df.index:
            if idx not in m_df.index:
                row = n_df.loc[idx].to_dict()
                if isinstance(idx, tuple):
                    for i, k in enumerate(keys): row[k] = idx[i]
                added_rows.append(row)
            else:
                is_changed = False
                for col in compare_cols:
                    # 마스터 데이터에 중복이 있을 경우 첫 번째 값을 기준으로 비교
                    ov_series = m_df.loc[[idx], col]
                    ov = ov_series.iloc[0] if len(ov_series) > 0 else None
                    nv = n_df.loc[idx, col]
                    
                    if pd.notnull(nv) and nv != "" and str(nv).strip() != str(ov).strip():
                        is_changed = True; break
                if is_changed:
                    row = n_df.loc[idx].to_dict()
                    if isinstance(idx, tuple):
                        for i, k in enumerate(keys): row[k] = idx[i]
                    changed_rows.append(row)

        c1, c2 = st.columns(2)
        c1.warning(f"⚠️ 변경: {len(changed_rows)}건"); c1.dataframe(pd.DataFrame(changed_rows), use_container_width=True)
        c2.success(f"➕ 신규: {len(added_rows)}건"); c2.dataframe(pd.DataFrame(added_rows), use_container_width=True)

        if st.button("🚀 마스터 DB 최종 반영"):
            # 마스터 중복 제거 (덮어쓰기 에러 방지)
            m_df_final = m_df[~m_df.index.duplicated(keep='first')].copy()
            
            for idx in n_df.index:
                if idx in m_df_final.index:
                    for col in compare_cols:
                        val = n_df.loc[idx, col]
                        if pd.notnull(val) and str(val).strip() != "":
                            m_df_final.loc[idx, col] = val
            
            # 최종 결합
            final_df = pd.concat([m_df_final, n_df[~n_df.index.isin(m_df_final.index)]]).reset_index()
            final_df = final_df[[c for c in conf["columns"] if c in final_df.columns]]
            
            st.session_state.db[category] = final_df
            new_log = {"일시": datetime.now().strftime("%Y-%m-%d %H:%M"), "카테고리": conf["name"], "변경건수": len(changed_rows), "추가건수": len(added_rows)}
            st.session_state.db["update_log"] = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
            
            success, code = save_to_github(st.session_state.db, f"{conf['name']} 엑셀 업데이트")
            if success:
                st.toast("동기화 완료!"); st.rerun()
            else: st.error(f"저장 실패 (코드: {code})")
