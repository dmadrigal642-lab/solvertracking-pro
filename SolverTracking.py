import streamlit as st
import sqlite3
import json
import urllib.request
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="SolverTracking Pro", page_icon="📦", layout="wide")

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
        destino TEXT,
        estado TEXT,
        fecha TEXT
    )
    '''
    if "TURSO_DATABASE_URL" in st.secrets:
        ejecutar_sql(query_tabla)
    else:
        conn = sqlite3.connect("solver_tracking.db")
        cursor = conn.cursor()
        cursor.execute(query_tabla)
        conn.commit()
        conn.close()

init_db()

st.title("📦 SolverTracking Pro")

tab1, tab2, tab3 = st.tabs(["Registrar Nueva Guía", "Rastreo y Seguimiento", "Dashboard y Analítica"])

with tab1:
    st.subheader("Registrar Nueva Guía")
    with st.form("form_guia", clear_on_submit=True):
        num_guia = st.text_input("Número de Guía")
        producto = st.text_input("Descripción del Producto")
        destino = st.text_input("Destino")
        estado = st.selectbox("Estado inicial", ["Registrado", "En tránsito", "Entregado"])
        submitted = st.form_submit_button("Guardar Guía")
        
        if submitted and num_guia:
            fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql = "INSERT INTO guias (numero_guia, producto, destino, estado, fecha) VALUES (?, ?, ?, ?, ?)"
            if "TURSO_DATABASE_URL" in st.secrets:
                res = ejecutar_sql(sql, [num_guia, producto, destino, estado, fecha_actual])
                if res is not None:
                    st.success("¡Guía registrada con éxito en Turso!")
            else:
                conn = sqlite3.connect("solver_tracking.db")
                cursor = conn.cursor()
                try:
                    cursor.execute(sql, (num_guia, producto, destino, estado, fecha_actual))
                    conn.commit()
                    st.success("¡Guía registrada con éxito localmente!")
                except Exception as ex:
                    st.error(f"Error: {ex}")
                finally:
                    conn.close()

with tab2:
    st.subheader("Envíos Registrados")
    sql_select = "SELECT numero_guia, producto, destino, estado, fecha FROM guias"
    if "TURSO_DATABASE_URL" in st.secrets:
        res = ejecutar_sql(sql_select)
        data_loaded = False
        if res and "results" in res:
            try:
                result_set = res["results"][0]
                if "response" in result_set and "result" in result_set["response"]:
                    cols = [c["name"] for c in result_set["response"]["result"]["cols"]]
                    rows = result_set["response"]["result"]["rows"]
                    parsed_rows = []
                    for row in rows:
                        parsed_rows.append([val.get("value") for val in row])
                    df = pd.DataFrame(parsed_rows, columns=cols)
                    if not df.empty:
                        st.dataframe(df, use_container_width=True)
                        data_loaded = True
            except Exception:
                pass
        if not data_loaded:
            st.info("No tienes guías registradas actualmente. ¡Agrega una en la pestaña 'Registrar Nueva Guía'!")
    else:
        conn = sqlite3.connect("solver_tracking.db")
        df = pd.read_sql(sql_select, conn)
        conn.close()
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No tienes guías registradas actualmente. ¡Agrega una en la pestaña 'Registrar Nueva Guía'!")

with tab3:
    st.subheader("Dashboard y Analítica")
    st.write("Panel general de métricas y rendimiento de envíos.")
