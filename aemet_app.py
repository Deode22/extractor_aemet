import streamlit as st
import requests
import json
import pandas as pd
from io import BytesIO
import streamlit.components.v1 as components
import plotly.express as px
from datetime import timedelta


# Se que tener el secreto API aquí es una chapuza, pero quería mantenerlo simple y accesible. Es una API que he recogido especificamente para el proyecto
# --- Configuración y API Key ---
API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJkLmZ2aWxsYW51ZXZhQHVwbS5lcyIsImp0aSI6IjcwMGU0NDA4LWEzODktNDg3MC1hNzRlLTFhOTBiZDUxOTRlNCIsImlzcyI6IkFFTUVUIiwiaWF0IjoxNzE4Mjg1NzAwLCJ1c2VySWQiOiI3MDBlNDQwOC1hMzg5LTQ4NzAtYTc0ZS0xYTkwYmQ1MTk0ZTQiLCJyb2xlIjoiIn0.JZjhHTGBk-85Q0g260S08Qekel2LVnk3pSOGdVwBdUM"

# --- Funciones de la API ---
def obtener_datos12h_estacion(idema, api_key):
    base_url = "https://opendata.aemet.es/opendata"
    endpoint = f"/api/observacion/convencional/datos/estacion/{idema}"
    url = base_url + endpoint
    headers = {"api_key": api_key}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        datos_respuesta = response.json()

        if datos_respuesta.get("estado") == 200:
            datos_url = datos_respuesta.get("datos")
            datos_response = requests.get(datos_url)
            datos_response.raise_for_status()
            datos = datos_response.json()
            df = pd.DataFrame(datos)
            if 'fint' in df.columns:
                df['fint'] = pd.to_datetime(df['fint'], errors='coerce').dt.tz_localize(None)

            # --- Conversión de comas a puntos y a tipo numérico (12h) ---
            for col in df.columns:
                if df[col].dtype == 'object':  # Solo columnas de tipo 'object' (string)
                    try:
                        # Intenta convertir directamente a float (si ya tiene puntos)
                        df[col] = df[col].astype(float)
                    except (ValueError, TypeError):
                        # Si falla, reemplaza comas por puntos y luego convierte a float
                        df[col] = df[col].str.replace(',', '.', regex=False).astype(float, errors='ignore')
            return df

        else:
            st.error(f"Error AEMET: {datos_respuesta.get('descripcion')}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error de conexión: {e}")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        st.error(f"Error datos: {e}")
        return None
    except ValueError as e:  # Captura errores de conversión
        st.error(f"Error al convertir datos a numérico: {e}")
        return None
def obtener_datos_diarios_estacion(idema, fecha_ini, fecha_fin, api_key):
    base_url = "https://opendata.aemet.es/opendata"
    headers = {"api_key": api_key}
    all_data = []  # Lista para almacenar los DataFrames de cada batch

    fecha_inicio_batch = fecha_ini
    while fecha_inicio_batch <= fecha_fin:
        # Calcula la fecha de fin del batch (máximo 6 meses)
        fecha_fin_batch = fecha_inicio_batch + timedelta(days=180)  # Aprox. 6 meses
        if fecha_fin_batch > fecha_fin:
            fecha_fin_batch = fecha_fin  # No sobrepasar la fecha_fin original

        fechaIniStr = fecha_inicio_batch.strftime("%Y-%m-%dT00:00:00UTC")
        fechaFinStr = fecha_fin_batch.strftime("%Y-%m-%dT00:00:00UTC")

        endpoint = f"/api/valores/climatologicos/diarios/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{idema}"
        url = base_url + endpoint

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            datos_respuesta = response.json()

            if datos_respuesta.get("estado") == 200:
                datos_url = datos_respuesta.get("datos")
                datos_response = requests.get(datos_url)
                datos_response.raise_for_status()
                datos = datos_response.json()
                df = pd.DataFrame(datos)
                if 'fecha' in df.columns:
                    df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce').dt.tz_localize(None)

                # --- Conversión de comas a puntos y a tipo numérico (diarios) ---
                for col in df.columns:
                    if df[col].dtype == 'object':
                        try:
                            df[col] = df[col].astype(float)
                        except (ValueError, TypeError):
                            df[col] = df[col].str.replace(',', '.', regex=False).astype(float, errors='ignore')

                all_data.append(df)  # Añade el DataFrame del batch a la lista
            else:
                st.error(f"Error AEMET: {datos_respuesta.get('descripcion')}")
                return None  # O manejar el error de otra forma

        except requests.exceptions.RequestException as e:
            st.error(f"Error de conexión: {e}")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            st.error(f"Error al procesar datos: {e}")
            return None
        except ValueError as e:
            st.error(f"Error al convertir datos a numérico: {e}")
            return None

        fecha_inicio_batch = fecha_fin_batch + timedelta(days=1)  # Siguiente batch

    if all_data:  # Si se obtuvieron datos
        final_df = pd.concat(all_data, ignore_index=True)  # Combina todos los DataFrames
        return final_df
    else:
        return None


# --- Funciones para generar gráficos Plotly ---
def graficar_datos_diarios(df):
    if df is None or df.empty:
        st.warning("No hay datos para graficar.")
        return

    fig_prec = px.bar(df, x='fecha', y='prec', title='Precipitación Diaria',
                      labels={'prec': 'Precipitación (mm)', 'fecha': 'Fecha'})
    st.plotly_chart(fig_prec, use_container_width=True)

    fig_temp = px.line(df, x='fecha', y=['tmed', 'tmin', 'tmax'],
                       title='Temperaturas Diarias',
                       labels={'value': 'Temperatura (°C)', 'fecha': 'Fecha', 'variable': 'Tipo de Temperatura'})
    fig_temp.update_traces(mode='lines+markers')
    fig_temp.update_traces(line_color='green', selector=dict(name='tmed'))
    st.plotly_chart(fig_temp, use_container_width=True)

def graficar_datos_12h(df):
    if df is None or df.empty:
        st.warning("No hay datos para graficar.")
        return

    fig_prec = px.bar(df, x='fint', y='prec', title='Precipitación (12h)',
                      labels={'prec': 'Precipitación (mm)', 'fint': 'Fecha y Hora'})
    st.plotly_chart(fig_prec, use_container_width=True)

    fig_temp = px.line(df, x='fint', y=['ta', 'tamin', 'tamax'],
                       title='Temperaturas (12h)',
                       labels={'value': 'Temperatura (°C)', 'fint': 'Fecha y Hora', 'variable': 'Tipo de Temperatura'})
    fig_temp.update_traces(mode='lines+markers')
    fig_temp.update_traces(line_color='green', selector=dict(name='ta'))
    st.plotly_chart(fig_temp, use_container_width=True)

# --- Estilo CSS personalizado con pie de página ---
st.markdown(
    """
    <style>
    .reportview-container .main .block-container{
        max-width: 100%;
        padding-top: 1rem;
        padding-right: 1rem;
        padding-left: 1rem;
        padding-bottom: 4rem;  /* Añadido padding para dejar espacio al footer */
    }
    
    .footer {
        position: sticky;
        left: 0;
        bottom: 0;
        width: 100%;
        text-align: center;
        padding: 3px 0;
        font-style: italic;
        font-size: 0.8rem;
        border-top: 1px solid #ddd;
    }
    </style>
    
    <div class="footer">
        <p>Información elaborada por la Agencia Estatal de Meteorología AEMET©</p>
    </div>
    """,
    unsafe_allow_html=True,
)


st.title("Consulta de Datos Meteorológicos (AEMET)")

# --- Mapa de estaciones (iframe) ---
mostrar_mapa = st.checkbox("Mostrar mapa de estaciones")
if mostrar_mapa:
    try:
        with open("mapa_estaciones.html", "r", encoding="utf-8") as f:
            html_mapa = f.read()
        components.html(html_mapa, height=600, scrolling=True)
    except FileNotFoundError:
        st.error("Error: No se encontró el archivo mapa_estaciones.html")

# --- Inicialización del estado de sesión ---
if 'datos_obtenidos' not in st.session_state:
    st.session_state.datos_obtenidos = False
if 'df_datos' not in st.session_state:
    st.session_state.df_datos = None
if 'tipo_consulta_actual' not in st.session_state:
    st.session_state.tipo_consulta_actual = None

# Selección del tipo de consulta
tipo_consulta = st.radio("Selecciona el tipo de consulta:", ["Últimas 12 horas", "Datos diarios entre fechas"])

# Input común: IDEMA
idema = st.text_input("Introduce el INDICATIVO (IDEMA) de la estación:", value="3129")

# --- Lógica para OBTENER datos ---
if tipo_consulta == "Últimas 12 horas":
    if st.button("Obtener Datos (12h)"):
        st.session_state.df_datos = obtener_datos12h_estacion(idema, API_KEY)
        st.session_state.datos_obtenidos = True
        st.session_state.tipo_consulta_actual = "12h"

elif tipo_consulta == "Datos diarios entre fechas":
    col1, col2 = st.columns(2)
    with col1:
        fecha_ini = st.date_input("Fecha de inicio:", pd.to_datetime("2025-01-01"))
    with col2:
        fecha_fin = st.date_input("Fecha de fin:", pd.to_datetime("2025-02-15"))

    if st.button("Obtener Datos Diarios"):
        if fecha_ini > fecha_fin:
            st.error("La fecha de inicio debe ser anterior a la fecha de fin.")
        else:
            st.session_state.df_datos = obtener_datos_diarios_estacion(idema, fecha_ini, fecha_fin, API_KEY)
            st.session_state.datos_obtenidos = True
            st.session_state.tipo_consulta_actual = "diarios"

# --- Lógica para MOSTRAR y GRAFICAR datos ---
if st.session_state.datos_obtenidos:
    st.dataframe(st.session_state.df_datos)

    # Botón de descarga (sin columnas)
    csv_buffer = BytesIO()
    st.session_state.df_datos.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)
    nombre_archivo = f"datos_{idema}.csv"
    if st.session_state.tipo_consulta_actual == "12h":
        nombre_archivo = f"datos_12h_{idema}.csv"
    elif st.session_state.tipo_consulta_actual == "diarios":
        nombre_archivo = f"datos_diarios_{idema}_{fecha_ini.strftime('%Y%m%d')}-{fecha_fin.strftime('%Y%m%d')}.csv"
    st.download_button(label="Descargar CSV", data=csv_buffer, file_name=nombre_archivo, mime="text/csv")

    # Botones de graficado y llamadas a funciones (sin columnas)
    if st.session_state.tipo_consulta_actual == "12h":
        if st.button("Graficar (12h)"):
            graficar_datos_12h(st.session_state.df_datos)
            st.info("Si quieres los graficos en modo claro, ve a la esquina superior derecha > settings > y cambia el tema a modo claro")
    elif st.session_state.tipo_consulta_actual == "diarios":
        if st.button("Graficar (Diarios)"):
            graficar_datos_diarios(st.session_state.df_datos)
            st.info("Si quieres los graficos en modo claro, ve a la esquina superior derecha > settings > y cambia el tema a modo claro")
