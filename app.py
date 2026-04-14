import streamlit as st
import pandas as pd
import os
from datetime import datetime
import io

# 설정된 파일명 및 시트 정보
DB_FILE = "material_database.xlsx"
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

def load_all_data():
    if os.path.exists(DB_FILE):
        # 엔진을 명시적으로 지정하여 안정성 확보
        return pd.read_excel(DB_FILE, sheet_name=None, engine='openpyxl')
    else:
        return {
            "material": pd.DataFrame(columns=SHEET_CONFIG["material"]["columns"]),
            "cover": pd.DataFrame(columns=SHEET_CONFIG["cover"]["columns"]),
            "update_log": pd.DataFrame(columns=["일시", "카테고리", "변경건수", "추가건수"])
        }

st.set_page_config(page_title="자재/마감재 단가 관리 시스템", layout="wide")

# 1. 제목 (오늘 날짜 제거)
st.title("🏗️ 자재/마감재 단가 관리 시스템")

all_sheets = load_all_data()
log_df = all_sheets.get("update_log", pd.DataFrame(columns=["일시", "카테고리", "변경건수", "추가건수"]))

# 2. 최근 업데이트 내역 표시 (상단 4개)
if not log_df.empty:
    st.write("🕒 **최근 업데이트 내역**")
    recent_logs = log_df.sort_values(by="일시", ascending=False).head(4)
    cols = st.columns(4)
    for i, (idx, row) in enumerate(recent_logs.iterrows()):
        with cols[i]:
            st.info(f"**{row['카테고리']}**\n\n{row['일시']}\n\n변동:{row['변경건수']} / 신규:{row['추가건수']}")

st.divider()

# 3. 사이드바 및 현황
category = st.sidebar.radio("카테고리 선택", ["material", "cover"], format_func=lambda x: SHEET_CONFIG[x]["name"])
conf = SHEET_CONFIG[category]
df_master = all_sheets.get(category, pd.DataFrame(columns=conf["columns"]))

st.subheader(f"📍 {SHEET_CONFIG[category]['name']} 단가 기준")
st.dataframe(df_master, use_container_width=True)

# 4. 파일 업로드 섹션
st.divider()
col_down, col_up = st.columns([1, 3])
with col_down:
    st.write("📋 **양식 다운로드**")
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        pd.DataFrame(columns=conf["columns"]).to_excel(writer, index=False, sheet_name='Sheet1')
    st.download_button(label=f"{conf['name']} 양식 받기", data=output.getvalue(), file_name=f"{category}_template.xlsx")

with col_up:
    st.write(f"📤 **신규 단가 데이터 업로드 ({conf['name']})**")
    uploaded_file = st.file_uploader("수정할 엑셀 파일을 선택하세요", type=["xlsx"], label_visibility="collapsed")

if uploaded_file:
    df_new = pd.read_excel(uploaded_file, engine='openpyxl')
    keys = conf["keys"]
    price_col = conf["price_col"]
    
    # [데이터 비교] 변경사항 추적용
    df_compare = pd.merge(df_master, df_new, on=keys, how='outer', suffixes=('_기존', '_신규'))
    changed = df_compare[df_compare[f'{price_col}_기존'].notnull() & df_compare[f'{price_col}_신규'].notnull() & (df_compare[f'{price_col}_기존'] != df_compare[f'{price_col}_신규'])]
    added = df_compare[df_compare[f'{price_col}_기존'].isnull() & df_compare[f'{price_col}_신규'].notnull()]

    rep1, rep2 = st.columns(2)
    with rep1:
        st.warning(f"⚠️ 단가 변동: {len(changed)}건")
        if not changed.empty: st.dataframe(changed[keys + [f'{price_col}_기존', f'{price_col}_신규']], use_container_width=True)
    with rep2:
        st.success(f"➕ 신규 추가: {len(added)}건")
        if not added.empty: st.dataframe(added.filter(like='_신규').rename(columns=lambda x: x.replace('_신규','')), use_container_width=True)

    if st.button("✅ 변경 사항 최종 반영 및 저장"):
        # --- 핵심 로직: 신규 데이터의 빈칸은 기존 데이터를 유지함 ---
        m_df = df_master.copy()
        n_df = df_new.copy()

        # 자재코드와 색상을 인덱스로 설정하여 정확히 매칭
        m_df.set_index(keys, inplace=True)
        n_df.set_index(keys, inplace=True)

        # 1. 기존 데이터 업데이트 (update 함수는 n_df의 NaN 값을 무시하고 기존값을 유지함)
        m_df.update(n_df)

        # 2. 아예 없던 신규 데이터 추가
        new_entries = n_df[~n_df.index.isin(m_df.index)]
        df_final = pd.concat([m_df, new_entries]).reset_index()
        
        # 컬럼 순서 및 타입 정리
        df_final = df_final[conf["columns"]]
        
        # 로그 추가
        new_log = {"일시": datetime.now().strftime("%Y-%m-%d %H:%M"), "카테고리": conf['name'], "변경건수": len(changed), "추가건수": len(added)}
        log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)

        # 파일 최종 저장
        all_sheets[category] = df_final
        all_sheets["update_log"] = log_df
        
        with pd.ExcelWriter(DB_FILE, engine='openpyxl') as writer:
            for s_name, data in all_sheets.items():
                data.to_excel(writer, sheet_name=s_name, index=False)
        
        st.success("데이터베이스에 영구 저장되었습니다!")
        st.rerun()

# 5. 사이드바 통합 DB 다운로드
if os.path.exists(DB_FILE):
    with open(DB_FILE, "rb") as f:
        st.sidebar.divider()
        st.sidebar.download_button("💾 전체 DB 다운로드 (백업용)", f, file_name="material_database.xlsx")
