import streamlit as st
import sqlite3
import pandas as pd
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import urllib.request
import json

# Configuración de página
st.set_page_config(page_title="SolverTracking Pro", layout="wide", page_icon="🚢")

# --- SISTEMA DE LOGIN Y CONTROL DE ACCESO ---
USUARIO_CORRECTO = "admin"
PASSWORD_CORRECTO = "Tracking2026*"

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

def pantalla_login():
    st.markdown("<h2 style='text-align: center;'>🔒 Acceso Restringido - SolverTracking Pro</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("form_login"):
            usr = st.text_input("Usuario")
            pwd = st.text_input("Contraseña", type="password")
            btn_login = st.form_submit_button("Iniciar Sesión", use_container_width=True)
            
            if btn_login:
                if usr == USUARIO_CORRECTO and pwd == PASSWORD_CORRECTO:
                    st.session_state["autenticado"] = True
                    st.success("¡Acceso concedido!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")

if not st.session_state["autenticado"]:
    pantalla_login()
    st.stop()

# CSS Personalizado
st.markdown("""
    <style>
    .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; }
    div[data-testid="stForm"] { padding: 15px !important; }
    hr { margin: 1em 0 !important; }
    </style>
""", unsafe_allow_html=True)

# --- FUNCIÓN PARA ENVIAR CORREO DE ALERTA ---
def enviar_correo_alerta(remitente, password, destinatario, guias_alerta):
    try:
        msg = MIMEMultipart()
        msg['From'] = remitente
        msg['To'] = destinatario
        msg['Subject'] = f"🚨 Alerta de Envíos - SolverTracking Pro ({datetime.now().strftime('%d/%m/%Y')})"

        cuerpo = "<h2>🚨 Resumen de Envíos con Alerta Activa</h2>"
        cuerpo += "<p>Las siguientes órdenes están próximas a llegar o se encuentran retrasadas:</p><ul>"
        
        for g in guias_alerta:
            cuerpo += f"""
            <li style='margin-bottom: 10px;'>
                <b>Producto:</b> {g['producto']} (Guía: <code>{g['numero_guia']}</code>)<br>
                <b>Estado:</b> {g['estado']}<br>
                <b>Fecha Estimada:</b> {g['fecha_est']}<br>
                <b>Proveedor:</b> {g['proveedor']}
            </li>
            """
        cuerpo += "</ul><br><p><i>Este es un mensaje automático generado por SolverTracking Pro.</i></p>"

        msg.attach(MIMEText(cuerpo, 'html'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
        return True, "¡Correo enviado exitosamente!"
    except Exception as e:
        return False, f"Error al enviar correo: {str(e)}"

# --- FUNCIÓN PARA CONSULTAR CLIMA EN RUTA ---
@st.cache_data(ttl=3600)
def obtener_clima_ruta(origen):
    coordenadas = {
        "China": {"lat": 22.3, "lon": 114.1, "nombre": "Mar de China Meridional"},
        "Hong Kong": {"lat": 22.3, "lon": 114.1, "nombre": "Hong Kong / Mar del Sur"},
        "EE.UU.": {"lat": 25.7, "lon": -80.1, "nombre": "Miami / Estrecho de Florida"},
        "Europa": {"lat": 36.0, "lon": -5.3, "nombre": "Estrecho de Gibraltar"},
        "Japón": {"lat": 35.6, "lon": 139.6, "nombre": "Pacífico Norte"},
        "Otro": {"lat": 8.9, "lon": -79.5, "nombre": "Canal de Panamá"}
    }
    punto = coordenadas.get(origen, coordenadas["Otro"])
    url = f"https://api.open-meteo.com/v1/forecast?latitude={punto['lat']}&longitude={punto['lon']}&current_weather=true"
    try:
        res = requests.get(url, timeout=5).json()
        clima = res.get("current_weather", {})
        viento = clima.get("windspeed", 0)
        codigo = clima.get("weathercode", 0)
        alerta = viento > 40 or codigo in [95, 96, 99]
        return {
            "lugar": punto["nombre"],
            "viento": viento,
            "temperatura": clima.get("temperature", "N/A"),
            "alerta": alerta
        }
    except Exception:
        return None

# --- CONEXIÓN Y BASE DE DATOS (TURSO / LOCAL) ---
def ejecutar_sql(sql, params=None):
    if "TURSO_DATABASE_URL" in st.secrets:
        base_url = st.secrets["TURSO_DATABASE_URL"].strip()
        base_url = base_url.replace("libsql://", "https://").replace("wss://", "https://").rstrip("/")
        api_url = f"{base_url}/v2/pipeline"
        
        args_list = []
        for p in (params or []):
            if p is None:
                args_list.append({"type": "null"})
            elif isinstance(p, (int, float)):
                args_list.append({"type": "float" if isinstance(p, float) else "integer", "value": str(p)})
            else:
                args_list.append({"type": "text", "value": str(p)})
                
        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": args_list
                    }
                },
                {
                    "type": "close"
                }
            ]
        }
        
        req_data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(api_url, data=req_data, headers={
            "Authorization": f"Bearer {st.secrets['TURSO_AUTH_TOKEN']}",
            "Content-Type": "application/json"
        })
        try:
            with urllib.request.urlopen(req) as response:
                res_json = json.loads(response.read().decode('utf-8'))
                return res_json
        except Exception as e:
            st.error(f"Error de conexión con Turso: {e}")
            return None
    else:
        return sqlite3.connect("solver_tracking.db")

def init_db():
    query_tabla = '''
        CREATE TABLE IF NOT EXISTS guias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_guia TEXT UNIQUE,
            producto TEXT,
            proveedor TEXT,
            costo REAL,
            origen TEXT,
            destino TEXT,
            metodo TEXT,
            fecha_compra DATE,
            dias_promedio INTEGER,
            fecha_estimada DATE,
            dias_alarma INTEGER,
            estado TEXT,
            escala TEXT, 
            metodo_1 TEXT, 
            costo_1 REAL,
            dias_1 INTEGER, 
            metodo_2 TEXT, 
            costo_2 REAL,
            dias_2 INTEGER, 
            impuesto_1 REAL, 
            impuesto_2 REAL,
            tipo_cambio REAL, 
            notas TEXT
        )
    '''
    if "TURSO_DATABASE_URL" in st.secrets:
        ejecutar_sql(query_tabla)
    else:
        conn = sqlite3.connect("solver_tracking.db")
        c = conn.cursor()
        c.execute(query_tabla)
        columnas_nuevas = [
            ("escala", "TEXT"), ("metodo_1", "TEXT"), ("costo_1", "REAL"),
            ("dias_1", "INTEGER"), ("metodo_2", "TEXT"), ("costo_2", "REAL"),
            ("dias_2", "INTEGER"), ("impuesto_1", "REAL"), ("impuesto_2", "REAL"),
            ("tipo_cambio", "REAL"), ("notas", "TEXT")
        ]
        for col, tipo in columnas_nuevas:
            try:
                c.execute(f"ALTER TABLE guias ADD COLUMN {col} {tipo}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()

def guardar_guia(guia, producto, proveedor, origen, escala, destino, metodo_1, costo_1, imp_1, dias_1, metodo_2, costo_2, imp_2, dias_2, tipo_cambio, fecha_compra, dias_alarma, notas):
    dias_totales = dias_1 + dias_2
    costo_total = costo_1 + imp_1 + costo_2 + imp_2
    fecha_est = (fecha_compra + timedelta(days=dias_totales)).strftime('%Y-%m-%d')
    f_compra_str = fecha_compra.strftime('%Y-%m-%d')
    
    sql = '''
        INSERT INTO guias (numero_guia, producto, proveedor, costo, origen, escala, destino, metodo_1, costo_1, impuesto_1, dias_1, metodo_2, costo_2, impuesto_2, dias_2, tipo_cambio, fecha_compra, dias_promedio, fecha_estimada, dias_alarma, notas, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    params = (guia, producto, proveedor, costo_total, origen, escala, destino, metodo_1, costo_1, imp_1, dias_1, metodo_2, costo_2, imp_2, dias_2, tipo_cambio, f_compra_str, dias_totales, fecha_est, dias_alarma, notas, 'En Tránsito')
    
    if "TURSO_DATABASE_URL" in st.secrets:
        res = ejecutar_sql(sql, params)
        return res is not None
    else:
        conn = sqlite3.connect("solver_tracking.db")
        try:
            c = conn.cursor()
            c.execute(sql, params)
            conn.commit()
            conn.close()
            return True
        except Exception:
            conn.close()
            return False

def actualizar_guia(id_registro, costo_1, imp_1, costo_2, imp_2, tipo_cambio, escala, notas, estado):
    costo_total = costo_1 + imp_1 + costo_2 + imp_2
    sql = '''
        UPDATE guias 
        SET costo_1 = ?, impuesto_1 = ?, costo_2 = ?, impuesto_2 = ?, tipo_cambio = ?, costo = ?, escala = ?, notas = ?, estado = ?
        WHERE id = ?
    '''
    params = (costo_1, imp_1, costo_2, imp_2, tipo_cambio, costo_total, escala, notas, estado, id_registro)
    if "TURSO_DATABASE_URL" in st.secrets:
        ejecutar_sql(sql, params)
    else:
        conn = sqlite3.connect("solver_tracking.db")
        c = conn.cursor()
        c.execute(sql, params)
        conn.commit()
        conn.close()

def eliminar_guia(id_registro):
    sql = "DELETE FROM guias WHERE id = ?"
    if "TURSO_DATABASE_URL" in st.secrets:
        ejecutar_sql(sql, (id_registro,))
    else:
        conn = sqlite3.connect("solver_tracking.db")
        c = conn.cursor()
        c.execute(sql, (id_registro,))
        conn.commit()
        conn.close()

def cargar_guias():
    sql = "SELECT * FROM guias ORDER BY id DESC"
    if "TURSO_DATABASE_URL" in st.secrets:
        res = ejecutar_sql(sql)
        try:
            results = res["results"][0]["response"]["result"]
            cols = [c["name"] for c in results["cols"]]
            rows = []
            for row in results["rows"]:
                r_vals = [cell.get("value") for cell in row]
                rows.append(r_vals)
            return pd.DataFrame(rows, columns=cols)
        except Exception:
            return pd.DataFrame()
    else:
        conn = sqlite3.connect("solver_tracking.db")
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return df

init_db()

# --- BARRA LATERAL ---
with st.sidebar:
    if st.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["autenticado"] = False
        st.rerun()
        
    st.divider()

    st.header("⚙️ Configuración Notificaciones")
    st.caption("Envía resumen de alertas por correo usando Gmail.")
    
    email_emisor = st.text_input("Tu Correo (Gmail)", placeholder="ejemplo@gmail.com")
    email_pass = st.text_input("Contraseña de App (16 letras)", type="password")
    email_destino = st.text_input("Correo Destino", placeholder="ejemplo@gmail.com")
    
    st.divider()
    
    if st.button("📧 Verificar y Enviar Alertas Ahora", use_container_width=True):
        if not email_emisor or not email_pass or not email_destino:
            st.warning("Completa los datos de correo en la barra lateral.")
        else:
            df_alertas = cargar_guias()
            hoy_check = datetime.now().date()
            guias_para_notificar = []
            
            for _, r in df_alertas.iterrows():
                if r['estado'] not in ['Entregado', 'Cancelado / Perdido', 'Devuelto']:
                    f_est = datetime.strptime(str(r['fecha_estimada']), "%Y-%m-%d").date()
                    f_alr = f_est - timedelta(days=r['dias_alarma'])
                    
                    est_str = ""
                    if hoy_check > f_est:
                        est_str = f"🔴 Atrasado (Vencía el {f_est.strftime('%d/%m/%Y')})"
                    elif hoy_check >= f_alr:
                        est_str = f"🟡 Próximo a Llegar ({f_est.strftime('%d/%m/%Y')})"
                        
                    if est_str:
                        guias_para_notificar.append({
                            "producto": r['producto'],
                            "numero_guia": r['numero_guia'],
                            "estado": est_str,
                            "fecha_est": f_est.strftime('%d/%m/%Y'),
                            "proveedor": r['proveedor']
                        })
            
            if guias_para_notificar:
                exito, msg = enviar_correo_alerta(email_emisor, email_pass, email_destino, guias_para_notificar)
                if exito:
                    st.success(f"¡Alerta enviada! Se notificaron {len(guias_para_notificar)} órdenes.")
                else:
                    st.error(msg)
            else:
                st.info("No hay órdenes pendientes de alerta en este momento.")

# --- HEADER PRINCIPAL ---
st.title("🚢 SolverTracking Pro")
st.caption("Sistema de Control de Importaciones, Seguimiento y Analítica de Costos")

tab_nuevo, tab_rastreo, tab_dashboard = st.tabs([
    "➕ Registrar Nueva Guía", 
    "📦 Rastreo y Seguimiento", 
    "📊 Dashboard y Analítica"
])

# ==============================================================================
# PESTAÑA 1: REGISTRAR NUEVA GUÍA
# ==============================================================================
with tab_nuevo:
    st.subheader("➕ Registrar Nueva Guía / Envío Seccionado")
    with st.form("form_nueva_guia", clear_on_submit=True):
        st.markdown("##### 📋 Datos Generales")
        c_g1, c_g2, c_g3 = st.columns(3)
        with c_g1:
            guia = st.text_input("Número de Guía / Tracking *")
            producto = st.text_input("Nombre del Producto *")
        with c_g2:
            proveedor = st.text_input("Proveedor / Tienda")
            fecha_compra = st.date_input("Fecha de Compra", value=datetime.today())
        with c_g3:
            tipo_cambio = st.number_input("Tipo de Cambio (₡/$)", min_value=0.0, value=515.0, step=1.0)
            dias_alarma = st.number_input("Avisar (días antes)", min_value=1, value=3)

        st.divider()
        
        st.markdown("##### 🛫 **Tramo 1: Origen ➔ Escala**")
        c_t1_1, c_t1_2, c_t1_3 = st.columns(3)
        with c_t1_1:
            origen = st.selectbox("Origen Inicial", ["China", "Hong Kong", "EE.UU.", "Europa", "Japón", "Otro"])
            costo_1 = st.number_input("Costo Tramo 1 ($)", min_value=0.0, value=0.0, step=5.0)
        with c_t1_2:
            metodo_1 = st.selectbox("Método Tramo 1", ["Aéreo ✈️", "Marítimo 🚢", "Terrestre 🚛"])
            imp_1 = st.number_input("Impuesto Tramo 1 ($)", min_value=0.0, value=0.0, step=5.0)
        with c_t1_3:
            escala = st.text_input("Escala / Casillero", placeholder="Ej. Miami")
            dias_1 = st.number_input("Días Estimados T1", min_value=1, value=15)

        st.divider()

        st.markdown("##### 🛬 **Tramo 2: Escala ➔ Destino Final**")
        c_t2_1, c_t2_2, c_t2_3 = st.columns(3)
        with c_t2_1:
            destino = st.selectbox("Destino Final", ["Costa Rica", "México", "Colombia", "Panamá", "Otro"])
            costo_2 = st.number_input("Costo Tramo 2 ($)", min_value=0.0, value=0.0, step=5.0)
        with c_t2_2:
            metodo_2 = st.selectbox("Método Tramo 2", ["Ninguno / Directo 🚫", "Marítimo 🚢", "Aéreo ✈️", "Terrestre 🚛"])
            imp_2 = st.number_input("Impuesto Tramo 2 ($)", min_value=0.0, value=0.0, step=5.0)
        with c_t2_3:
            dias_2 = st.number_input("Días Estimados T2", min_value=0, value=10)

        st.divider()

        notas = st.text_area("📝 Comentarios / Notas adicionales", placeholder="Detalles de casillero, facturas, notas de aduana...", height=70)

        btn_guardar = st.form_submit_button("Guardar Registro", type="primary", use_container_width=True)

        if btn_guardar:
            if guia and producto:
                if guardar_guia(guia, producto, proveedor, origen, escala, destino, metodo_1, costo_1, imp_1, dias_1, metodo_2, costo_2, imp_2, dias_2, tipo_cambio, fecha_compra, dias_alarma, notas):
                    st.success(f"¡Guía '{guia}' guardada exitosamente!")
                    st.rerun()
                else:
                    st.error(f"La guía '{guia}' ya existe en el sistema.")
            else:
                st.warning("Por favor complete los campos obligatorios (*).")

# ==============================================================================
# PESTAÑA 2: RASTREO Y SEGUIMIENTO
# ==============================================================================
with tab_rastreo:
    st.subheader("📦 Envíos Registrados")

    df_guias = cargar_guias()

    if df_guias.empty:
        st.info("No tienes guías registradas actualmente. ¡Agrega una en la pestaña 'Registrar Nueva Guía'!")
    else:
        hoy = datetime.now().date()
        
        for idx, row in df_guias.iterrows():
            fecha_est = datetime.strptime(str(row['fecha_estimada']), "%Y-%m-%d").date()
            dias_restantes = (fecha_est - hoy).days
            fecha_alarma = fecha_est - timedelta(days=row['dias_alarma'])
            
            if row['estado'] == 'Entregado':
                badge = "🟢 Entregado"
            elif row['estado'] in ['Cancelado / Perdido', 'Devuelto']:
                badge = f"🔴 {row['estado']}"
            elif hoy > fecha_est:
                badge = f"🔴 Atrasado ({abs(dias_restantes)} días de retraso)"
            elif hoy >= fecha_alarma:
                badge = f"🟡 Próximo a Llegar ({dias_restantes} días restantes)"
            else:
                badge = f"🟢 En Tiempo ({dias_restantes} días restantes)"
            
            metodo_1_val = row.get('metodo_1') if pd.notna(row.get('metodo_1')) else row.get('metodo', '')
            
            if pd.notna(row.get('escala')) and str(row['escala']).strip() != "":
                ruta_txt = f"{row['origen']} ➔ {row['escala']} ({metodo_1_val}) ➔ {row['destino']}"
                if pd.notna(row.get('metodo_2')) and row['metodo_2'] != "Ninguno / Directo 🚫":
                    ruta_txt += f" ({row['metodo_2']})"
            else:
                ruta_txt = f"{row['origen']} ➔ {row['destino']} ({metodo_1_val})"

            c1_val = float(row['costo_1']) if pd.notna(row.get('costo_1')) else 0.0
            imp1_val = float(row['impuesto_1']) if pd.notna(row.get('impuesto_1')) else 0.0
            
            c2_val = float(row['costo_2']) if pd.notna(row.get('costo_2')) else 0.0
            imp2_val = float(row['impuesto_2']) if pd.notna(row.get('impuesto_2')) else 0.0

            total_t1 = c1_val + imp1_val
            total_t2 = c2_val + imp2_val
            c_tot = total_t1 + total_t2
            
            tc_val = float(row['tipo_cambio']) if pd.notna(row.get('tipo_cambio')) and row['tipo_cambio'] > 0 else 515.0
            total_crc = c_tot * tc_val

            with st.container(border=True):
                st.markdown(f"## **{row['producto']}** `[{row['numero_guia']}]`")
                st.write(f"📍 **Ruta:** {ruta_txt}")
                st.write(f"🏢 **Proveedor:** {row['proveedor']} | 💱 **Tipo Cambio:** ₡{tc_val:.2f}/$")
                st.write(f"📅 **Llegada Estimada:** {fecha_est.strftime('%d/%m/%Y')} | **Estado:** {badge}")
                
                st.markdown("<br>", unsafe_allow_html=True)

                st.markdown(f"""
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 15px; background-color: #1a1c23; padding: 15px; border-radius: 10px; border: 1px solid #2e323e; text-align: center;">
                    <div>
                        <div style="font-size: 13px; color: #a0aab8; font-weight: bold;">Costo T1 + Imp</div>
                        <div style="font-size: 22px; font-weight: bold; color: #ffffff;">${total_t1:.2f}</div>
                        <div style="font-size: 11px; color: #737d8c;">(${c1_val:.2f} + ${imp1_val:.2f})</div>
                    </div>
                    <div>
                        <div style="font-size: 13px; color: #a0aab8; font-weight: bold;">Costo T2 + Imp</div>
                        <div style="font-size: 22px; font-weight: bold; color: #ffffff;">${total_t2:.2f}</div>
                        <div style="font-size: 11px; color: #737d8c;">(${c2_val:.2f} + ${imp2_val:.2f})</div>
                    </div>
                    <div>
                        <div style="font-size: 13px; color: #a0aab8; font-weight: bold;">Total USD</div>
                        <div style="font-size: 22px; font-weight: bold; color: #00d47b;">${c_tot:.2f}</div>
                    </div>
                    <div style="grid-column: span 2;">
                        <div style="font-size: 13px; color: #a0aab8; font-weight: bold;">Total CRC</div>
                        <div style="font-size: 24px; font-weight: bold; color: #4da6ff; word-break: break-all;">₡{total_crc:,.2f}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                if pd.notna(row.get('notas')) and str(row['notas']).strip() != "":
                    st.caption(f"📝 **Notas:** {row['notas']}")

                if row['estado'] not in ['Entregado', 'Cancelado / Perdido', 'Devuelto']:
                    info_clima = obtener_clima_ruta(row['origen'])
                    if info_clima:
                        if info_clima['alerta']:
                            st.error(f"⚠️ **Alerta Meteorológica ({info_clima['lugar']}):** Vientos de {info_clima['viento']} km/h.")
                        else:
                            st.caption(f"🌤️ **Clima en Ruta ({info_clima['lugar']}):** {info_clima['temperatura']}°C | Viento: {info_clima['viento']} km/h (Normal)")

                with st.expander("✏️ Actualizar Costos, Estado o Eliminar", expanded=False):
                    with st.form(f"form_edit_{row['id']}"):
                        ec1, ec2, ec3 = st.columns(3)
                        with ec1:
                            edit_c1 = st.number_input("Costo T1 ($)", value=c1_val, step=5.0, key=f"ec1_{row['id']}")
                            edit_imp1 = st.number_input("Impuesto T1 ($)", value=imp1_val, step=5.0, key=f"eimp1_{row['id']}")
                        with ec2:
                            edit_c2 = st.number_input("Costo T2 ($)", value=c2_val, step=5.0, key=f"ec2_{row['id']}")
                            edit_imp2 = st.number_input("Impuesto T2 ($)", value=imp2_val, step=5.0, key=f"eimp2_{row['id']}")
                        with ec3:
                            edit_tc = st.number_input("Tipo Cambio (₡/$)", value=tc_val, step=1.0, key=f"etc_{row['id']}")
                            edit_escala = st.text_input("Escala / Casillero", value=str(row.get('escala', '')), key=f"eesc_{row['id']}")

                        col_edit_bot_a, col_edit_bot_b = st.columns(2)
                        with col_edit_bot_a:
                            estados_opciones = ["En Tránsito", "Entregado", "Cancelado / Perdido", "Devuelto"]
                            index_est = estados_opciones.index(row['estado']) if row['estado'] in estados_opciones else 0
                            edit_estado = st.selectbox("Estado de la Orden", estados_opciones, index=index_est, key=f"eest_{row['id']}")
                        with col_edit_bot_b:
                            edit_notas = st.text_area("Notas", value=str(row.get('notas', '')), key=f"enotas_{row['id']}")
                        
                        if st.form_submit_button("💾 Guardar Cambios", type="primary"):
                            actualizar_guia(row['id'], edit_c1, edit_imp1, edit_c2, edit_imp2, edit_tc, edit_escala, edit_notas, edit_estado)
                            st.success("¡Registro actualizado!")
                            st.rerun()

                    st.markdown("---")
                    col_del1, col_del2 = st.columns([3, 1])
                    with col_del1:
                        st.caption("⚠️ **Atención:** Eliminar esta orden la borrará de forma permanente.")
                    with col_del2:
                        if st.button("🗑️ Eliminar Guía", key=f"btn_del_{row['id']}", type="secondary"):
                            eliminar_guia(row['id'])
                            st.warning(f"Guía {row['numero_guia']} eliminada.")
                            st.rerun()

# ==============================================================================
# PESTAÑA 3: DASHBOARD Y ANALÍTICA DE DATOS
# ==============================================================================
with tab_dashboard:
    st.subheader("📊 Módulo de Analítica y Control de Órdenes")
    
    df_raw = cargar_guias()
    
    if df_raw.empty:
        st.info("No hay suficiente información para generar analítica. Registra al menos una guía.")
    else:
        hoy = datetime.now().date()
        df = df_raw.copy()
        
        df['costo_1'] = df['costo_1'].fillna(0.0)
        df['impuesto_1'] = df['impuesto_1'].fillna(0.0)
        df['costo_2'] = df['costo_2'].fillna(0.0)
        df['impuesto_2'] = df['impuesto_2'].fillna(0.0)
        df['tipo_cambio'] = df['tipo_cambio'].apply(lambda x: x if pd.notna(x) and x > 0 else 515.0)

        df['Fletes Totales ($)'] = df['costo_1'] + df['costo_2']
        df['Impuestos Totales ($)'] = df['impuesto_1'] + df['impuesto_2']
        df['Total USD ($)'] = df['Fletes Totales ($)'] + df['Impuestos Totales ($)']
        df['Total CRC (₡)'] = df['Total USD ($)'] * df['tipo_cambio']

        def calcular_estado_real(row):
            if row['estado'] == 'Entregado':
                return 'Entregado 🟢'
            elif row['estado'] in ['Cancelado / Perdido', 'Devuelto']:
                return 'Cancelado / Devuelto 🔴'
            try:
                fecha_est = datetime.strptime(str(row['fecha_estimada']), "%Y-%m-%d").date()
                if hoy > fecha_est:
                    return 'Atrasado 🔴'
            except Exception:
                pass
            return 'En Tránsito 🟡'

        df['Estado Real'] = df.apply(calcular_estado_real, axis=1)

        with st.expander("🔍 **Filtros de Búsqueda**", expanded=True):
            f_col1, f_col2, f_col3 = st.columns(3)
            with f_col1:
                filtro_estado = st.multiselect("Estado de Orden", options=df['estado'].unique().tolist(), default=df['estado'].unique().tolist())
            with f_col2:
                prov_list = [p for p in df['proveedor'].unique().tolist() if str(p).strip() != ""]
                filtro_proveedor = st.multiselect("Proveedor", options=prov_list, default=prov_list)
            with f_col3:
                search_text = st.text_input("🔎 Número de Guía o Producto", placeholder="Ej. 008612456, Varios...")

        df_filtered = df[df['estado'].isin(filtro_estado)]
        if filtro_proveedor:
            df_filtered = df_filtered[df_filtered['proveedor'].isin(filtro_proveedor)]
        if search_text:
            df_filtered = df_filtered[
                df_filtered['producto'].str.contains(search_text, case=False, na=False) | 
                df_filtered['numero_guia'].str.contains(search_text, case=False, na=False)
            ]

        st.markdown("### 📈 **Métricas Consolidadas**")
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        
        total_ordenes = len(df_filtered)
        total_usd = df_filtered['Total USD ($)'].sum()
        total_fletes = df_filtered['Fletes Totales ($)'].sum()
        total_impuestos = df_filtered['Impuestos Totales ($)'].sum()

        kpi1.metric("Órdenes Filtradas", f"{total_ordenes}")
        kpi2.metric("Inversión Total (USD)", f"${total_usd:,.2f}")
        kpi3.metric("Fletes Envíos Total", f"${total_fletes:,.2f}")
        kpi4.metric("Impuestos Totales", f"${total_impuestos:,.2f}")

        st.divider()

        st.markdown("### 📊 **Estado y Análisis de Costos**")
        if df_filtered.empty:
            st.warning("No hay datos que coincidan con los filtros seleccionados.")
        else:
            st.markdown("#### 📌 **1. Control de Estados (Entregados, En Tránsito y Atrasados)**")
            dist_estado = df_filtered["Estado Real"].value_counts().reset_index()
            dist_estado.columns = ["Estado", "Cantidad de Órdenes"]
            st.bar_chart(data=dist_estado, x="Estado", y="Cantidad de Órdenes", color="#4da6ff")

            st.divider()

            g_col1, g_col2 = st.columns(2)
            with g_col1:
                st.markdown("#### 💰 **2. Inversión USD por Proveedor**")
                inv_prov = df_filtered.groupby("proveedor")["Total USD ($)"].sum().reset_index()
                st.bar_chart(data=inv_prov, x="proveedor", y="Total USD ($)", color="#00d47b")

            with g_col2:
                st.markdown("#### 💸 **3. Desglose Costo Envíos vs. Impuestos**")
                desglose_df = pd.DataFrame({
                    "Concepto": ["Costos Envíos (Fletes)", "Impuestos Totales"],
                    "Monto USD": [total_fletes, total_impuestos]
                })
                st.bar_chart(data=desglose_df, x="Concepto", y="Monto USD", color="#ffaa00")

        st.divider()

        st.markdown("### 📑 **Tabla de Datos Completa**")
        columnas_visibles = [
            'numero_guia', 'producto', 'proveedor', 'estado', 'Estado Real',
            'Fletes Totales ($)', 'Impuestos Totales ($)', 'Total USD ($)', 'Total CRC (₡)', 
            'fecha_compra', 'fecha_estimada', 'notas'
        ]
        
        st.dataframe(
            df_filtered[columnas_visibles], 
            use_container_width=True,
            hide_index=True
        )

        csv_data = df_filtered.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Exportar Reporte Seleccionado a CSV",
            data=csv_data,
            file_name=f"reporte_solvertracking_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
