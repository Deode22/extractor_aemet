import streamlit as st
import requests
import json
import pandas as pd
from io import BytesIO
import streamlit.components.v1 as components
import plotly.express as px
from datetime import timedelta, datetime, date
import numpy as np
import xlsxwriter
import time
import matplotlib.pyplot as plt
import base64

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


def obtener_datos_mensuales_estacion(idema, año_inicio, año_fin, api_key):
    base_url = "https://opendata.aemet.es/opendata"
    headers = {"api_key": api_key}
    all_data = []  # Lista para almacenar los DataFrames de cada lote
    
    # Crear un contenedor para los mensajes de progreso
    progress_container = st.empty()
    
    # Variables para rastrear el primer y último año con datos reales
    primer_año_con_datos = None
    ultimo_año_con_datos = None
    
    # Procesar en lotes de 2 años para evitar demasiadas solicitudes
    año_actual = año_inicio
    while año_actual <= año_fin:
        # Calcular el año final del lote (máximo 2 años por lote)
        año_final_lote = min(año_actual + 1, año_fin)
        
        # Crear endpoint para el lote de años
        endpoint = f"/api/valores/climatologicos/mensualesanuales/datos/anioini/{año_actual}/aniofin/{año_final_lote}/estacion/{idema}"
        url = base_url + endpoint
        
        try:
            # Mostrar mensaje de progreso en el contenedor
            progress_container.info(f"Obteniendo datos para el período {año_actual}-{año_final_lote}...")
            
            # Realizar la solicitud a la API
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            datos_respuesta = response.json()
            
            if datos_respuesta.get("estado") == 200:
                datos_url = datos_respuesta.get("datos")
                datos_response = requests.get(datos_url)
                datos_response.raise_for_status()
                datos = datos_response.json()
                df = pd.DataFrame(datos)
                
                # Procesar los datos si no están vacíos
                if not df.empty:
                    # Convertir fecha a datetime
                    if 'fecha' in df.columns:
                        df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
                        
                        # Actualizar el primer y último año con datos
                        años_en_datos = df['fecha'].dt.year.dropna().unique()
                        if len(años_en_datos) > 0:
                            min_año = min(años_en_datos)
                            max_año = max(años_en_datos)
                            
                            if primer_año_con_datos is None or min_año < primer_año_con_datos:
                                primer_año_con_datos = min_año
                            
                            if ultimo_año_con_datos is None or max_año > ultimo_año_con_datos:
                                ultimo_año_con_datos = max_año
                    
                    # Conversión de comas a puntos y a tipo numérico
                    for col in df.columns:
                        if df[col].dtype == 'object':
                            try:
                                df[col] = df[col].astype(float)
                            except (ValueError, TypeError):
                                df[col] = df[col].str.replace(',', '.', regex=False).astype(float, errors='ignore')
                    
                    all_data.append(df)
                    progress_container.success(f"Datos obtenidos correctamente para {año_actual}-{año_final_lote}")
                else:
                    progress_container.warning(f"No hay datos disponibles para el período {año_actual}-{año_final_lote}")
            else:
                progress_container.warning(f"No hay datos para el período {año_actual}-{año_final_lote}: {datos_respuesta.get('descripcion')}")
        
        except requests.exceptions.RequestException as e:
            progress_container.error(f"Error de conexión para el período {año_actual}-{año_final_lote}: {e}")
            # Si es un error de demasiadas solicitudes, esperar más tiempo
            if "429" in str(e):
                progress_container.warning("Demasiadas solicitudes. Esperando 10 segundos antes de continuar...")
                time.sleep(10)  # Esperar 10 segundos antes de continuar
                continue  # Reintentar el mismo lote
        except (json.JSONDecodeError, KeyError) as e:
            progress_container.error(f"Error al procesar datos para el período {año_actual}-{año_final_lote}: {e}")
        except ValueError as e:
            progress_container.error(f"Error al convertir datos a numérico para el período {año_actual}-{año_final_lote}: {e}")
        
        # Pausa entre solicitudes para evitar límites de la API
        time.sleep(2)  # Esperar 2 segundos entre solicitudes
        
        # Avanzar al siguiente lote
        año_actual = año_final_lote + 1
    
    # Limpiar el contenedor de progreso al finalizar
    progress_container.empty()
    
    if all_data:  # Si se obtuvieron datos
        final_df = pd.concat(all_data, ignore_index=True)  # Combina todos los DataFrames
        
        # Si no se encontraron años con datos, usar los años de entrada como fallback
        if primer_año_con_datos is None:
            primer_año_con_datos = año_inicio
        if ultimo_año_con_datos is None:
            ultimo_año_con_datos = año_fin
            
        # Convertir a enteros para evitar decimales
        primer_año_con_datos = int(primer_año_con_datos)
        ultimo_año_con_datos = int(ultimo_año_con_datos)
            
        # Devolver el DataFrame y los años reales con datos
        return final_df, primer_año_con_datos, ultimo_año_con_datos
    else:
        return None, None, None

def obtener_datos_estacion_12h(idema, api_key):
    """Función auxiliar para obtener solo los datos de la estación (nombre, coordenadas, altitud) desde la API de 12h"""
    df_12h = obtener_datos12h_estacion(idema, api_key)
    if df_12h is not None and not df_12h.empty:
        # Extraer datos de la estación del primer registro
        datos_estacion = {
            'nombre': df_12h['ubi'].iloc[0] if 'ubi' in df_12h.columns else None,
            'lat': df_12h['lat'].iloc[0] if 'lat' in df_12h.columns else None,
            'lon': df_12h['lon'].iloc[0] if 'lon' in df_12h.columns else None,
            'alt': df_12h['alt'].iloc[0] if 'alt' in df_12h.columns else None
        }
        return datos_estacion
    return None

def generar_tabla_climatica(df):
    if df is None or df.empty:
        st.warning("No hay datos suficientes para generar la tabla climática.")
        return None
    
    # Extraer el mes de la columna 'fecha'
    df['mes'] = df['fecha'].dt.month
    
    # Inicializar listas para almacenar los datos mensuales
    months = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC']
    TMA = []
    TmmA = []
    Tm = []
    Tmmm = []
    TmA = []
    PP = []
    
    # Función para extraer el valor de temperatura del formato "##.#(dd)"
    def extract_temp_value(temp_str):
        if pd.isna(temp_str):
            return np.nan
        try:
            # Intentar extraer el valor numérico antes del paréntesis
            return float(str(temp_str).split('(')[0].strip())
        except:
            return np.nan
    
    # Iterar sobre cada mes y calcular los valores requeridos
    for i in range(1, 13):
        monthly_data = df[df['mes'] == i]
        
        # Verificar si hay datos para este mes
        if monthly_data.empty:
            TMA.append(np.nan)
            TmmA.append(np.nan)
            Tm.append(np.nan)
            Tmmm.append(np.nan)
            TmA.append(np.nan)
            PP.append(np.nan)
            continue
        
        # Calcular valores para cada mes
        try:
            # Temperatura máxima absoluta
            ta_max_values = monthly_data['ta_max'].apply(extract_temp_value)
            TMA.append(ta_max_values.max())
            
            # Temperatura media de máximas
            TmmA.append(monthly_data['tm_max'].mean())
            
            # Temperatura media
            Tm.append(monthly_data['tm_mes'].mean())
            
            # Temperatura media de mínimas
            Tmmm.append(monthly_data['tm_min'].mean())
            
            # Temperatura mínima absoluta
            ta_min_values = monthly_data['ta_min'].apply(extract_temp_value)
            TmA.append(ta_min_values.min())
            
            # Precipitación media
            PP.append(monthly_data['p_mes'].mean())
        except Exception as e:
            st.warning(f"Error al procesar datos para el mes {i}: {e}")
            TMA.append(np.nan)
            TmmA.append(np.nan)
            Tm.append(np.nan)
            Tmmm.append(np.nan)
            TmA.append(np.nan)
            PP.append(np.nan)
    
    # Crear un DataFrame con los resultados
    result_df = pd.DataFrame({
        'Parámetro': ['T.M.A', 'T.m.A', 'T.m', 'T.m.m', 'T.m.A', 'PP'],
        'ENE': [TMA[0], TmmA[0], Tm[0], Tmmm[0], TmA[0], PP[0]],
        'FEB': [TMA[1], TmmA[1], Tm[1], Tmmm[1], TmA[1], PP[1]],
        'MAR': [TMA[2], TmmA[2], Tm[2], Tmmm[2], TmA[2], PP[2]],
        'ABR': [TMA[3], TmmA[3], Tm[3], Tmmm[3], TmA[3], PP[3]],
        'MAY': [TMA[4], TmmA[4], Tm[4], Tmmm[4], TmA[4], PP[4]],
        'JUN': [TMA[5], TmmA[5], Tm[5], Tmmm[5], TmA[5], PP[5]],
        'JUL': [TMA[6], TmmA[6], Tm[6], Tmmm[6], TmA[6], PP[6]],
        'AGO': [TMA[7], TmmA[7], Tm[7], Tmmm[7], TmA[7], PP[7]],
        'SEP': [TMA[8], TmmA[8], Tm[8], Tmmm[8], TmA[8], PP[8]],
        'OCT': [TMA[9], TmmA[9], Tm[9], Tmmm[9], TmA[9], PP[9]],
        'NOV': [TMA[10], TmmA[10], Tm[10], Tmmm[10], TmA[10], PP[10]],
        'DIC': [TMA[11], TmmA[11], Tm[11], Tmmm[11], TmA[11], PP[11]]
    })
    
    # Añadir descripciones de los parámetros
    parametros_desc = {
        'T.M.A': 'Temperatura Máxima Absoluta (°C)',
        'T.m.A': 'Temperatura Media de Máximas (°C)',
        'T.m': 'Temperatura Media (°C)',
        'T.m.m': 'Temperatura Media de Mínimas (°C)',
        'T.m.A': 'Temperatura Mínima Absoluta (°C)',
        'PP': 'Precipitación Media (mm)'
    }
    
    result_df['Descripción'] = result_df['Parámetro'].map(parametros_desc)
    
    # Reordenar columnas para que Parámetro y Descripción estén al principio
    cols = ['Parámetro', 'Descripción'] + months
    result_df = result_df[cols]
    
    return result_df

# --- Función para generar el climodiagrama ---
def generar_climodiagrama(tabla_climatica, nombre_estacion, lat_estacion, lon_estacion, alt_estacion, anio_inicio, anio_fin):
    if tabla_climatica is None or tabla_climatica.empty:
        st.warning("No hay datos suficientes para generar el climodiagrama.")
        return None

    # Extraer datos de la tabla climática
    meses = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC']
    precipitacion = np.array(tabla_climatica[meses].iloc[5].values)  # PP (Precipitación Media)
    temp_max = np.array(tabla_climatica[meses].iloc[1].values)  # T.m.A (Temperatura Media de Máximas)
    temp_min = np.array(tabla_climatica[meses].iloc[3].values)  # T.m.m (Temperatura Media de Mínimas)
    temp_media = np.array(tabla_climatica[meses].iloc[2].values)  # T.m (Temperatura Media)

    # Cálculos generales
    precip_total = np.sum(precipitacion)
    temp_max_media = np.mean(temp_max)
    temp_min_media = np.mean(temp_min)
    temp_media_anual = np.mean(temp_media)
    max_abs = np.max(temp_max)
    min_abs = np.min(temp_min)

    # Crear figura y ejes
    fig, ax1 = plt.subplots(figsize=(8,8), dpi=300)
    fig.patch.set_facecolor('white')

    x = np.arange(len(meses))

    # Línea de precipitación
    ax1.plot(x, precipitacion, color='#0070C0', linewidth=2, zorder=2)

    # Relleno hachurado bajo la curva de precipitación
    ax1.fill_between(x, precipitacion, 0, where=precipitacion>0, 
                     facecolor='none', edgecolor='#0070C0', hatch='////', linewidth=0, zorder=1)

    # Línea de temperatura (roja)
    ax2 = ax1.twinx()
    ax2.plot(x, temp_media, color='#D0021B', linewidth=2, zorder=3)

    # Ejes y estética
    ax1.set_ylabel('Precipitación mensual [mm]', fontsize=11, color='black')
    ax2.set_ylabel('Temperatura media mensual [°C]', fontsize=11, color='black')
    ax1.set_xlabel('Meses', fontsize=11, color='black')

    # Ejes en negro y gruesos
    for spine in ax1.spines.values():
        spine.set_color('black')
        spine.set_linewidth(1.2)
    for spine in ax2.spines.values():
        spine.set_color('black')
        spine.set_linewidth(1.2)

    # Ejes secundarios sin ticks extra
    ax2.tick_params(axis='y', colors='black')
    ax1.tick_params(axis='y', colors='black')
    ax1.tick_params(axis='x', colors='black')

    # Limites
    # Establecer límites para que la precipitación sea el doble de la temperatura
    max_temp_for_scale = max(max(temp_max) + 5, 40)  # Asegurar un mínimo razonable
    max_precip_for_scale = max_temp_for_scale * 2  # Precipitación = 2 * Temperatura
    
    # Asegurar que el máximo de precipitación visible sea al menos el máximo real + un margen
    max_precip_visible = max(max_precip_for_scale, max(precipitacion) + 20)
    
    ax1.set_ylim(0, max_precip_visible)
    ax2.set_ylim(-10, max_temp_for_scale)
    
    # Configurar las marcas de los ejes para mantener la relación 2:1
    temp_ticks = np.arange(-10, max_temp_for_scale+1, 10)
    precip_ticks = np.arange(0, max_precip_visible+1, 20)  # Incrementos de 20mm
    
    ax1.set_yticks(precip_ticks)
    ax2.set_yticks(temp_ticks)
    ax1.set_xticks(x)
    ax1.set_xticklabels(meses)

    # Líneas horizontales principales
    ax1.axhline(0, color='black', linewidth=1)
    ax2.axhline(0, color='black', linewidth=1, linestyle=':')

    # Más espacio arriba para la info
    plt.subplots_adjust(top=0.99)

    # Información superior izquierda
    coords_estacion = f"{lat_estacion}, {lon_estacion}"
    fig.text(0.05, 0.92, f'Estación: {nombre_estacion}', fontsize=10, va='top', ha='left', color='black')
    fig.text(0.05, 0.95, f'{coords_estacion} | {alt_estacion} msnm', fontsize=10, va='top', ha='left', color='black')

    # Información superior derecha
    fig.text(0.95, 0.98, f'{int(anio_inicio)}–{int(anio_fin)}', fontsize=12, fontweight='bold', va='top', ha='right', color='black')
    fig.text(0.95, 0.95, f'Prec. total anual: {precip_total:.1f} mm', fontsize=10, va='top', ha='right', color='black')
    fig.text(0.95, 0.92, f'T. máx. media: {temp_max_media:.1f} °C', fontsize=10, va='top', ha='right', color='black')
    fig.text(0.95, 0.89, f'T. media: {temp_media_anual:.1f} °C', fontsize=10, va='top', ha='right', color='black')
    fig.text(0.95, 0.86, f'T. mín. media: {temp_min_media:.1f} °C', fontsize=10, va='top', ha='right', color='black')

    # Fuente sans-serif
    plt.rcParams['font.family'] = 'sans-serif'

    plt.tight_layout(rect=[0.05, 0.12, 0.95, 0.85])
    
    return fig

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
if 'tabla_climatica' not in st.session_state:
    st.session_state.tabla_climatica = None
if 'nombre_estacion' not in st.session_state:
    st.session_state.nombre_estacion = None
if 'lat_estacion' not in st.session_state:
    st.session_state.lat_estacion = None
if 'lon_estacion' not in st.session_state:
    st.session_state.lon_estacion = None
if 'alt_estacion' not in st.session_state:
    st.session_state.alt_estacion = None
if 'anio_inicio' not in st.session_state:
    st.session_state.anio_inicio = None
if 'anio_fin' not in st.session_state:
    st.session_state.anio_fin = None

# Selección del tipo de consulta
tipo_consulta = st.radio("Selecciona el tipo de consulta:", ["Últimas 12 horas", "Datos diarios entre fechas", "Tabla climática"])

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

elif tipo_consulta == "Tabla climática":
    col1, col2 = st.columns(2)
    with col1:
        anio_inicio = st.number_input("Año de inicio:", min_value=1950, max_value=date.today().year, value=2005)
    with col2:
        anio_fin = st.number_input("Año de fin:", min_value=1950, max_value=date.today().year, value=date.today().year)

    if st.button("Generar Tabla Climática"):
        if anio_inicio > anio_fin:
            st.error("El año de inicio debe ser anterior al año de fin.")
        else:
            # Limpiar los datos de la estación anterior para forzar su actualización
            st.session_state.nombre_estacion = None
            st.session_state.lat_estacion = None
            st.session_state.lon_estacion = None
            st.session_state.alt_estacion = None
            
            # Guardar los años de entrada en session_state
            st.session_state.anio_inicio_input = anio_inicio
            st.session_state.anio_fin_input = anio_fin
            
            with st.spinner("Obteniendo datos mensuales y generando tabla climática..."):
                # Obtener datos mensuales y los años reales con datos
                datos_mensuales, primer_anio_real, ultimo_anio_real = obtener_datos_mensuales_estacion(idema, anio_inicio, anio_fin, API_KEY)
                
                # Guardar los años reales en session_state
                st.session_state.anio_inicio = primer_anio_real
                st.session_state.anio_fin = ultimo_anio_real
                
                # Verificar si se obtuvieron datos mensuales
                if datos_mensuales is not None and not datos_mensuales.empty:
                    # Generar tabla climática
                    tabla_climatica = generar_tabla_climatica(datos_mensuales)
                    
                    # Verificar si se generó la tabla climática
                    if tabla_climatica is not None:
                        st.session_state.tabla_climatica = tabla_climatica
                        st.session_state.tipo_consulta_actual = "tabla_climatica"
                        st.success(f"Tabla climática generada correctamente para la estación {idema} ({int(primer_anio_real)}-{int(ultimo_anio_real)})")
                    else:
                        st.error("No se pudo generar la tabla climática con los datos obtenidos.")
                else:
                    st.error(f"No se pudieron obtener datos mensuales para la estación {idema} en el periodo {anio_inicio}-{anio_fin}.")

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
    elif st.session_state.tipo_consulta_actual == "diarios" and 'fecha_ini' in locals() and 'fecha_fin' in locals():
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

# --- Mostrar y descargar tabla climática ---
if st.session_state.tipo_consulta_actual == "tabla_climatica" and st.session_state.tabla_climatica is not None:
    st.subheader(f"Tabla Climática para la estación {idema}")
    st.dataframe(st.session_state.tabla_climatica)
    
    # Botón para descargar la tabla climática como Excel
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        st.session_state.tabla_climatica.to_excel(writer, sheet_name='Tabla Climatica', index=False)
        # Ajustar el formato de la hoja
        workbook = writer.book
        worksheet = writer.sheets['Tabla Climatica']
        # Formato para números con 1 decimal
        num_format = workbook.add_format({'num_format': '0.0'})
        # Aplicar formato a todas las columnas numéricas (desde la columna 2 hasta el final)
        for col_num in range(2, len(st.session_state.tabla_climatica.columns)):
            worksheet.set_column(col_num, col_num, 10, num_format)
        # Ajustar ancho de columnas
        worksheet.set_column(0, 0, 10)  # Columna Parámetro
        worksheet.set_column(1, 1, 30)  # Columna Descripción
    
    excel_buffer.seek(0)
    st.download_button(
        label="Descargar Tabla Climática (Excel)",
        data=excel_buffer,
        file_name=f"tabla_climatica_{idema}.xlsx",
        mime="application/vnd.ms-excel"
    )

    # Botón para generar el climodiagrama
    if st.button("Generar Climodiagrama"):
        # Siempre obtener los datos actualizados de la estación actual
        with st.spinner("Obteniendo datos de la estación..."):
            datos_estacion = obtener_datos_estacion_12h(idema, API_KEY)
            
            if datos_estacion:
                st.session_state.nombre_estacion = datos_estacion['nombre']
                st.session_state.lat_estacion = datos_estacion['lat']
                st.session_state.lon_estacion = datos_estacion['lon']
                st.session_state.alt_estacion = datos_estacion['alt']
            else:
                st.error("No se pudieron obtener los datos de la estación. Verifica que el IDEMA sea correcto.")
                st.stop()
        
        # Verificar que tenemos los au00f1os necesarios
        if (st.session_state.anio_inicio is not None and
            st.session_state.anio_fin is not None):
            
            with st.spinner("Generando climodiagrama..."):
                fig = generar_climodiagrama(
                    st.session_state.tabla_climatica,
                    st.session_state.nombre_estacion,
                    st.session_state.lat_estacion,
                    st.session_state.lon_estacion,
                    st.session_state.alt_estacion,
                    st.session_state.anio_inicio,
                    st.session_state.anio_fin
                )
                
                if fig is not None:
                    st.pyplot(fig)
                    st.success("Climodiagrama generado correctamente")
                else:
                    st.error("No se pudo generar el climodiagrama")
        else:
            st.error("Faltan datos de la estación para generar el climodiagrama.")
