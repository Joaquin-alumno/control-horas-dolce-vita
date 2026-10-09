import os
import sqlite3
import hashlib
import datetime
import calendar
import io
import pandas as pd
import streamlit as st

# Configuración de la página
st.set_page_config(page_title="Control de Horas Laborales - La Dolce Vita", page_icon="⏱️", layout="wide")

MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

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

# --- TABLA DETALLADA ---
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
        CREATE TABLE IF NOT EXISTS registros_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            t1_entrada TEXT,
            t1_salida_real TEXT,
            t1_salida_oficial TEXT,
            has_t2 INTEGER DEFAULT 0,
            t2_entrada TEXT,
            t2_salida_real TEXT,
            t2_salida_oficial TEXT,
            notas TEXT,
            UNIQUE(usuario_id, fecha)
        )
    """)
    conn.commit()

init_db()

# --- FUNCIONES DE CÁLCULO DE TIEMPO ---
def calcular_duracion_minutos(e_str, s_str):
    if not e_str or not s_str:
        return 0
    try:
        h1, m1 = map(int, e_str.strip().split(":"))
        h2, m2 = map(int, s_str.strip().split(":"))
        t1 = h1 * 60 + m1
        t2 = h2 * 60 + m2
        if t2 < t1:  # Manejo de paso por medianoche
            t2 += 24 * 60
        return max(0, t2 - t1)
    except Exception:
        return 0

def minutos_a_str(minutos):
    if minutos <= 0:
        return ""
    h = minutos // 60
    m = minutos % 60
    return f"{h}h {m:02d}m"

# --- AUTENTICACIÓN ---
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

# --- CONTROL DE SESIÓN ---
if "user" not in st.session_state:
    st.session_state.user = None

if "current_year" not in st.session_state:
    st.session_state.current_year = datetime.date.today().year
if "current_month" not in st.session_state:
    st.session_state.current_month = datetime.date.today().month
if "selected_date" not in st.session_state:
    st.session_state.selected_date = datetime.date.today()

# --- INTERFAZ DE USUARIO ---
st.title("Control de Horas Laborales")

if st.session_state.user is None:
    tab1, tab2 = st.tabs(["🔐 Iniciar Sesión", "📝 Crear Cuenta"])
    with tab1:
        st.subheader("Acceso")
        user_input = st.text_input("Usuario")
        pass_input = st.text_input("
