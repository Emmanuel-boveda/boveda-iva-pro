import os
import re
from datetime import datetime
import pandas as pd
import pypdf
from supabase import create_client, Client
import gradio as gr

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# --- CONFIGURACIÓN DE SUPABASE ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

def get_supabase_client():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception:
            return None
    return None

supabase = get_supabase_client()

# --- REGISTRO DE AUDITORÍA (LOGS) ---
def registrar_log(email, accion, detalles):
    try:
        if supabase:
            supabase.table("logs_actividad").insert({
                "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "usuario_email": email,
                "accion": accion,
                "detalles": detalles
            }).execute()
    except Exception:
        pass

# --- LÓGICA DE DATOS ---
def mes_a_numero(mes_str):
    meses_dict = {
        "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6,
        "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12
    }
    return meses_dict.get(str(mes_str).capitalize(), 1)

def cargar_saldos(email):
    try:
        if not supabase:
            return pd.DataFrame()
        response = supabase.table("saldos_iva").select("*").eq("usuario_email", email).execute()
        data = response.data
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        return df.rename(columns={
            "id": "ID", "rfc": "RFC", "periodo_mes": "Periodo_Mes", "periodo_anio": "Periodo_Anio",
            "tipo_declaracion": "Tipo_Declaracion", "num_operacion": "Num_Operacion",
            "fecha_presentacion": "Fecha_Presentacion", "saldo_original": "Saldo_Original",
            "saldo_disponible": "Saldo_Disponible", "estatus": "Estatus",
            "folio_fed": "Folio_FED", "fecha_ingreso_fed": "Fecha_Ingreso_FED", "observaciones_fed": "Observaciones_FED"
        })
    except Exception:
        return pd.DataFrame()

def cargar_historial(email):
    try:
        if not supabase:
            return pd.DataFrame()
        response = supabase.table("historial_acreditamientos").select("*").eq("usuario_email", email).execute()
        data = response.data
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        column_map = {
            "id": "ID", "usuario_email": "Usuario_Email", "fecha_aplicacion": "Fecha_Aplicacion",
            "rfc": "RFC", "periodo_origen": "Periodo_Origen", "periodo_destino": "Declaracion_Aplicada_Destino",
            "num_operacion_origen": "Num_Operacion_Origen", "saldo_anterior": "Saldo_Anterior",
            "monto_aplicado": "Monto_Aplicado", "remanente_nuevo": "Remanente_Nuevo"
        }
        df = df.rename(columns=column_map)
        if "Declaracion_Aplicada_Destino" not in df.columns:
            df["Declaracion_Aplicada_Destino"] = "No especificado"
        return df
    except Exception:
        return pd.DataFrame()

def obtener_rfcs_unicos(email):
    df_saldos = cargar_saldos(email)
    df_hist = cargar_historial(email)
    rfcs = set()
    if not df_saldos.empty and "RFC" in df_saldos.columns:
        rfcs.update(df_saldos["RFC"].dropna().unique().tolist())
    if not df_hist.empty and "RFC" in df_hist.columns:
        rfcs.update(df_hist["RFC"].dropna().unique().tolist())
    return sorted(list(rfcs))

def exportar_dataframe_excel(df, nombre_archivo):
    if df.empty:
        return None
    ruta_archivo = f"./{nombre_archivo}.xlsx"
    try:
        df.to_excel(ruta_archivo, index=False, engine='openpyxl')
        return ruta_archivo
    except Exception:
        return None

def obtener_o_crear_plantilla_excel():
    ruta = "./Plantilla_Carga_Masiva_BovedaIVA.xlsx"
    if not os.path.exists(ruta):
