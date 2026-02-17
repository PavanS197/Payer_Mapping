import streamlit as st
import pandas as pd
import re
import os
import sys

# --- DIAGNOSTIC CHECK ---
# This will print to the app if openpyxl is actually installed
try:
    import openpyxl
    OPENPYXL_FOUND = True
except ImportError:
    OPENPYXL_FOUND = False

# --- CONFIGURATION ---
DEFAULT_MASTER_FILE = "Insurance_Creation_Master_New-Version.csv"

# --- CORE LOGIC ---
def normalize(val):
    if pd.isna(val): return ""
    return re.sub(r'[^a-zA-Z0-9]', '', str(val)).lower()

def standardize_id(val):
    if pd.isna(val) or str(val).strip() == '': return ""
    val_str = str(val).split('.')[0].strip().split('-')[0]
    if val_str.isdigit() and len(val_str) < 5:
        return val_str.zfill(5)
    return val_str

@st.cache_data
def load_lookup_data(file_source):
    df = pd.read_csv(file_source, dtype=str, encoding='latin1').fillna('')
    id_map = {}
    name_map = {}
    master_names_list = []

    for _, row in df.iterrows():
        pid = standardize_id(row.get('Payer ID', ''))
        raw_name = row.get('Clean_payer Name') if row.get('Clean_payer Name') else row.get('Payer Name', '')
        pname = normalize(raw_name)
        data = row.to_dict()
        
        if pid: id_map[pid] = data
        if pname: 
            name_map[pname] = data
            master_names_list.append((pname, data))
            
    return df, id_map, name_map, master_names_list

# --- STREAMLIT UI ---
st.set_page_config(page_title="Scrubber Pro v2", layout="wide")
st.title("🛡️ Scrubber Pro: Intelligent Mapper")

# Diagnostic Message
if not OPENPYXL_FOUND:
    st.error("⚠️ CRITICAL ERROR: The 'openpyxl' library is missing. You cannot process Excel files.")
    st.info("To fix this: Ensure 'requirements.txt' exists in your GitHub root and contains the word 'openpyxl'. Then Delete and Re-deploy the app.")

# Check for Master File
if os.path.exists(DEFAULT_MASTER_FILE):
    m_df, m_id, m_name, m_name_list = load_lookup_data(DEFAULT_MASTER_FILE)
    st.sidebar.success(f"✅ Master DB Loaded: {len(m_df)} records")
else:
    st.error(f"❌ Master file not found: {DEFAULT_MASTER_FILE}")
    st.stop()

# File Upload
st.subheader("Step 1: Upload Data")
target_files = st.file_uploader("Upload CSV or Excel", type=['csv', 'xlsx'], accept_multiple_files=True)

if target_files:
    for t_file in target_files:
        try:
            # LOAD FILE LOGIC
            if t_file.name.endswith('.csv'):
                t_df = pd.read_csv(t_file, dtype=str, encoding='latin1').fillna('')
            else:
                if not OPENPYXL_FOUND:
                    st.error(f"❌ Cannot open {t_file.name} because openpyxl is missing.")
                    continue
                t_df = pd.read_excel(t_file, dtype=str, engine='openpyxl').fillna('')

            if st.button(f"🚀 Scrub {t_file.name}"):
                with st.spinner("Analyzing..."):
                    results = []
                    name_cols = [c for c in t_df.columns if 'NAME' in c.upper()]
                    
                    for _, row in t_df.iterrows():
                        t_id = standardize_id(row.get('Payer ID', ''))
                        
                        potential_names = []
                        for col in name_cols:
                            raw_val = str(row.get(col, ''))
                            parts = [normalize(x) for x in raw_val.split(',')]
                            potential_names.extend(parts)
                        potential_names = list(set(filter(None, potential_names)))

                        match_data = None
                        method = "Unresolved"

                        # MATCHING LOGIC
                        if t_id in m_id:
                            match_data = m_id[t_id]
                            method = "ID Match"
                        
                        if not match_data:
                            for name in potential_names:
                                if name in m_name:
                                    match_data = m_name[name]
                                    method = f"Exact Name: {name}"
                                    break
                        
                        if not match_data and potential_names:
                            for name in potential_names:
                                if len(name) < 4: continue
                                for m_n, m_d in m_name_list:
                                    if name in m_n: 
                                        match_data = m_d
                                        method = f"Partial: '{name}' in Master"
                                        break
                                    if m_n in name:
                                        match_data = m_d
                                        method = f"Partial: Master in '{name}'"
                                        break
                                if match_data: break

                        if match_data:
                            for col in m_df.columns:
                                if col not in t_df.columns:
                                    row[col] = match_data[col]
                            row['Payer Std?'] = 'Yes'
                        else:
                            row['Payer Std?'] = 'No'
                        
                        row['Search Method'] = method
                        results.append(row)

                    final_df = pd.DataFrame(results)
                    st.write(f"### Results for {t_file.name}")
                    st.dataframe(final_df.head(50))
                    csv = final_df.to_csv(index=False).encode('utf-8')
                    st.download_button(f"📥 Download Result", csv, f"Mapped_{t_file.name}", "text/csv")
        
        except Exception as e:
            st.error(f"Error processing {t_file.name}: {str(e)}")
