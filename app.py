import streamlit as st
import sqlite3
import hashlib
import datetime
import pandas as pd
import io

# Intentar cargar la librería de Turso si está instalada
try:
    import libsql_experimental as libsql
    HAS_LIBSQL = True
except ImportError:
    HAS_LIBSQL = False

# ==========================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Control de Horas Laborales - La Dolce Vita",
    page_icon="🍕",
    layout="wide"
)

# ==========================================
# 2. CONEXIÓN INTELIGENTE Y BASE DE DATOS
# ==========================================
def get_db():
    """Conecta a Turso en la nube si existen los secretos, o a SQLite local si no."""
    if "TURSO_DATABASE_URL" in st.secrets and "TURSO_AUTH_TOKEN" in st.secrets and HAS_LIBSQL:
        return libsql.connect(
            database=st.secrets["TURSO_DATABASE_URL"],
            auth_token=st.secrets["TURSO_AUTH_TOKEN"]
        )
    else:
        return sqlite3.connect("registro_horas.db", check_same_thread=False)

def init_db():
    """Inicializa las tablas en la base de datos."""
    conn = get_db()
    c = conn.cursor()
    
    # Tabla Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            jornada_base INTEGER DEFAULT 25
        )
    ''')
    
    # Tabla Registro Horas
    c.execute('''
        CREATE TABLE IF NOT EXISTS registro_horas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            t1_entrada TEXT,
            t1_salida_real TEXT,
            t1_cierre TEXT,
            t2_activo INTEGER DEFAULT 0,
            t2_entrada TEXT,
            t2_salida_real TEXT,
            t2_cierre TEXT,
            notas TEXT,
            UNIQUE(usuario_id, fecha)
        )
    ''')
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def time_to_minutes(t_str):
    if not t_str or t_str == "-":
        return 0
    try:
        parts = t_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 0

def calc_turn_minutes(entrada_str, salida_str):
    if not entrada_str or not salida_str or entrada_str == "-" or salida_str == "-":
        return 0
    e_min = time_to_minutes(entrada_str)
    s_min = time_to_minutes(salida_str)
    
    if s_min <= e_min and s_min != 0:
        s_min += 24 * 60
    elif s_min == 0 and e_min > 0:
        s_min = 24 * 60
        
    diff = s_min - e_min
    return max(0, diff)

def format_minutes(total_min):
    es_negativo = total_min < 0
    total_min = abs(total_min)
    horas = total_min // 60
    mins = total_min % 60
    prefix = "-" if es_negativo else ""
    return f"{prefix}{horas}h {mins:02d}m"

# Inicializar BD
init_db()

# ==========================================
# 3. CONTROL DE SESIÓN
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario_id"] = None
    st.session_state["usuario_nombre"] = ""

# ==========================================
# 4. PANTALLA DE LOGIN / REGISTRO
# ==========================================
if not st.session_state["autenticado"]:
    st.title("🍕 Control de Horas - La Dolce Vita")
    st.markdown("Acceso privado para el personal autorizado.")

    col1, _ = st.columns([1, 1])
    
    with col1:
        tab_login, tab_reg = st.tabs(["🔑 Iniciar Sesión", "📝 Crear Cuenta"])
        
        with tab_login:
            login_user = st.text_input("Usuario", key="login_user")
            login_pass = st.text_input("Contraseña", type="password", key="login_pass")
            
            if st.button("Entrar", type="primary"):
                conn = get_db()
                c = conn.cursor()
                pass_enc = hash_password(login_pass)
                c.execute("SELECT id, usuario FROM usuarios WHERE usuario = ? AND password = ?", (login_user, pass_enc))
                user_match = c.fetchone()
                conn.close()
                
                if user_match:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_id"] = user_match[0]
                    st.session_state["usuario_nombre"] = user_match[1]
                    st.success(f"¡Bienvenido, {user_match[1]}!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")

        with tab_reg:
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM usuarios")
            total_usuarios = c.fetchone()[0]
            conn.close()

            if total_usuarios >= 2:
                st.warning("⚠️ Se ha alcanzado el límite máximo de 2 usuarios autorizados.")
            else:
                st.info(f"Cuentas registradas: {total_usuarios}/2")
                reg_user = st.text_input("Nuevo Usuario", key="reg_user")
                reg_pass = st.text_input("Nueva Contraseña", type="password", key="reg_pass")
                
                if st.button("Registrar Cuenta"):
                    if reg_user and reg_pass:
                        conn = get_db()
                        c = conn.cursor()
                        try:
                            c.execute("INSERT INTO usuarios (usuario, password) VALUES (?, ?)", 
                                      (reg_user, hash_password(reg_pass)))
                            conn.commit()
                            st.success("¡Cuenta creada correctamente! Ya puedes iniciar sesión.")
                        except Exception:
                            st.error("Error al registrar. Puede que ese nombre ya exista.")
                        finally:
                            conn.close()
                    else:
                        st.error("Por favor, completa todos los campos.")

# ==========================================
# 5. PANEL PRINCIPAL (SOLO TRAS INICIAR SESIÓN)
# ==========================================
else:
    user_id = st.session_state["usuario_id"]
    user_nombre = st.session_state["usuario_nombre"]

    st.sidebar.title("📋 Configuración")
    st.sidebar.write(f"👤 Conectado como: **{user_nombre}**")
    
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state["autenticado"] = False
        st.session_state["usuario_id"] = None
        st.session_state["usuario_nombre"] = ""
        st.rerun()

    st.sidebar.markdown("---")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT jornada_base FROM usuarios WHERE id = ?", (user_id,))
    res_jornada = c.fetchone()
    jornada_actual = res_jornada[0] if res_jornada else 25

    opcion_jornada = st.sidebar.radio(
        "Selecciona tu jornada base semanal:",
        ["Contrato 25h/semana", "Contrato 30h/semana"],
        index=0 if jornada_actual == 25 else 1
    )
    nueva_jornada = 25 if "25h" in opcion_jornada else 30

    if nueva_jornada != jornada_actual:
        c.execute("UPDATE usuarios SET jornada_base = ? WHERE id = ?", (nueva_jornada, user_id))
        conn.commit()
        st.sidebar.success("Jornada actualizada.")
    conn.close()

    st.title("⏰ Control de Horas Laborales")

    tab1, tab2 = st.tabs(["📝 Registro Diario", "📊 Resumen Mensual y Exportación"])

    # TAB 1: REGISTRO DIARIO
    with tab1:
        st.subheader("Registro de Turnos")
        fecha_sel = st.date_input("Selecciona la fecha:", datetime.date.today())
        fecha_str = fecha_sel.strftime("%Y-%m-%d")

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM registro_horas WHERE usuario_id = ? AND fecha = ?", (user_id, fecha_str))
        registro_existente = c.fetchone()
        conn.close()

        val_t1_e, val_t1_sr, val_t1_sc = "12:00", "16:00", "16:00"
        val_t2_act, val_t2_e, val_t2_sr, val_t2_sc = True, "20:00", "00:00", "00:00"
        val_notas = ""

        if registro_existente:
            val_t1_e = registro_existente[3] or val_t1_e
            val_t1_sr = registro_existente[4] or val_t1_sr
            val_t1_sc = registro_existente[5] or val_t1_sc
            val_t2_act = bool(registro_existente[6])
            val_t2_e = registro_existente[7] or val_t2_e
            val_t2_sr = registro_existente[8] or val_t2_sr
            val_t2_sc = registro_existente[9] or val_t2_sc
            val_notas = registro_existente[10] or ""

        st.markdown("---")
        st.markdown("### Turno 1 (Mañana / Principal)")
        col_t1_1, col_t1_2, col_t1_3 = st.columns(3)
        with col_t1_1:
            t1_e = st.text_input("Entrada T1", value=val_t1_e)
        with col_t1_2:
            t1_sr = st.text_input("Salida Real T1", value=val_t1_sr)
        with col_t1_3:
            t1_sc = st.text_input("Salida Oficial/Cierre T1", value=val_t1_sc)

        st.markdown("---")
        st.markdown("### Turno 2 (Tarde / Noche - Doble Turno)")
        t2_act = st.checkbox("Activar Turno 2", value=val_t2_act)

        if t2_act:
            col_t2_1, col_t2_2, col_t2_3 = st.columns(3)
            with col_t2_1:
                t2_e = st.text_input("Entrada T2", value=val_t2_e)
            with col_t2_2:
                t2_sr = st.text_input("Salida Real T2", value=val_t2_sr)
            with col_t2_3:
                t2_sc = st.text_input("Salida Oficial/Cierre T2", value=val_t2_sc)
        else:
            t2_e, t2_sr, t2_sc = "-", "-", "-"

        st.markdown("---")
        notas = st.text_area("Notas / Incidencias:", value=val_notas)

        if st.button("💾 Guardar Registro", type="primary"):
            conn = get_db()
            c = conn.cursor()
            
            # Borrar registro previo si existe e insertar actualizado
            c.execute("DELETE FROM registro_horas WHERE usuario_id = ? AND fecha = ?", (user_id, fecha_str))
            c.execute('''
                INSERT INTO registro_horas 
                (usuario_id, fecha, t1_entrada, t1_salida_real, t1_cierre, t2_activo, t2_entrada, t2_salida_real, t2_cierre, notas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, fecha_str, t1_e, t1_sr, t1_sc, 1 if t2_act else 0, t2_e, t2_sr, t2_sc, notas))
            conn.commit()
            conn.close()
            st.success("¡Registro guardado en la nube correctamente!")

    # TAB 2: RESUMEN MENSUAL
    with tab2:
        st.subheader("Cálculos y Reportes Mensuales")
        
        col_m1, col_m2 = st.columns(2)
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
                 "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        
        mes_actual_idx = datetime.date.today().month - 1
        with col_m1:
            mes_sel = st.selectbox("Mes:", meses, index=mes_actual_idx)
        with col_m2:
            anio_sel = st.number_input("Año:", value=datetime.date.today().year, step=1)

        num_mes = meses.index(mes_sel) + 1
        prefix_fecha = f"{anio_sel:04d}-{num_mes:02d}-"

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM registro_horas WHERE usuario_id = ? AND fecha LIKE ? ORDER BY fecha ASC", 
                  (user_id, f"{prefix_fecha}%"))
        rows = c.fetchall()
        conn.close()

        if not rows:
            st.info("No hay registros guardados para este mes.")
        else:
            filas_procesadas = []
            semanas_detectadas = set()
            total_minutos_reales = 0

            for r in rows:
                fecha_db = r[2]
                f_obj = datetime.datetime.strptime(fecha_db, "%Y-%m-%d").date()
                num_semana = f_obj.isocalendar()[1]
                semanas_detectadas.add(num_semana)

                dias_semana_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                nombre_dia = dias_semana_es[f_obj.weekday()]

                m_t1_real = calc_turn_minutes(r[3], r[4])
                m_t1_cierre = calc_turn_minutes(r[3], r[5])

                m_t2_real = calc_turn_minutes(r[7], r[8]) if r[6] else 0
                m_t2_cierre = calc_turn_minutes(r[7], r[9]) if r[6] else 0

                day_real_min = m_t1_real + m_t2_real
                day_cierre_min = m_t1_cierre + m_t2_cierre
                total_minutos_reales += day_real_min

                filas_procesadas.append({
                    "Fecha": f_obj.strftime("%d/%m/%Y"),
                    "Día": nombre_dia,
                    "Semana": f"Semana {num_semana}",
                    "T1 Entrada": r[3],
                    "T1 Salida Real": r[4],
                    "T1 Cierre": r[5],
                    "T2 Entrada": r[7] if r[6] else "-",
                    "T2 Salida Real": r[8] if r[6] else "-",
                    "T2 Cierre": r[9] if r[6] else "-",
                    "Horas Reales": format_minutes(day_real_min),
                    "Horas Cierre": format_minutes(day_cierre_min),
                    "Notas": r[10] or ""
                })

            num_semanas_activas = len(semanas_detectadas)
            minutos_base_contrato = num_semanas_activas * nueva_jornada * 60
            diferencia_minutos = total_minutos_reales - minutos_base_contrato

            col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
            with col_kpi1:
                st.metric("Horas Reales Hechas", format_minutes(total_minutos_reales))
            with col_kpi2:
                st.metric(f"Base Contrato ({num_semanas_activas} sem)", f"{num_semanas_activas * nueva_jornada}h 00m")
            with col_kpi3:
                st.metric("Horas Extra / Exceso", format_minutes(diferencia_minutos))

            st.markdown("---")
            df_tabla = pd.DataFrame(filas_procesadas)
            st.dataframe(df_tabla, use_container_width=True)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_tabla.to_excel(writer, index=False, sheet_name=f"Horas {mes_sel}")
            
            st.download_button(
                label="📊 Descargar Informe Excel (.xlsx)",
                data=buffer.getvalue(),
                file_name=f"Informe_Horas_{user_nombre}_{mes_sel}_{anio_sel}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )