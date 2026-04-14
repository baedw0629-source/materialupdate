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
        return pd.read_excel(DB_FILE, sheet_name=None)
    else:
        return {
            "material": pd.DataFrame(columns=SHEET_CONFIG["material"]["columns"]),
            "cover": pd.DataFrame(columns=SHEET_CONFIG["cover"]["columns"])
        }

# 엑셀 양식 생성을 위한 함수
def generate_template(columns):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        pd.DataFrame(columns=columns).to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

st.set_page_config(page_title="자재/마감재 단가 관리 시스템", layout="wide")

# 제목 수정
st.title("🏗️ 자재/마감재 단가 관리 시스템")

all_sheets = load_all_data()

# 1. 카테고리 선택
category = st.sidebar.radio("카테고리 선택", ["material", "cover"], format_func=lambda x: SHEET_CONFIG[x]["name"])
conf = SHEET_CONFIG[category]
df_master = all_sheets.get(category, pd.DataFrame(columns=conf["columns"]))

# 오늘 날짜 기준 헤더 수정
today_str = datetime.now().strftime("%Y-%m-%d")
st.subheader(f"📍 {SHEET_CONFIG[category]['name']} 단가 기준 ({today_str})")
st.dataframe(df_master, use_container_width=True)

# 2. 양식 다운로드 및 업로드 섹션
st.divider()
col_down, col_up = st.columns([1, 3])

with col_down:
    st.write("📋 **양식 다운로드**")
    template_data = generate_template(conf["columns"])
    st.download_button(
        label=f"{conf['name']} 업로드 양식 받기",
        data=template_data,
        file_name=f"{category}_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="template_download"
    )

with col_up:
    # 문구 수정 (이모티콘 제거 및 이름 변경)
    st.write(f"📤 **신규 단가 데이터 업로드 ({conf['name']})**")
    uploaded_file = st.file_uploader("수정 또는 추가할 엑셀 파일을 선택하세요", type=["xlsx"], label_visibility="collapsed")

if uploaded_file:
    df_new = pd.read_excel(uploaded_file)
    keys = conf["keys"]
    price_col = conf["price_col"]
    
    # 데이터 비교 로직
    df_compare = pd.merge(df_master, df_new, on=keys, how='outer', suffixes=('_기존', '_신규'))

    changed = df_compare[
        df_compare[f'{price_col}_기존'].notnull() & 
        df_compare[f'{price_col}_신규'].notnull() & 
        (df_compare[f'{price_col}_기존'] != df_compare[f'{price_col}_신규'])
    ].copy()
    
    added = df_compare[df_compare[f'{price_col}_기존'].isnull()].copy()

    # 변경 내역 표시
    report_col1, report_col2 = st.columns(2)
    with report_col1:
        st.warning(f"⚠️ 단가 변경 건수: {len(changed)}건")
        if not changed.empty:
            st.dataframe(changed[keys + [f'{price_col}_기존', f'{price_col}_신규']], use_container_width=True)

    with report_col2:
        st.success(f"➕ 신규 추가 건수: {len(added)}건")
        if not added.empty:
            display_added = added.drop(columns=[c for c in added.columns if '_기존' in c])
            display_added.columns = [c.replace('_신규', '') for c in display_added.columns]
            st.dataframe(display_added[conf["columns"]], use_container_width=True)

    if st.button("✅ 변경 사항 최종 반영 및 저장"):
        df_master_clean = df_master.set_index(keys).drop(index=df_new.set_index(keys).index, errors='ignore').reset_index()
        df_updated = pd.concat([df_master_clean, df_new], ignore_index=True)
        df_updated = df_updated[conf["columns"]]
        
        all_sheets[category] = df_updated
        with pd.ExcelWriter(DB_FILE, engine='xlsxwriter') as writer:
            for s_name, data in all_sheets.items():
                data.to_excel(writer, sheet_name=s_name, index=False)
        
        st.balloons()
        st.success("데이터베이스 업데이트 완료!")
        st.rerun()

# 4. 전체 마스터 데이터 다운로드
if os.path.exists(DB_FILE):
    with open(DB_FILE, "rb") as f:
        st.sidebar.divider()
        st.sidebar.download_button(
            label="💾 전체 데이터베이스 다운로드",
            data=f,
            file_name="material_database_updated.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
