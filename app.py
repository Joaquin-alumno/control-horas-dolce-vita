import os
import sqlite3
import hashlib
import pandas as pd
import streamlit as st

# Configuración de la página
st.set_page_config(page_title="Control de Horas - La Dolce Vita", page_icon="⏱️", layout="centered")

# --- CONEXIÓN A LA BASE DE DATOS ---
def get_connection():
    # Intenta conectar a Turso (Producción) o SQLite Local (Desarrollo)
    turso_url = st.secrets.get("TURSO_DATABASE_URL", os.getenv("TURSO_DATABASE_URL"))
    turso_token = st.secrets.get("TURSO_AUTH_TOKEN", os.getenv("TURSO_AUTH_TOKEN"))
    
    if turso_url and turso_token:
        import libsql_experimental as libsql
        return libsql.connect(database=turso_url, auth_token=turso_token)
    else:
        return sqlite3.connect("horas_local.db", check_same_thread=False)

conn = get_connection()

# --- CREACIÓN DE TABLAS ---
def init_db():
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            fecha DATE NOT NULL,
            horas_ordinarias REAL NOT NULL,
            horas_extra REAL NOT NULL,
            notas TEXT,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    """)
    conn.commit()

init_db()

# --- FUNCIONES DE AUTENTICACIÓN ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def contar_usuarios():
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    res = cursor.fetchone()
    return res[0] if res else 0

def registrar_usuario(username, password):
    if contar_usuarios() >= 2:
        return False, "Límite máximo de 2 usuarios alcanzado."
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO usuarios (username, password) VALUES (?, ?)", (username, hash_password(password)))
        conn.commit()
        return True, "Usuario registrado con éxito."
    except Exception as e:
        return False, "El nombre de usuario ya existe o hubo un error."

def verificar_login(username, password):
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM usuarios WHERE username = ? AND password = ?", (username, hash_password(password)))
    return cursor.fetchone()

# --- FUNCIONES DE REGISTROS ---
def agregar_registro(usuario_id, fecha, h_ord, h_ext, notas):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO registros (usuario_id, fecha, horas_ordinarias, horas_extra, notas)
        VALUES (?, ?, ?, ?, ?)
    """, (usuario_id, str(fecha), h_ord, h_ext, notas))
    conn.commit()

def obtener_registros(usuario_id):
    query = "SELECT id, fecha, horas_ordinarias, horas_extra, notas FROM registros WHERE usuario_id = ? ORDER BY fecha DESC"
    return pd.read_sql_query(query, conn, params=(usuario_id,))

def eliminar_registro(registro_id, usuario_id):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registros WHERE id = ? AND usuario_id = ?", (registro_id, usuario_id))
    conn.commit()

# --- GESTIÓN DE SESIÓN ---
if "user" not in st.session_state:
    st.session_state.user = None

# --- INTERFAZ DE USUARIO ---
st.title("⏱️ Control de Horas - La Dolce Vita")

if st.session_state.user is None:
    tab1, tab2 = st.tabs(["🔐 Iniciar Sesión", "📝 Crear Cuenta"])
    
    with tab1:
        st.subheader("Acceso")
        user_input = st.text_input("Usuario")
        pass_input = st.text_input("Contraseña", type="password")
        if st.button("Entrar", type="primary"):
            res = verificar_login(user_input, pass_input)
            if res:
                st.session_state.user = {"id": res[0], "username": res[1]}
                st.success(f"Bienvenido, {res[1]}")
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
                
    with tab2:
        st.subheader("Registro (Máximo 2 personas)")
        if contar_usuarios() >= 2:
            st.warning("⚠️ Ya se han registrado los 2 usuarios autorizados.")
        else:
            new_user = st.text_input("Nuevo Usuario")
            new_pass = st.text_input("Nueva Contraseña", type="password")
            if st.button("Registrar"):
                if new_user and new_pass:
                    ok, msg = registrar_usuario(new_user, new_pass)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.warning("Rellena todos los campos.")
else:
    # Panel de Usuario Autenticado
    st.sidebar.write(f"👤 **Usuario:** {st.session_state.user['username']}")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.user = None
        st.rerun()
        
    st.header("Añadir Turno / Día")
    with st.form("form_horas", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            fecha = st.date_input("Fecha")
            h_ord = st.number_input("Horas Ordinarias", min_value=0.0, max_value=24.0, step=0.5, value=8.0)
        with col2:
            h_ext = st.number_input("Horas Extra", min_value=0.0, max_value=24.0, step=0.5, value=0.0)
            notas = st.text_input("Notas / Observaciones")
            
        submitted = st.form_submit_button("Guardar Día")
        if submitted:
            agregar_registro(st.session_state.user["id"], fecha, h_ord, h_ext, notas)
            st.success("¡Registro guardado correctamente!")
            st.rerun()
            
    st.divider()
    
    st.header("📋 Tus Registros")
    df = obtener_registros(st.session_state.user["id"])
    
    if not df.empty:
        # Resumen métrico
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Total Días", len(df))
        col_m2.metric("Total Horas Ord.", f"{df['horas_ordinarias'].sum():.1f} h")
        col_m3.metric("Total Horas Extra", f"{df['horas_extra'].sum():.1f} h")
        
        st.dataframe(df[["fecha", "horas_ordinarias", "horas_extra", "notas"]], use_container_width=True)
        
        # --- SECCIÓN DE BORRADO DE DÍAS ---
        st.subheader("🗑️ Borrar un Día")
        # Crear opciones legibles para el desplegable (Fecha e ID)
        opciones_borrado = {f"Fecha: {row['fecha']} | Ord: {row['horas_ordinarias']}h, Ext: {row['horas_extra']}h": row['id'] for _, row in df.iterrows()}
        
        eleccion = st.selectbox("Selecciona el día que deseas eliminar:", list(opciones_borrado.keys()))
        
        if st.button("Eliminar Registro Seleccionado", type="secondary"):
            registro_id = opciones_borrado[eleccion]
            eliminar_registro(registro_id, st.session_state.user["id"])
            st.success("Registro eliminado correctamente.")
            st.rerun()
    else:
        st.info("Aún no tienes horas registradas.")
