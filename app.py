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

# --- CONEXIÓN A LA BASE DE DATABASE ---
@st.cache_resource
def get_connection():
    turso_url = st.secrets.get("TURSO_DATABASE_URL", os.getenv("TURSO_DATABASE_URL"))
    turso_token = st.secrets.get("TURSO_AUTH_TOKEN", os.getenv("TURSO_AUTH_TOKEN"))
    
    try:
        if turso_url and turso_token:
            import libsql
            return libsql.connect(database=turso_url, auth_token=turso_token)
        else:
            return sqlite3.connect("horas_local.db", check_same_thread=False)
    except Exception as e:
        st.error(f"Error crítico al conectar con la base de datos: {e}")
        st.stop()

conn = get_connection()

# --- EJECUCIÓN SQL CON CAPTURA DE ERROR REAL ---
def ejecutar_sql(query, params=(), fetch_one=False, fetch_all=False, commit=False):
    try:
        cursor = conn.cursor()
        res = cursor.execute(query, params) if params else cursor.execute(query)
        if commit:
            try:
                conn.commit()
            except Exception:
                pass
        if fetch_one:
            return res.fetchone()
        if fetch_all:
            return res.fetchall()
        return res
    except Exception as e:
        st.error(f"⚠️ **Fallo SQL en la consulta:** `{query}`\n\n**Parámetros:** `{params}`\n\n**Error exacto:** `{e}`")
        st.stop()

# --- INICIALIZACIÓN DE TABLAS ---
def init_db():
    ejecutar_sql("CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL)", commit=True)
    ejecutar_sql("CREATE TABLE IF NOT EXISTS registros_detalle (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER NOT NULL, fecha TEXT NOT NULL, t1_entrada TEXT, t1_salida_real TEXT, t1_salida_oficial TEXT, has_t2 INTEGER DEFAULT 0, t2_entrada TEXT, t2_salida_real TEXT, t2_salida_oficial TEXT, notas TEXT, UNIQUE(usuario_id, fecha))", commit=True)

init_db()

# --- CONSULTAS OPTIMIZADAS CON CACHÉ DE DATOS ---
@st.cache_data(ttl=300)
def cargar_registros_mes(usuario_id, month_prefix):
    query = "SELECT fecha, t1_entrada, t1_salida_real, t1_salida_oficial, has_t2, t2_entrada, t2_salida_real, t2_salida_oficial, notas FROM registros_detalle WHERE usuario_id = ? AND fecha LIKE ? ORDER BY fecha ASC"
    return ejecutar_sql(query, (usuario_id, f"{month_prefix}-%"), fetch_all=True)

@st.cache_data(ttl=300)
def cargar_dia_especifico(usuario_id, f_sel_str):
    query = "SELECT t1_entrada, t1_salida_real, t1_salida_oficial, has_t2, t2_entrada, t2_salida_real, t2_salida_oficial, notas FROM registros_detalle WHERE usuario_id = ? AND fecha = ?"
    return ejecutar_sql(query, (usuario_id, f_sel_str), fetch_one=True)

# --- FUNCIONES DE CÁLCULO DE TIEMPO ---
def calcular_duracion_minutos(e_str, s_str):
    if not e_str or not s_str:
        return 0
    try:
        h1, m1 = map(int, e_str.strip().split(":"))
        h2, m2 = map(int, s_str.strip().split(":"))
        t1 = h1 * 60 + m1
        t2 = h2 * 60 + m2
        if t2 < t1:
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
    res = ejecutar_sql("SELECT COUNT(*) FROM usuarios", fetch_one=True)
    return res[0] if res else 0

def registrar_usuario(username, password):
    if contar_usuarios() >= 2:
        return False, "Límite máximo de 2 usuarios alcanzado."
    try:
        ejecutar_sql("INSERT INTO usuarios (username, password) VALUES (?, ?)", (username, hash_password(password)), commit=True)
        st.cache_data.clear()
        return True, "Usuario registrado con éxito."
    except Exception as e:
        return False, f"Error al registrar: {e}"

def verificar_login(username, password):
    return ejecutar_sql("SELECT id, username FROM usuarios WHERE username = ? AND password = ?", (username, hash_password(password)), fetch_one=True)

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
    # --- BARRA SUPERIOR DE CONTRATO Y LOGOUT ---
    col_user, col_logout = st.columns([4, 1])
    col_user.write(f"👤 **Usuario en sesión:** {st.session_state.user['username']}")
    if col_logout.button("Cerrar Sesión"):
        st.session_state.user = None
        st.rerun()

    st.write("---")

    # 1. SELECTOR DE CONTRATO
    tipo_contrato = st.radio(
        "📝 **Selector de Contrato:**",
        ["Contrato 25h/sem (~100h/mes)", "Contrato 30h/sem (~120h/mes)"],
        horizontal=True
    )
    horas_objetivo_mes = 100.0 if "25h" in tipo_contrato else 120.0

    st.write("")

    # 2. CALENDARIO DE TRABAJO
    st.subheader("📅 Calendario de Trabajo")
    
    # Navegación del mes
    col_prev, col_title, col_next = st.columns([1, 2, 1])
    if col_prev.button("◀ Mes Anterior", use_container_width=True):
        if st.session_state.current_month == 1:
            st.session_state.current_month = 12
            st.session_state.current_year -= 1
        else:
            st.session_state.current_month -= 1
        st.rerun()

    col_title.markdown(f"<h3 style='text-align: center; margin:0;'>{MESES[st.session_state.current_month - 1]} {st.session_state.current_year}</h3>", unsafe_allow_html=True)

    if col_next.button("Mes Siguiente ▶", use_container_width=True):
        if st.session_state.current_month == 12:
            st.session_state.current_month = 1
            st.session_state.current_year += 1
        else:
            st.session_state.current_month += 1
        st.rerun()

    # Obtener registros del mes actual usando la caché
    month_prefix = f"{st.session_state.current_year:04d}-{st.session_state.current_month:02d}"
    todos_registros_mes = cargar_registros_mes(st.session_state.user["id"], month_prefix)

    minutos_map = {}
    for row in todos_registros_mes:
        f_str, t1_e, t1_sr, t1_so, has2, t2_e, t2_sr, t2_so, nts = row
        m1 = calcular_duracion_minutos(t1_e, t1_sr)
        m2 = calcular_duracion_minutos(t2_e, t2_sr) if has2 else 0
        tot = m1 + m2
        if tot > 0:
            minutos_map[f_str] = tot

    # Renderizar rejilla del calendario
    cal = calendar.monthcalendar(st.session_state.current_year, st.session_state.current_month)
    headers = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    
    cols_h = st.columns(7)
    for idx, h in enumerate(headers):
        cols_h[idx].markdown(f"**{h}**")

    for week in cal:
        cols_w = st.columns(7)
        for day_idx, d in enumerate(week):
            if d == 0:
                cols_w[day_idx].write("")
            else:
                d_obj = datetime.date(st.session_state.current_year, st.session_state.current_month, d)
                f_str = d_obj.strftime("%Y-%m-%d")
                tot_m = minutos_map.get(f_str, 0)
                
                label_m = f"({minutos_a_str(tot_m)})" if tot_m > 0 else ""
                btn_label = f"{d}\n{label_m}" if label_m else f"{d}"
                
                is_selected = (st.session_state.selected_date == d_obj)
                btn_type = "primary" if is_selected else "secondary"

                if cols_w[day_idx].button(btn_label, key=f"cal_day_{f_str}", type=btn_type, use_container_width=True):
                    st.session_state.selected_date = d_obj
                    st.rerun()

    st.write("---")

    # 3. REGISTRO DEL DÍA SELECCIONADO
    st.subheader("📝 Registro del Día Seleccionado")
    
    sel_date = st.session_state.selected_date
    f_sel_str = sel_date.strftime("%Y-%m-%d")
    nombres_dias_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    nombre_dia_sel = nombres_dias_es[sel_date.weekday()]
    fecha_formateada = sel_date.strftime("%d/%m/%Y")

    st.markdown(f"<h4 style='color: #0044cc;'>Día Seleccionado: {nombre_dia_sel} {fecha_formateada}</h4>", unsafe_allow_html=True)

    # Cargar datos guardados del día usando la función en caché
    rec_guardado = cargar_dia_especifico(st.session_state.user["id"], f_sel_str)

    # Manejo de estado del formulario
    if "form_loaded_date" not in st.session_state or st.session_state.form_loaded_date != f_sel_str:
        st.session_state.form_loaded_date = f_sel_str
        if rec_guardado:
            st.session_state.val_t1_e = rec_guardado[0] or ""
            st.session_state.val_t1_sr = rec_guardado[1] or ""
            st.session_state.val_t1_so = rec_guardado[2] or ""
            st.session_state.val_has_t2 = bool(rec_guardado[3])
            st.session_state.val_t2_e = rec_guardado[4] or ""
            st.session_state.val_t2_sr = rec_guardado[5] or ""
            st.session_state.val_t2_so = rec_guardado[6] or ""
            st.session_state.val_notas = rec_guardado[7] or ""
        else:
            st.session_state.val_t1_e = ""
            st.session_state.val_t1_sr = ""
            st.session_state.val_t1_so = ""
            st.session_state.val_has_t2 = False
            st.session_state.val_t2_e = ""
            st.session_state.val_t2_sr = ""
            st.session_state.val_t2_so = ""
            st.session_state.val_notas = ""

    st.write("**TURNO 1 (Mañana / Principal):**")
    col_t1a, col_t1b, col_t1c = st.columns(3)
    val_t1_e = col_t1a.text_input("Entrada:", value=st.session_state.val_t1_e, key="in_t1_e")
    val_t1_sr = col_t1b.text_input("Salida Real:", value=st.session_state.val_t1_sr, key="in_t1_sr")
    val_t1_so = col_t1c.text_input("Salida Oficial:", value=st.session_state.val_t1_so, key="in_t1_so")

    val_has_t2 = st.checkbox("Activar TURNO 2 (Tarde / Noche - Doble Turno)", value=st.session_state.val_has_t2, key="in_has_t2")

    val_t2_e, val_t2_sr, val_t2_so = "", "", ""
    if val_has_t2:
        col_t2a, col_t2b, col_t2c = st.columns(3)
        val_t2_e = col_t2a.text_input("Entrada (Turno 2):", value=st.session_state.val_t2_e, key="in_t2_e")
        val_t2_sr = col_t2b.text_input("Salida Real (Turno 2):", value=st.session_state.val_t2_sr, key="in_t2_sr")
        val_t2_so = col_t2c.text_input("Salida Oficial (Turno 2):", value=st.session_state.val_t2_so, key="in_t2_so")

    val_notas = st.text_input("Notas / Incidencias:", value=st.session_state.val_notas, key="in_notas")

    # Botones de Acción
    col_act1, col_act2, col_act3 = st.columns(3)

    if col_act1.button("📋 Cargar Horario Habitual", use_container_width=True):
        dow = sel_date.weekday()
        if dow in [1, 2, 3]:  # Martes, Miércoles, Jueves
            st.session_state.val_t1_e = "19:00"
            st.session_state.val_t1_sr = "23:00"
            st.session_state.val_t1_so = "23:00"
            st.session_state.val_has_t2 = False
            st.session_state.val_t2_e = ""
            st.session_state.val_t2_sr = ""
            st.session_state.val_t2_so = ""
        elif dow == 4:  # Viernes
            st.session_state.val_t1_e = "12:00"
            st.session_state.val_t1_sr = "16:00"
            st.session_state.val_t1_so = "16:00"
            st.session_state.val_has_t2 = True
            st.session_state.val_t2_e = "20:00"
            st.session_state.val_t2_sr = "23:40"
            st.session_state.val_t2_so = "23:00"
        elif dow == 5:  # Sábado
            st.session_state.val_t1_e = "13:00"
            st.session_state.val_t1_sr = "16:00"
            st.session_state.val_t1_so = "16:00"
            st.session_state.val_has_t2 = True
            st.session_state.val_t2_e = "20:00"
            st.session_state.val_t2_sr = "23:00"
            st.session_state.val_t2_so = "23:00"
        elif dow == 6:  # Domingo
            st.session_state.val_t1_e = "13:00"
            st.session_state.val_t1_sr = "16:00"
            st.session_state.val_t1_so = "16:00"
            st.session_state.val_has_t2 = False
            st.session_state.val_t2_e = ""
            st.session_state.val_t2_sr = ""
            st.session_state.val_t2_so = ""
        else:  # Lunes
            st.session_state.val_t1_e = ""
            st.session_state.val_t1_sr = ""
            st.session_state.val_t1_so = ""
            st.session_state.val_has_t2 = False
            st.session_state.val_t2_e = ""
            st.session_state.val_t2_sr = ""
            st.session_state.val_t2_so = ""
        st.rerun()

    if col_act2.button("💾 Guardar / Actualizar Día", type="primary", use_container_width=True):
        query_save = "INSERT OR REPLACE INTO registros_detalle (usuario_id, fecha, t1_entrada, t1_salida_real, t1_salida_oficial, has_t2, t2_entrada, t2_salida_real, t2_salida_oficial, notas) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ejecutar_sql(query_save, (
            st.session_state.user["id"], f_sel_str,
            val_t1_e, val_t1_sr, val_t1_so,
            1 if val_has_t2 else 0,
            val_t2_e, val_t2_sr, val_t2_so,
            val_notas
        ), commit=True)
        st.cache_data.clear()
        st.session_state.val_t1_e = val_t1_e
        st.session_state.val_t1_sr = val_t1_sr
        st.session_state.val_t1_so = val_t1_so
        st.session_state.val_has_t2 = val_has_t2
        st.session_state.val_t2_e = val_t2_e
        st.session_state.val_t2_sr = val_t2_sr
        st.session_state.val_t2_so = val_t2_so
        st.session_state.val_notas = val_notas
        st.success("¡Registro guardado correctamente!")
        st.rerun()

    if col_act3.button("🗑️ Borrar Día", use_container_width=True):
        ejecutar_sql("DELETE FROM registros_detalle WHERE usuario_id = ? AND fecha = ?", (st.session_state.user["id"], f_sel_str), commit=True)
        st.cache_data.clear()
        st.session_state.val_t1_e = ""
        st.session_state.val_t1_sr = ""
        st.session_state.val_t1_so = ""
        st.session_state.val_has_t2 = False
        st.session_state.val_t2_e = ""
        st.session_state.val_t2_sr = ""
        st.session_state.val_t2_so = ""
        st.session_state.val_notas = ""
        st.success("Día eliminado.")
        st.rerun()

    st.write("---")

    # 4. RESUMEN DE HORAS Y EXPORTACIÓN
    st.subheader("📊 Resumen de Horas y Exportación")

    col_exp1, col_exp2 = st.columns(2)
    calc_pressed = col_exp1.button("📊 CALCULAR HORAS MES", use_container_width=True)

    export_data = []
    tot_m_real_mes = 0
    tot_m_oficial_mes = 0

    for r in todos_registros_mes:
        f_s, t1e, t1sr, t1so, h2, t2e, t2sr, t2so, nts = r
        m1_r = calcular_duracion_minutos(t1e, t1sr)
        m1_o = calcular_duracion_minutos(t1e, t1so)
        m2_r = calcular_duracion_minutos(t2e, t2sr) if h2 else 0
        m2_o = calcular_duracion_minutos(t2e, t2so) if h2 else 0
        
        dr = m1_r + m2_r
        do = m1_o + m2_o
        tot_m_real_mes += dr
        tot_m_oficial_mes += do
        
        export_data.append({
            "Fecha": f_s,
            "T1 Entrada": t1e,
            "T1 Salida Real": t1sr,
            "T1 Salida Oficial": t1so,
            "T2 Entrada": t2e if h2 else "",
            "T2 Salida Real": t2sr if h2 else "",
            "T2 Salida Oficial": t2so if h2 else "",
            "Horas Reales": minutos_a_str(dr),
            "Horas Oficiales": minutos_a_str(do),
            "Notas": nts
        })

    df_excel = pd.DataFrame(export_data)
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df_excel.to_excel(writer, index=False, sheet_name=f"{MESES[st.session_state.current_month - 1]} {st.session_state.current_year}")

    col_exp2.download_button(
        label="📄 EXPORTAR MES A EXCEL (.xlsx)",
        data=excel_buffer.getvalue(),
        file_name=f"Control_Horas_{MESES[st.session_state.current_month - 1]}_{st.session_state.current_year}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    # Mostrar cálculo de horas en pantalla
    horas_reales_h = tot_m_real_mes / 60.0
    horas_oficiales_h = tot_m_oficial_mes / 60.0
    diferencia_h = horas_reales_h - horas_oficiales_h
    balance_contrato_h = horas_reales_h - horas_objetivo_mes

    nombre_mes_actual = MESES[st.session_state.current_month - 1].upper()
    anio_actual = st.session_state.current_year
    str_horas_reales = minutos_a_str(tot_m_real_mes)
    str_horas_oficiales = minutos_a_str(tot_m_oficial_mes)

    lineas_informe = [
        "--- INFORME DE " + str(nombre_mes_actual) + " " + str(anio_actual) + " ---",
        "• Jornada Seleccionada: " + str(tipo_contrato),
        "• Total Horas Reales Trabajadas: " + str(str_horas_reales) + " (" + f"{horas_reales_h:.2f}" + " h)",
        "• Total Horas Oficiales: " + str(str_horas_oficiales) + " (" + f"{horas_oficiales_h:.2f}" + " h)",
        "• Horas Extra / Exceso de Salida: " + f"{diferencia_h:+.2f}" + " h",
        "• Balance respecto al Contrato (" + f"{horas_objetivo_mes:.0f}" + "h): " + f"{balance_contrato_h:+.2f}" + " h"
    ]
    informe_texto = "\n".join(lineas_informe)

    st.text_area("Informe del Mes:", value=informe_texto, height=140)
