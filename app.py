"""
Ortegas Auto - Gestión de Facturación por Usuarios y Clientes
Stack: Streamlit, Pandas, pdfplumber, openpyxl
"""

import streamlit as st
import pandas as pd
import pdfplumber
import openpyxl
from openpyxl.utils.dataframe import dataframe_to_rows
from io import BytesIO
import json
from pathlib import Path
from datetime import datetime

# Configuración de página
st.set_page_config(
    page_title="Ortegas Auto - Gestión de Facturación",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos personalizados
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        color: #1E3A5F;
        margin-bottom: 2rem;
        border-bottom: 3px solid #1E3A5F;
        padding-bottom: 0.5rem;
    }
    .section-header {
        font-size: 1.3rem;
        font-weight: 600;
        color: #2C5282;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }
    .stSuccess {
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Inicializar session state
def init_session_state():
    defaults = {
        "users_clients": {},      # {"Eric": ["CLIENT1", "CLIENT2"], "Arnau": [...]}
        "excel_master": None,     # DataFrame o dict de DataFrames por usuario
        "excel_master_bytes": None,
        "last_json_global_id": None,
        "last_load_json_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# ============ FUNCIONES AUXILIARES ============

def normalize_client_name(name):
    """Convierte nombre a MAYÚSCULAS y limpia espacios."""
    if pd.isna(name) or name == "":
        return ""
    return str(name).strip().upper()

def load_clients_from_json(file):
    """Carga diccionario de usuarios y clientes desde JSON."""
    try:
        data = json.load(file)
        if not isinstance(data, dict):
            return None, "El JSON debe ser un objeto con usuarios como claves."
        result = {}
        for user, clients in data.items():
            if isinstance(clients, list):
                result[user.strip()] = [normalize_client_name(c) for c in clients if c]
            else:
                result[user.strip()] = []
        return result, None
    except json.JSONDecodeError as e:
        return None, f"Error al leer JSON: {e}"

def save_clients_to_json(users_clients):
    """Genera bytes del JSON para descarga."""
    return json.dumps(users_clients, indent=2, ensure_ascii=False).encode("utf-8")

def extract_table_from_pdf(file):
    """Extrae tablas de un PDF usando pdfplumber."""
    tables = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables()
            if page_tables:
                for t in page_tables:
                    if t and len(t) > 1:
                        df = pd.DataFrame(t[1:], columns=t[0])
                        tables.append(df)
    if tables:
        return pd.concat(tables, ignore_index=True)
    return pd.DataFrame()

def extract_table_from_excel(file):
    """Extrae la primera hoja de un Excel."""
    return pd.read_excel(file, engine="openpyxl")

def process_billing_data(df, client_col, billing_col, date_col=None, selected_month=None):
    """
    Procesa datos y devuelve resumen por cliente y mes.
    Retorna: dict {mes: {cliente: suma}}
    """
    if df.empty or client_col not in df.columns or billing_col not in df.columns:
        return {}
    
    df = df.copy()
    df["_cliente"] = df[client_col].apply(normalize_client_name)
    
    # Convertir columna de facturación a numérico (soporta €, $, comas)
    billing_series = df[billing_col].astype(str).str.replace(r"[\$€\s]", "", regex=True).str.replace(",", ".")
    df["_billing"] = pd.to_numeric(billing_series, errors="coerce")
    df = df.dropna(subset=["_billing"])
    df = df[df["_cliente"] != ""]
    
    if df.empty:
        return {}
    
    result = {}
    
    if date_col and date_col in df.columns:
        try:
            df["_date"] = pd.to_datetime(df[date_col], errors="coerce")
            df = df.dropna(subset=["_date"])
            df["_mes"] = df["_date"].dt.to_period("M").astype(str)
            for mes, group in df.groupby("_mes"):
                result[mes] = group.groupby("_cliente")["_billing"].sum().to_dict()
        except Exception:
            mes = selected_month or datetime.now().strftime("%Y-%m")
            result[mes] = df.groupby("_cliente")["_billing"].sum().to_dict()
    else:
        mes = selected_month or datetime.now().strftime("%Y-%m")
        result[mes] = df.groupby("_cliente")["_billing"].sum().to_dict()
    
    return result

def filter_by_user_clients(billing_by_month, user_clients):
    """Filtra facturación solo por clientes del usuario."""
    filtered = {}
    client_set = set(c.upper() for c in user_clients)
    for mes, client_sums in billing_by_month.items():
        filtered[mes] = {c: v for c, v in client_sums.items() if c in client_set}
    return filtered

def merge_into_excel_master(current_master, new_data_by_user):
    """
    current_master: dict {user: DataFrame con Mes, Cliente, Facturación}
    new_data_by_user: dict {user: {mes: {cliente: suma}}}
    """
    for user, data in new_data_by_user.items():
        rows = []
        for mes, client_sums in data.items():
            for cliente, facturacion in client_sums.items():
                rows.append({"Mes": mes, "Cliente": cliente, "Facturación": facturacion})
        if rows:
            new_df = pd.DataFrame(rows)
            if user in current_master and not current_master[user].empty:
                combined = pd.concat([current_master[user], new_df], ignore_index=True)
                combined = combined.groupby(["Mes", "Cliente"])["Facturación"].sum().reset_index()
                current_master[user] = combined.sort_values(["Mes", "Cliente"])
            else:
                current_master[user] = new_df.sort_values(["Mes", "Cliente"])
    return current_master

def excel_master_to_bytes(master_data):
    """Convierte el Excel Maestro a bytes para descarga."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for user, df in master_data.items():
            sheet_name = user[:31]  # Excel limita nombres de hoja
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output.getvalue()

def normalize_excel_master_columns(df):
    """Normaliza columnas del Excel Maestro a Mes, Cliente, Facturación."""
    if df.empty:
        return pd.DataFrame(columns=["Mes", "Cliente", "Facturación"])
    cols = [c.strip() for c in df.columns]
    mapping = {}
    for i, c in enumerate(df.columns):
        cu = str(c).upper()
        if "MES" in cu or "MONTH" in cu:
            mapping[c] = "Mes"
        elif "CLIENTE" in cu or "CLIENT" in cu or "NOMBRE" in cu:
            mapping[c] = "Cliente"
        elif "FACTUR" in cu or "IMPORTE" in cu or "TOTAL" in cu or "BILLING" in cu:
            mapping[c] = "Facturación"
    if mapping:
        df = df.rename(columns=mapping)
    if "Mes" not in df.columns:
        df["Mes"] = ""
    if "Cliente" not in df.columns:
        df["Cliente"] = ""
    if "Facturación" not in df.columns:
        df["Facturación"] = 0
    return df[["Mes", "Cliente", "Facturación"]].copy()


def load_excel_master_from_file(file):
    """Carga Excel Maestro desde archivo. Retorna dict {sheet_name: DataFrame}."""
    xl = pd.ExcelFile(file, engine="openpyxl")
    result = {}
    for name in xl.sheet_names:
        df = pd.read_excel(file, sheet_name=name)
        result[name] = normalize_excel_master_columns(df)
    return result

# ============ SIDEBAR - INSTRUCCIONES ============

with st.sidebar:
    st.markdown("## 📋 Instrucciones")
    st.markdown("---")
    
    step = st.radio(
        "Selecciona el paso actual:",
        [
            "1️⃣ Gestión de Usuarios y Clientes",
            "2️⃣ Excel Maestro",
            "3️⃣ Cargar Datos (PDF/Excel)"
        ],
        index=0
    )
    
    st.markdown("---")
    
    if "1️⃣" in step:
        st.markdown("**Paso 1:** Gestiona usuarios y sus listas de clientes.")
        st.markdown("- Crea usuarios (ej: Eric, Arnau)")
        st.markdown("- Carga clientes desde JSON")
        st.markdown("- Añade manualmente en MAYÚSCULAS")
        st.markdown("- Actualiza o descarga el JSON")
    elif "2️⃣" in step:
        st.markdown("**Paso 2:** Carga o crea el Excel Maestro.")
        st.markdown("- Cada usuario tiene su hoja")
        st.markdown("- Usuarios nuevos se añaden automáticamente")
        st.markdown("- Descarga el Excel para guardar")
    elif "3️⃣" in step:
        st.markdown("**Paso 3:** Inserta PDF o Excel.")
        st.markdown("- Selecciona columnas de cliente y facturación")
        st.markdown("- Los datos se procesan por usuario")
        st.markdown("- El Excel Maestro se actualiza")
    
    st.markdown("---")
    if st.session_state["users_clients"]:
        st.markdown("**Usuarios activos:**")
        for u in st.session_state["users_clients"]:
            st.markdown(f"- {u} ({len(st.session_state['users_clients'][u])} clientes)")

# ============ MAIN CONTENT ============

st.markdown('<p class="main-header">📊 Ortegas Auto - Gestión de Facturación</p>', unsafe_allow_html=True)

# ---------- PARTE 1: GESTIÓN DE USUARIOS Y CLIENTES ----------
if "1️⃣" in step:
    st.markdown('<p class="section-header">1. Gestión de Usuarios y Clientes</p>', unsafe_allow_html=True)
    
    # Cargar JSON completo (múltiples usuarios) - útil para importar todo de una vez
    st.markdown("**Cargar JSON con usuarios y clientes (opcional)**")
    json_global = st.file_uploader("Archivo .json con estructura {usuario: [clientes]}", type=["json"], key="json_global")
    if json_global:
        file_id = f"{json_global.name}_{json_global.size}"
        if file_id != st.session_state.get("last_json_global_id"):
            with st.spinner("Cargando JSON..."):
                data, err = load_clients_from_json(json_global)
                if err:
                    st.error(err)
                else:
                    for u, c in data.items():
                        existing = st.session_state["users_clients"].get(u, [])
                        st.session_state["users_clients"][u] = list(set(existing + c))
                    st.session_state["last_json_global_id"] = file_id
                    st.success(f"Se han cargado {len(data)} usuario(s) con sus clientes.")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        new_user = st.text_input("Nuevo usuario", placeholder="Ej: Arnau")
        if st.button("➕ Añadir usuario") and new_user.strip():
            user = new_user.strip()
            if user not in st.session_state["users_clients"]:
                st.session_state["users_clients"][user] = []
                st.success(f"Usuario '{user}' creado correctamente.")
            else:
                st.warning(f"El usuario '{user}' ya existe.")
    
    if st.session_state["users_clients"]:
        st.markdown("---")
        selected_user = st.selectbox("Seleccionar usuario", list(st.session_state["users_clients"].keys()))
        
        if selected_user:
            clients = st.session_state["users_clients"][selected_user]
            
            # Opción 1: Cargar JSON
            st.markdown("**Cargar clientes desde JSON**")
            json_file = st.file_uploader("Archivo .json", type=["json"], key="load_json")
            replace_mode = st.checkbox("Reemplazar listas existentes (si no, se fusionan)", value=False, key="replace_json")
            if json_file:
                fid = f"load_{json_file.name}_{json_file.size}"
                if fid != st.session_state.get("last_load_json_id"):
                    with st.spinner("Cargando JSON..."):
                        data, err = load_clients_from_json(json_file)
                        if err:
                            st.error(err)
                        else:
                            for u, c in data.items():
                                if replace_mode and u in st.session_state["users_clients"]:
                                    st.session_state["users_clients"][u] = list(set(c))
                                else:
                                    existing = st.session_state["users_clients"].get(u, [])
                                    st.session_state["users_clients"][u] = list(set(existing + c))
                            st.session_state["last_load_json_id"] = fid
                            st.success(f"Clientes cargados para {len(data)} usuario(s).")
            
            # Opción 2 y 3: Añadir manual / Actualizar
            st.markdown("**Añadir cliente manualmente (MAYÚSCULAS)**")
            manual_client = st.text_input("Nombre del cliente", placeholder="Ej: RAZÓN SOCIAL POR LA QUE BUSCAR EN LAS FACTURAS").upper()
            if st.button("➕ Añadir a la lista") and manual_client:
                if manual_client not in st.session_state["users_clients"][selected_user]:
                    st.session_state["users_clients"][selected_user].append(manual_client)
                    st.session_state["users_clients"][selected_user].sort()
                    st.success(f"Cliente '{manual_client}' añadido.")
                else:
                    st.info("El cliente ya está en la lista.")
            
            st.markdown(f"**Clientes de {selected_user}:** {len(clients)}")
            if clients:
                st.write(", ".join(clients))
            
            # Eliminar usuario
            if st.button("🗑️ Eliminar usuario", type="secondary"):
                del st.session_state["users_clients"][selected_user]
                st.rerun()
        
        # Descargar JSON
        st.markdown("---")
        st.markdown("**Descargar lista de clientes (JSON)**")
        if st.button("📥 Generar y descargar JSON"):
            json_bytes = save_clients_to_json(st.session_state["users_clients"])
            st.download_button(
                "Descargar clientes.json",
                data=json_bytes,
                file_name="clientes.json",
                mime="application/json",
                key="dl_json"
            )

# ---------- PARTE 2: EXCEL MAESTRO ----------
elif "2️⃣" in step:
    st.markdown('<p class="section-header">2. Excel Maestro</p>', unsafe_allow_html=True)
    
    excel_file = st.file_uploader("Cargar Excel Maestro existente", type=["xlsx", "xls"], key="upload_excel_master")
    
    if excel_file:
        with st.spinner("Cargando Excel Maestro..."):
            try:
                master = load_excel_master_from_file(excel_file)
                st.session_state["excel_master"] = master
                st.success("Excel Maestro cargado correctamente.")
            except Exception as e:
                st.error(f"Error al cargar: {e}")
    
    # Crear Excel Maestro vacío o añadir páginas para usuarios nuevos
    if st.session_state["users_clients"]:
        if st.button("🔄 Inicializar/Actualizar Excel Maestro"):
            with st.spinner("Procesando..."):
                master = st.session_state.get("excel_master") or {}
                for user in st.session_state["users_clients"]:
                    if user not in master:
                        master[user] = pd.DataFrame(columns=["Mes", "Cliente", "Facturación"])
                st.session_state["excel_master"] = master
                st.success("Excel Maestro actualizado con todos los usuarios.")
    
    if st.session_state.get("excel_master"):
        st.markdown("**Hojas del Excel Maestro:**")
        for name, df in st.session_state["excel_master"].items():
            st.write(f"- **{name}**: {len(df)} registros")
        
        # Descargar
        st.markdown("---")
        excel_bytes = excel_master_to_bytes(st.session_state["excel_master"])
        st.download_button(
            "📥 Descargar Excel Maestro",
            data=excel_bytes,
            file_name=f"excel_maestro_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_excel"
        )

# ---------- PARTE 3: CARGAR DATOS (PDF/EXCEL) ----------
elif "3️⃣" in step:
    st.markdown('<p class="section-header">3. Cargar Datos (PDF o Excel)</p>', unsafe_allow_html=True)
    
    if not st.session_state["users_clients"]:
        st.warning("Primero añade al menos un usuario y sus clientes en el Paso 1.")
    elif not st.session_state.get("excel_master"):
        st.warning("Carga o inicializa el Excel Maestro en el Paso 2.")
    else:
        data_file = st.file_uploader("Archivo PDF o Excel", type=["pdf", "xlsx", "xls"], key="data_file")
        
        if data_file:
            with st.spinner("Extrayendo datos..."):
                if data_file.name.lower().endswith(".pdf"):
                    df = extract_table_from_pdf(data_file)
                else:
                    df = extract_table_from_excel(data_file)
            
            if df.empty:
                st.error("No se encontraron tablas en el archivo.")
            else:
                st.write("**Vista previa de columnas:**")
                st.dataframe(df.head(10), use_container_width=True)
                
                col_client = st.selectbox("Columna de nombres de clientes", df.columns.tolist())
                col_billing = st.selectbox("Columna de facturación/importe", df.columns.tolist())
                col_date = st.selectbox("Columna de fecha (opcional, para agrupar por mes)", ["-- No usar --"] + df.columns.tolist())
                col_date = None if col_date == "-- No usar --" else col_date
                
                if not col_date:
                    mes_manual = st.text_input("Mes manual (formato YYYY-MM)", value=datetime.now().strftime("%Y-%m"))
                else:
                    mes_manual = None
                
                if st.button("Procesar y actualizar Excel Maestro"):
                    with st.spinner("Procesando facturación por usuario..."):
                        billing_data = process_billing_data(df, col_client, col_billing, col_date, mes_manual)
                        
                        new_data_by_user = {}
                        for user, clients in st.session_state["users_clients"].items():
                            filtered = filter_by_user_clients(billing_data, clients)
                            if any(filtered.values()):
                                new_data_by_user[user] = filtered
                        
                        if new_data_by_user:
                            st.session_state["excel_master"] = merge_into_excel_master(
                                st.session_state["excel_master"], new_data_by_user
                            )
                            st.success("Datos procesados y Excel Maestro actualizado.")
                            
                            for user, data in new_data_by_user.items():
                                with st.expander(f"Resumen {user}"):
                                    for mes, sums in data.items():
                                        st.write(f"**{mes}:**")
                                        st.write(pd.DataFrame(list(sums.items()), columns=["Cliente", "Facturación"]))
                        else:
                            st.info("No se encontraron coincidencias con los clientes de los usuarios.")
