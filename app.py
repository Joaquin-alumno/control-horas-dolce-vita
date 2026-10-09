import os
import sqlite3
import hashlib
import pandas as pd
import streamlit as st

# Configuración de la página
st.set_page_config(page_title="Control de Horas - La Dolce Vita", page_icon="⏱️", layout="centered")

# --- CONEXIÓN A LA BASE DE DATOS ---
def get_connection():
    turso_url = st.secrets.get("TURSO_DATABASE_URL", os.getenv("TURSO_DATABASE_URL"))
    turso_token = st.secrets.get("TURSO_AUTH_TOKEN", os.getenv("TURSO_AUTH_TOKEN"))
    
    if turso_url and turso_token:
        import libsql
        return libsql.connect(database=turso_url, auth_token=turso_token)
    else:
        return sqlite3.connect("horas_local.db", check_same_thread=False)

conn = get_connection()

# --- CREACIÓN Y MIGRACIÓN DE TABLAS ---
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
            tipo_turno TEXT DEFAULT 'Tarde / Noche 🌙',
            horas_ordinarias REAL NOT NULL,
            horas_extra REAL NOT NULL,
            notas TEXT,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    """)
    conn.commit()
    
    # Intentar añadir la columna tipo_turno por si proviene de una versión anterior
    try:
        cursor.execute("ALTER TABLE registros ADD COLUMN tipo_turno TEXT DEFAULT 'Tarde / Noche 🌙'")
        conn.commit()
    except Exception:
        pass

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
    except Exception:
        return False, "El nombre de usuario ya existe o hubo un error."

def verificar_login(username, password):
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM usuarios WHERE username = ? AND password = ?", (username, hash_password(password)))
    return cursor.fetchone()

# --- FUNCIONES DE REGISTROS ---
def agregar_registro(usuario_id, fecha, tipo_turno, h_ord, h_ext, notas):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO registros (usuario_id, fecha, tipo_turno, horas_ordinarias, horas_extra, notas)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (usuario_id, str(fecha), tipo_turno, h_ord, h_ext, notas))
    conn.commit()

def obtener_registros(usuario_id):
    query = "SELECT id, fecha, tipo_turno, horas_ordinarias, horas_extra, notas FROM registros WHERE usuario_id = ? ORDER BY fecha DESC"
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
    # --- BARRA LATERAL (CONFIGURACIÓN DE CONTRATO Y USUARIO) ---
    st.sidebar.write(f"👤 **Usuario:** {st.session_state.user['username']}")
    
    st.sidebar.divider()
    st.sidebar.subheader("📄 Tipo de Contrato")
    tipo_contrato = st.sidebar.radio(
        "Selecciona tu jornada contratada:",
        ["Contrato 25h / semana 📜", "Contrato 30h / semana 📜"]
    )
    
    horas_contrato_semanal = 25.0 if "25h" in tipo_contrato else 30.0
    
    st.sidebar.divider()
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.user = None
        st.rerun()
        
    # --- FORMULARIO PARA REGISTRAR DÍAS ---
    st.header("Añadir Turno / Día")
    with st.form("form_horas", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            fecha = st.date_input("Fecha")
            tipo_turno = st.selectbox(
                "Tipo de Turno",
                [
                    "Tarde / Noche 🌙",
                    "Comida / Mediodía ☀️",
                    "Turno Partido 🔄",
                    "Día Libre 🏖️",
                    "Otro ⏱️"
                ]
            )
            val_ord_def = 0.0 if tipo_turno == "Día Libre 🏖️" else (5.0 if horas_contrato_semanal == 25.0 else 6.0)
            h_ord = st.number_input("Horas Ordinarias", min_value=0.0, max_value=24.0, step=0.5, value=val_ord_def)
            
        with col2:
            h_ext = st.number_input("Horas Extra", min_value=0.0, max_value=24.0, step=0.5, value=0.0)
            notas = st.text_input("Notas / Observaciones", placeholder="Ej: Cierre de caja, refuerzo...")
            
        submitted = st.form_submit_button("Guardar Día", type="primary")
        if submitted:
            horas_finales_ord = 0.0 if tipo_turno == "Día Libre 🏖️" else h_ord
            agregar_registro(st.session_state.user["id"], fecha, tipo_turno, horas_finales_ord, h_ext, notas)
            st.success("¡Turno guardado correctamente!")
            st.rerun()
            
    st.divider()
    
    # --- TABLA Y RESUMEN MÉTRICO ---
    st.header("📋 Tus Registros")
    df = obtener_registros(st.session_state.user["id"])
    
    if not df.empty:
        total_ord = df['horas_ordinarias'].sum()
        total_ext = df['horas_extra'].sum()
        dias_trabajados = len(df[df['tipo_turno'] != 'Día Libre 🏖️'])
        
        # Métricas de resumen
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Días Trabajados", dias_trabajados)
        col_m2.metric("Total Horas Ord.", f"{total_ord:.1f} h")
        col_m3.metric("Total Horas Extra", f"{total_ext:.1f} h")
        
        st.caption(f"📌 **Jornada activa:** {tipo_contrato}")
        
        # Tabla detallada
        st.dataframe(
            df[["fecha", "tipo_turno", "horas_ordinarias", "horas_extra", "notas"]],
            column_config={
                "fecha": "Fecha",
                "tipo_turno": "Turno / Tipo",
                "horas_ordinarias": "Horas Ord.",
                "horas_extra": "Horas Extra",
                "notas": "Notas"
            },
            use_container_width=True
        )
        
        # --- SECCIÓN DE BORRADO DE DÍAS ---
        st.subheader("🗑️ Borrar un Día")
        opciones_borrado = {
            f"📅 {row['fecha']} | {row['tipo_turno']} | {row['horas_ordinarias']}h ord.": row['id']
            for _, row in df.iterrows()
        }
        
        eleccion = st.selectbox("Selecciona el registro que deseas eliminar:", list(opciones_borrado.keys()))
        
        if st.button("Eliminar Registro Seleccionado", type="secondary"):
            registro_id = opciones_borrado[eleccion]
            eliminar_registro(registro_id, st.session_state.user["id"])
            st.success("Registro eliminado correctamente.")
            st.rerun()
    else:
        st.info("Aún no tienes horas registradas.")
