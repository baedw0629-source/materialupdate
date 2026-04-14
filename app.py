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
        # 초기 파일 구조 생성
        return {
            "material": pd.DataFrame(columns=SHEET_CONFIG["material"]["columns"]),
            "cover": pd.DataFrame(columns=SHEET_CONFIG["cover"]["columns"]),
            "update_log": pd.DataFrame(columns=["일시", "카테고리", "변경건수", "추가건수"])
        }

def generate_template(columns):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        pd.DataFrame(columns=columns).to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

st.set_page_config(page_title="자재/마감재 단가 관리 시스템", layout="wide")

# 1. 제목 (날짜 제거)
st.title("🏗️ 자재/마감재 단가 관리 시스템")

all_sheets = load_all_data()
log_df = all_sheets.get("update_log", pd.DataFrame(columns=["일시", "카테고리", "변경건수", "추가건수"]))

# 2. 최근 업데이트 내역 표시 (최근 4개)
if not log_df.empty:
    st.write("🕒 **최근 업데이트 내역**")
    recent_logs = log_df.sort_values(by="일시", ascending=False).head(4)
    cols = st.columns(4)
    for i, (idx, row) in enumerate(recent_logs.iterrows()):
        with cols[i]:
            st.info(f"**{row['카테고리']}** ({row['일시']})\n\n변동:{row['변경건수']} / 신규:{row['추가건수']}")

st.divider()

# 3. 카테고리 선택 및 현황 표시
category = st.sidebar.radio("카테고리 선택", ["material", "cover"], format_func=lambda x: SHEET_CONFIG[x]["name"])
conf = SHEET_CONFIG[category]
df_master = all_sheets.get(category, pd.DataFrame(columns=conf["columns"]))

st.subheader(f"📍 {SHEET_CONFIG[category]['name']} 단가 기준")
st.dataframe(df_master, use_container_width=True)

# 4. 양식 및 업로드 섹션
st.divider()
col_down, col_up = st.columns([1, 3])

with col_down:
    st.write("📋 **양식 다운로드**")
    st.download_button(
        label=f"{conf['name']} 양식 받기",
        data=generate_template(conf["columns"]),
        file_name=f"{category}_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

with col_up:
    st.write(f"📤 **신규 단가 데이터 업로드 ({conf['name']})**")
    uploaded_file = st.file_uploader("파일을 선택하세요", type=["xlsx"], label_visibility="collapsed")

if uploaded_file:
    df_new = pd.read_excel(uploaded_file)
    # 빈 칸(NaN) 처리
    df_new = df_new.where(pd.notnull(df_new), None)
    
    keys = conf["keys"]
    price_col = conf["price_col"]
    
    # 데이터 비교
    df_compare = pd.merge(df_master, df_new, on=keys, how='outer', suffixes=('_기존', '_신규'))

    # 변경/추가 내역 분석
    changed = df_compare[
        df_compare[f'{price_col}_기존'].notnull() & 
        df_compare[f'{price_col}_신규'].notnull() & 
        (df_compare[f'{price_col}_기존'] != df_compare[f'{price_col}_신규'])
    ].copy()
    added = df_compare[df_compare[f'{price_col}_기존'].isnull()].copy()

    # 화면 표시
    rep1, rep2 = st.columns(2)
    with rep1:
        st.warning(f"⚠️ 단가 변경: {len(changed)}건")
        if not changed.empty:
            st.dataframe(changed[keys + [f'{price_col}_기존', f'{price_col}_신규']], use_container_width=True)
    with rep2:
        st.success(f"➕ 신규 추가: {len(added)}건")
        if not added.empty:
            st.dataframe(added[keys + [f'{price_col}_신규']], use_container_width=True)

    if st.button("✅ 변경 사항 최종 반영 및 저장"):
        # --- 정교화된 업데이트 로직 ---
        updated_rows = []
        
        # 1. 기존 데이터 업데이트 및 유지
        for _, row in df_compare.iterrows():
            new_data = {}
            # 기존 데이터가 없는 경우 (신규 추가)
            if pd.isna(row[f'{conf["columns"][-1]}_기존']) and not any(pd.isna(row[keys])):
                for col in conf["columns"]:
                    new_data[col] = row[f'{col}_신규'] if f'{col}_신규' in row else row.get(col)
            # 기존 데이터가 있는 경우 (수정)
            else:
                for col in conf["columns"]:
                    if col in keys:
                        new_data[col] = row[col]
                    elif col == price_col:
                        # 단가는 무조건 신규 값 (신규가 없으면 기존 유지)
                        new_data[col] = row[f'{col}_신규'] if pd.notnull(row[f'{col}_신규']) else row[f'{col}_기존']
                    else:
                        # 기타 필드는 신규 값이 있을 때만 업데이트, 비어있으면 기존 유지
                        if pd.notnull(row.get(f'{col}_신규')):
                            new_data[col] = row[f'{col}_신규']
                        else:
                            new_data[col] = row[f'{col}_기존']
            
            if any(new_data.values()):
                updated_rows.append(new_data)

        df_final = pd.DataFrame(updated_rows)[conf["columns"]]
        
        # 로그 기록 추가
        new_log = {
            "일시": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "카테고리": conf['name'],
            "변경건수": len(changed),
            "추가건수": len(added)
        }
        log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)

        # 파일 저장
        all_sheets[category] = df_final
        all_sheets["update_log"] = log_df
        
        with pd.ExcelWriter(DB_FILE, engine='xlsxwriter') as writer:
            for s_name, data in all_sheets.items():
                data.to_excel(writer, sheet_name=s_name, index=False)
        
        st.success("데이터베이스 업데이트 완료!")
        st.rerun()

# 5. 사이드바 다운로드
if os.path.exists(DB_FILE):
    with open(DB_FILE, "rb") as f:
        st.sidebar.divider()
        st.sidebar.download_button("💾 전체 DB 다운로드", f, file_name="material_db.xlsx")
