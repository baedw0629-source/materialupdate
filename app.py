import streamlit as st
import pandas as pd
import os

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
    """기존 엑셀 파일 로드 (없으면 빈 데이터 생성)"""
    if os.path.exists(DB_FILE):
        return pd.read_excel(DB_FILE, sheet_name=None)
    else:
        return {
            "material": pd.DataFrame(columns=SHEET_CONFIG["material"]["columns"]),
            "cover": pd.DataFrame(columns=SHEET_CONFIG["cover"]["columns"])
        }

st.set_page_config(page_title="자재/마감재 단가 관리", layout="wide")
st.title("📊 자재 데이터베이스 자동 업데이트 시스템")

all_sheets = load_all_data()

# 1. 카테고리 선택
category = st.sidebar.radio("작업 선택", ["material", "cover"], format_func=lambda x: SHEET_CONFIG[x]["name"])
conf = SHEET_CONFIG[category]
df_master = all_sheets.get(category, pd.DataFrame(columns=conf["columns"]))

st.subheader(f"📍 현재 등록된 {conf['name']} 현황")
st.dataframe(df_master, use_container_width=True)

# 2. 신규 파일 업로드
st.divider()
st.subheader(f"🆕 신규 분기 {conf['name']} 데이터 업로드")
uploaded_file = st.file_uploader("엑셀 파일을 선택하세요", type=["xlsx"])

if uploaded_file:
    df_new = pd.read_excel(uploaded_file)
    
    # 데이터 비교 로직 (Key: 자재코드, 색상)
    keys = conf["keys"]
    price_col = conf["price_col"]
    
    # 기존 데이터와 새 데이터를 병합하여 비교 대상 추출
    df_compare = pd.merge(
        df_master, df_new, on=keys, how='outer', suffixes=('_기존', '_신규')
    )

    # A. 단가 변경 품목 추출
    # 기존에 데이터가 있고(not null), 신규 단가가 기존과 다른 경우
    changed = df_compare[
        df_compare[f'{price_col}_기존'].notnull() & 
        df_compare[f'{price_col}_신규'].notnull() & 
        (df_compare[f'{price_col}_기존'] != df_compare[f'{price_col}_신규'])
    ].copy()
    
    # B. 신규 추가 품목 추출
    # 기존에 데이터가 없는(null) 경우
    added = df_compare[df_compare[f'{price_col}_기존'].isnull()].copy()

    # 화면 표시 (변경 내역 리포트)
    col1, col2 = st.columns(2)
    
    with col1:
        st.warning(f"⚠️ 단가 변경 건수: {len(changed)}건")
        if not changed.empty:
            # 보기 편하게 주요 정보만 추출
            display_changed = changed[keys + [f'{price_col}_기존', f'{price_col}_신규']]
            st.dataframe(display_changed, use_container_width=True)

    with col2:
        st.success(f"➕ 신규 추가 건수: {len(added)}건")
        if not added.empty:
            # 신규 데이터 컬럼명 정리해서 표시
            display_added = added.drop(columns=[c for c in added.columns if '_기존' in c])
            display_added.columns = [c.replace('_신규', '') for c in display_added.columns]
            st.dataframe(display_added[conf["columns"]], use_container_width=True)

    # 3. 데이터 업데이트 및 저장 버튼
    if st.button("✅ 위 변경 사항을 마스터 DB에 최종 반영합니다"):
        # Upsert 로직: 신규 데이터로 덮어쓰기
        # 1. 기존 마스터에서 신규와 겹치지 않는 것만 남김
        df_master_clean = df_master.set_index(keys).drop(index=df_new.set_index(keys).index, errors='ignore').reset_index()
        # 2. 신규 데이터 합치기
        df_updated = pd.concat([df_master_clean, df_new], ignore_index=True)
        # 3. 컬럼 순서 고정
        df_updated = df_updated[conf["columns"]]
        
        # 파일 저장
        all_sheets[category] = df_updated
        with pd.ExcelWriter(DB_FILE, engine='openpyxl') as writer:
            for s_name, data in all_sheets.items():
                data.to_excel(writer, sheet_name=s_name, index=False)
        
        st.balloons()
        st.success("데이터베이스 업데이트 완료! 아래 버튼으로 파일을 다운로드하세요.")
        st.rerun()

# 4. 전체 마스터 데이터 다운로드
if os.path.exists(DB_FILE):
    with open(DB_FILE, "rb") as f:
        st.sidebar.divider()
        st.sidebar.download_button(
            label="💾 전체 마스터 데이터 다운로드",
            data=f,
            file_name="material_database_updated.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
