import streamlit as st
import pandas as pd
import re
import os

# --- CONFIGURATION ---
# IMPORTANT: This filename must match exactly what is in your GitHub Repo
DEFAULT_MASTER_FILE = "Insurance_Creation_Master_New-Version.csv"

# --- CORE LOGIC ---

def normalize(val):
    """Removes non-alphanumeric chars and converts to lowercase."""
    if pd.isna(val): return ""
    return re.sub(r'[^a-zA-Z0-9]', '', str(val)).lower()

def standardize_id(val):
    """Aggressively pads numeric IDs to 5 digits and removes decimals/suffixes."""
    if pd.isna(val) or str(val).strip() == '': return ""
    # Handle "1111.0" or "37077-NOCD"
    val_str = str(val).split('.')[0].strip().split('-')[0]
    # Pad with zeros if it's a number less than 5 digits
    if val_str.isdigit() and len(val_str) < 5:
        return val_str.zfill(5)
    return val_str

@st.cache_data
def load_lookup_data(file_source):
    # Load Master with 'latin1' to handle special chars
    df = pd.read_csv(file_source, dtype=str, encoding='latin1').fillna('')
    
    id_map = {}
    name_map = {}
    master_names_list = [] # For partial matching

    for _, row in df.iterrows():
        pid = standardize_id(row.get('Payer ID', ''))
        # Get cleanest name available
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

# Check for Master File in Repo
if os.path.exists(DEFAULT_MASTER_FILE):
    m_df, m_id, m_name, m_name_list = load_lookup_data(DEFAULT_MASTER_FILE)
    st.sidebar.success(f"✅ Master DB Loaded from Repo: {len(m_df)} records")
else:
    st.error(f"❌ Could not find '{DEFAULT_MASTER_FILE}' in the repository. Please check the filename.")
    st.stop()

# File Upload
st.subheader("Step 1: Upload Data to Scrub")
target_files = st.file_uploader("Upload CSV or Excel", type=['csv', 'xlsx'], accept_multiple_files=True)

if target_files:
    for t_file in target_files:
        # Load File (Explicit engine='openpyxl' for Excel to prevent ImportError)
        if t_file.name.endswith('.csv'):
            t_df = pd.read_csv(t_file, dtype=str, encoding='latin1').fillna('')
        else:
            t_df = pd.read_excel(t_file, dtype=str, engine='openpyxl').fillna('')

        if st.button(f"🚀 Scrub {t_file.name}"):
            with st.spinner("Analyzing aliases and partial matches..."):
                results = []
                
                # Auto-detect any column that might contain names (Payer Name, Known Names, etc.)
                name_cols = [c for c in t_df.columns if 'NAME' in c.upper()]
                
                for _, row in t_df.iterrows():
                    # 1. Prepare Target ID
                    t_id = standardize_id(row.get('Payer ID', ''))
                    
                    # 2. Prepare Target Names (Split commas!)
                    potential_names = []
                    for col in name_cols:
                        raw_val = str(row.get(col, ''))
                        # Split by comma to handle "MEDICAID TEXAS, MEDICAID OF TEXAS"
                        parts = [normalize(x) for x in raw_val.split(',')]
                        potential_names.extend(parts)
                    
                    # Remove empty strings and duplicates
                    potential_names = list(set(filter(None, potential_names)))

                    match_data = None
                    method = "Unresolved"

                    # --- MATCHING LOGIC ---
                    
                    # Tier 1: Exact ID Match
                    if t_id in m_id:
                        match_data = m_id[t_id]
                        method = "ID Match"
                    
                    # Tier 2: Exact Name Match (Check every alias in the cell)
                    if not match_data:
                        for name in potential_names:
                            if name in m_name:
                                match_data = m_name[name]
                                method = f"Exact Name: {name}"
                                break
                    
                    # Tier 3: Partial Name Match (Target inside Master or Master inside Target)
                    if not match_data and potential_names:
                        for name in potential_names:
                            if len(name) < 4: continue # Skip short noise like "HMO"
                            
                            for m_n, m_d in m_name_list:
                                # Target "Triwest" is in Master "Triwest Healthcare"
                                if name in m_n: 
                                    match_data = m_d
                                    method = f"Partial: '{name}' in Master"
                                    break
                                # Master "Cigna" is in Target "Cigna Medicare"
                                if m_n in name:
                                    match_data = m_d
                                    method = f"Partial: Master in '{name}'"
                                    break
                            if match_data: break

                    # --- RESULT ASSIGNMENT ---
                    if match_data:
                        for col in m_df.columns:
                            if col not in t_df.columns:
                                row[col] = match_data[col]
                        row['Payer Std?'] = 'Yes'
                    else:
                        row['Payer Std?'] = 'No'
                    
                    row['Search Method'] = method
                    results.append(row)

                # Output
                final_df = pd.DataFrame(results)
                st.write(f"### Results for {t_file.name}")
                st.dataframe(final_df.head(50))
                
                csv = final_df.to_csv(index=False).encode('utf-8')
                st.download_button(f"📥 Download Result", csv, f"Mapped_{t_file.name}", "text/csv")
