import streamlit as st
import pandas as pd
import re
import os

# --- CONFIGURATION ---
# Ensure this file is uploaded to your GitHub repository alongside this script
DEFAULT_MASTER_FILE = "Insurance_Creation_Master_New-Version.csv"

# --- CORE PROCESSING LOGIC ---

def normalize(val):
    """Removes all non-alphanumeric characters and converts to lowercase for fuzzy matching."""
    if pd.isna(val): return ""
    return re.sub(r'[^a-zA-Z0-9]', '', str(val)).lower()

def standardize_id(val):
    """Pads numeric IDs to 5 digits and handles suffixes (e.g., 37077-NOCD)."""
    if pd.isna(val) or str(val).strip() == '': return ""
    # Standardize by splitting at hyphens and taking the base ID
    val_str = str(val).strip().split('-')[0]
    return val_str.zfill(5) if val_str.isdigit() and len(val_str) < 5 else val_str

@st.cache_data
def load_lookup_data(file_source):
    """Loads master data and builds tiered lookup dictionaries."""
    df = pd.read_csv(file_source, dtype=str, encoding='latin1').fillna('')
    
    # Tiered Lookup Dictionaries
    lookups = {
        "full": {},     # (ID, Name, CH)
        "id_name": {},  # (ID, Name)
        "name_ch": {},  # (Name, CH)
        "id_ch": {},    # (ID, CH)
        "id_only": {},  # ID
        "name_only": {} # Name
    }

    for _, row in df.iterrows():
        pid = standardize_id(row.get('Payer ID', ''))
        pname = normalize(row.get('Clean_payer Name') if row.get('Clean_payer Name') else row.get('Payer Name', ''))
        ch = str(row.get('Source_File', '')).strip().upper()
        data = row.to_dict()

        # Build Lookups
        if pid and pname and ch: lookups["full"].setdefault((pid, pname, ch), data)
        if pid and pname: lookups["id_name"].setdefault((pid, pname), data)
        if pname and ch: lookups["name_ch"].setdefault((pname, ch), data)
        if pid and ch: lookups["id_ch"].setdefault((pid, ch), data)
        if pid: lookups["id_only"].setdefault(pid, data)
        if pname: lookups["name_only"].setdefault(pname, data)
            
    return df, lookups

# --- STREAMLIT UI ---

st.set_page_config(page_title="Scrubber Pro", layout="wide")
st.title("🛡️ Scrubber Pro: Cloud Edition")

# Check for Master File in the repository
if os.path.exists(DEFAULT_MASTER_FILE):
    m_df, m_lookups = load_lookup_data(DEFAULT_MASTER_FILE)
    st.sidebar.success(f"✅ Master Sheet Pre-loaded ({len(m_df)} records)")
else:
    st.sidebar.error("⚠️ Master Sheet not found in repository.")
    manual_master = st.sidebar.file_uploader("Upload Master Payer List (CSV)", type=['csv'])
    if manual_master:
        m_df, m_lookups = load_lookup_data(manual_master)
        st.sidebar.success("✅ Manual Master Sheet Loaded")
    else:
        st.info("Please ensure 'Insurance_Master_Final_Naming_Updated.csv' is in your GitHub repo.")
        st.stop()

# File Upload Section for target claims
st.subheader("Step 1: Upload Claims or Payer Files")
target_files = st.file_uploader("Drop your files here", type=['csv', 'xlsx'], accept_multiple_files=True)

if target_files:
    for target_file in target_files:
        # Load the uploaded target file
        if target_file.name.endswith('.csv'):
            t_df = pd.read_csv(target_file, dtype=str, encoding='latin1').fillna('')
        else:
            t_df = pd.read_excel(target_file, dtype=str).fillna('')
        
        if st.button(f"🚀 Process {target_file.name}"):
            with st.spinner(f"Scrubbing {target_file.name}..."):
                results = []
                # Find Clearinghouse column
                ch_col = next((c for c in ['Clearinghouse ID', 'CH Names', 'Source_File'] if c in t_df.columns), None)

                for _, row in t_df.iterrows():
                    pid = standardize_id(row.get('Payer ID', ''))
                    pname = normalize(row.get('Payer Name', ''))
                    ch = str(row.get(ch_col, '')).strip().upper() if ch_col else ""
                    
                    match, method = None, "No Match"

                    # --- TIERED SEARCH HIERARCHY ---
                    # Tier 1: Triple Match
                    if (pid, pname, ch) in m_lookups["full"]:
                        match, method = m_lookups["full"][(pid, pname, ch)], "Tier 1: ID+Name+CH"
                    
                    # Tier 2: Double Matches
                    elif (pid, pname) in m_lookups["id_name"]:
                        match, method = m_lookups["id_name"][(pid, pname)], "Tier 2: ID+Name"
                    elif (pname, ch) in m_lookups["name_ch"]:
                        match, method = m_lookups["name_ch"][(pname, ch)], "Tier 2: Name+CH"
                    elif (pid, ch) in m_lookups["id_ch"]:
                        match, method = m_lookups["id_ch"][(pid, ch)], "Tier 2: ID+CH"
                    
                    # Tier 3: Single Factor Matches
                    elif pid in m_lookups["id_only"]:
                        match, method = m_lookups["id_only"][pid], "Tier 3: ID Only"
                    elif pname in m_lookups["name_only"]:
                        match, method = m_lookups["name_only"][pname], "Tier 3: Name Only"

                    if match:
                        # Map missing columns from Master to the row
                        for col in m_df.columns:
                            if col not in t_df.columns:
                                row[col] = match[col]
                        row['Payer Std?'] = 'Yes'
                        row['Search Method'] = method
                    else:
                        row['Payer Std?'] = 'No'
                        row['Search Method'] = 'Unresolved'
                    
                    results.append(row)

                processed_df = pd.DataFrame(results)
                
                # Display and Download
                st.write(f"### Results for {target_file.name}")
                st.dataframe(processed_df.head(20))
                
                csv_data = processed_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=f"📥 Download Scrubbed_{target_file.name}",
                    data=csv_data,
                    file_name=f"Scrubbed_{target_file.name}",
                    mime="text/csv"
                )