import os
import re
import urllib.parse
from datetime import datetime, date
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

# --- CONFIGURACIÓN DE NÚMERO DE WHATSAPP PARA VENTAS ---
TELEFONO_WHATSAPP = "527226513054"  # Tu número configurado

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

def calcular_codigo_invitacion(email_referidor):
    if not email_referidor or "@" not in email_referidor:
        return ""
    parte_usuario = email_referidor.split("@")[0].strip().lower()
    solo_letras = re.sub(r'[^a-z]', '', parte_usuario)
    num_letras = len(solo_letras)
    if num_letras == 0:
        return "ref00"
    return f"{solo_letras}{num_letras:02d}"

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
    ruta = "./Plantilla_Carga_Masiva_BovedaIVA_v2.xlsx"
    datos_ejemplo = [
        {
            "RFC": "XAXX010101000", "Periodo_Mes": "Enero", "Ejercicio": 2026,
            "Tipo_Declaracion": "Normal", "Num_Operacion": "100200300",
            "Fecha_Presentacion": "2026-02-17", "Saldo_Original": 15000, "Remanente": 15000
        },
        {
            "RFC": "XAXX010101000", "Periodo_Mes": "Febrero", "Ejercicio": 2026,
            "Tipo_Declaracion": "Normal", "Num_Operacion": "100200301",
            "Fecha_Presentacion": "2026-03-17", "Saldo_Original": 22500, "Remanente": 10000
        }
    ]
    df_plantilla = pd.DataFrame(datos_ejemplo)
    df_plantilla.to_excel(ruta, index=False, engine='openpyxl')
    return ruta

PLANTILLA_EXCEL_PATH = obtener_o_crear_plantilla_excel()

def generar_html_tabla_planes(codigo_referido=""):
    cod_clean = codigo_referido.strip().lower()
    
    ref_txt_mensual = f" (Código de referido ingresado: {cod_clean})" if cod_clean else ""
    ref_txt_anual = f" (Código de referido ingresado: {cod_clean} | SOLICITO PROMOCIÓN ANUAL: +1 Mes gratis para mí y +2 Meses gratis para el colega del código {cod_clean})." if cod_clean else ""

    msg_bm = urllib.parse.quote(f"Hola, deseo contratar el Plan Básico Mensual ($39 MXN) de Bóveda IVA Pro.{ref_txt_mensual}")
    msg_ba = urllib.parse.quote(f"Hola, deseo contratar el Plan Básico Anual ($399 MXN) de Bóveda IVA Pro.{ref_txt_anual}")
    msg_pm = urllib.parse.quote(f"Hola, deseo contratar el Plan Plus Mensual ($69 MXN) de Bóveda IVA Pro.{ref_txt_mensual}")
    msg_pa = urllib.parse.quote(f"Hola, deseo contratar el Plan Plus Anual ($699 MXN) de Bóveda IVA Pro.{ref_txt_anual}")
    msg_im = urllib.parse.quote(f"Hola, deseo contratar el Plan Ilimitado Mensual ($99 MXN) de Bóveda IVA Pro.{ref_txt_mensual}")
    msg_ia = urllib.parse.quote(f"Hola, deseo contratar el Plan Ilimitado Anual ($999 MXN) de Bóveda IVA Pro.{ref_txt_anual}")

    link_bm = f"https://wa.me/{TELEFONO_WHATSAPP}?text={msg_bm}"
    link_ba = f"https://wa.me/{TELEFONO_WHATSAPP}?text={msg_ba}"
    link_pm = f"https://wa.me/{TELEFONO_WHATSAPP}?text={msg_pm}"
    link_pa = f"https://wa.me/{TELEFONO_WHATSAPP}?text={msg_pa}"
    link_im = f"https://wa.me/{TELEFONO_WHATSAPP}?text={msg_im}"
    link_ia = f"https://wa.me/{TELEFONO_WHATSAPP}?text={msg_ia}"

    banner_ref = ""
    if cod_clean:
        banner_ref = f"""
        <div style="background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 20px; font-size: 0.9rem;">
            🎉 <b>¡Código de referido aplicado ({cod_clean})!</b><br/>
            Al contratar un <b>Plan Anual</b>, recibes <b>+1 MES GRATIS</b> y tu colega con código {cod_clean} recibe <b>+2 MESES GRATIS</b>.
        </div>
        """

    return f"""
    <div style="max-width: 1000px; margin: 10px auto; padding: 10px;">
        {banner_ref}
        <h3 style="color: #1e3c72; text-align: center; margin-bottom: 20px; font-size: 1.4rem;">💳 Planes y Suscripciones — Bóveda IVA Pro</h3>
        <div style="display: flex; gap: 15px; justify-content: center; flex-wrap: wrap;">
            
            <!-- PLAN BÁSICO -->
            <div style="background: #ffffff; border: 2px solid #cbd5e1; border-radius: 12px; padding: 20px; width: 290px; text-align: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
                <h3 style="color: #1e3c72; margin-top: 0; font-size: 1.2rem;">Plan Básico</h3>
                <p style="font-size: 0.85rem; color: #64748b;">Hasta 5 RFCs de clientes.</p>
                <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 12px 0;">
                <p style="font-size: 1.6rem; font-weight: bold; color: #0f172a; margin: 5px 0;">$39 <span style="font-size: 0.85rem; font-weight: normal; color: #64748b;">MXN / mes</span></p>
                <p style="font-size: 1.0rem; font-weight: bold; color: #16a34a; margin: 5px 0;">o $399 <span style="font-size: 0.8rem; font-weight: normal; color: #64748b;">MXN / año</span></p>
                <p style="font-size: 0.75rem; color: #94a3b8; margin-bottom: 15px;">IVA incluido</p>
                
                <a href="{link_bm}" target="_blank" style="display: block; background: #25d366; color: white; padding: 10px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 0.9rem; margin-bottom: 8px;">💬 Contratar Mensual ($39)</a>
                <a href="{link_ba}" target="_blank" style="display: block; background: #128c7e; color: white; padding: 10px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 0.9rem;">💬 Contratar Anual ($399)</a>
            </div>

            <!-- PLAN PLUS -->
            <div style="background: #ffffff; border: 2px solid #16a34a; border-radius: 12px; padding: 20px; width: 290px; text-align: center; box-shadow: 0 6px 10px -2px rgba(0,0,0,0.1); position: relative;">
                <div style="position: absolute; top: -11px; right: 20px; background: #16a34a; color: white; padding: 3px 10px; border-radius: 10px; font-size: 0.7rem; font-weight: bold;">RECOMENDADO</div>
                <h3 style="color: #16a34a; margin-top: 0; font-size: 1.2rem;">Plan Plus</h3>
                <p style="font-size: 0.85rem; color: #64748b;">Hasta 10 RFCs de clientes.</p>
                <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 12px 0;">
                <p style="font-size: 1.6rem; font-weight: bold; color: #0f172a; margin: 5px 0;">$69 <span style="font-size: 0.85rem; font-weight: normal; color: #64748b;">MXN / mes</span></p>
                <p style="font-size: 1.0rem; font-weight: bold; color: #16a34a; margin: 5px 0;">o $699 <span style="font-size: 0.8rem; font-weight: normal; color: #64748b;">MXN / año</span></p>
                <p style="font-size: 0.75rem; color: #94a3b8; margin-bottom: 15px;">IVA incluido</p>
                
                <a href="{link_pm}" target="_blank" style="display: block; background: #25d366; color: white; padding: 10px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 0.9rem; margin-bottom: 8px;">💬 Contratar Mensual ($69)</a>
                <a href="{link_pa}" target="_blank" style="display: block; background: #128c7e; color: white; padding: 10px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 0.9rem;">💬 Contratar Anual ($699)</a>
            </div>

            <!-- PLAN ILIMITADO -->
            <div style="background: #ffffff; border: 2px solid #2a5298; border-radius: 12px; padding: 20px; width: 290px; text-align: center; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); position: relative;">
                <div style="position: absolute; top: -11px; right: 20px; background: #2a5298; color: white; padding: 3px 10px; border-radius: 10px; font-size: 0.7rem; font-weight: bold;">MÁXIMO PODER</div>
                <h3 style="color: #2a5298; margin-top: 0; font-size: 1.2rem;">Plan Ilimitado</h3>
                <p style="font-size: 0.85rem; color: #64748b;">RFCs e importaciones ilimitadas.</p>
                <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 12px 0;">
                <p style="font-size: 1.6rem; font-weight: bold; color: #0f172a; margin: 5px 0;">$99 <span style="font-size: 0.85rem; font-weight: normal; color: #64748b;">MXN / mes</span></p>
                <p style="font-size: 1.0rem; font-weight: bold; color: #16a34a; margin: 5px 0;">o $999 <span style="font-size: 0.8rem; font-weight: normal; color: #64748b;">MXN / año</span></p>
                <p style="font-size: 0.75rem; color: #94a3b8; margin-bottom: 15px;">IVA incluido</p>
                
                <a href="{link_im}" target="_blank" style="display: block; background: #25d366; color: white; padding: 10px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 0.9rem; margin-bottom: 8px;">💬 Contratar Mensual ($99)</a>
                <a href="{link_ia}" target="_blank" style="display: block; background: #128c7e; color: white; padding: 10px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 0.9rem;">💬 Contratar Anual ($999)</a>
            </div>

        </div>
    </div>
    """

def actualizar_enlace_referido(codigo_input):
    cod_clean = codigo_input.strip().lower()
    html_actualizado = generar_html_tabla_planes(cod_clean)
    if cod_clean:
        msg_info = f"✅ Código de referido activo: **{cod_clean}**. Al contratar un **Plan Anual**, se sumará **+1 mes gratis** para ti y **+2 meses gratis** para tu colega."
    else:
        msg_info = "ℹ️ Al contratar un paquete anual con un código de referido válido, recibes **+1 Mes Gratis** y tu colega recibe **+2 Meses Gratis**."
    return html_actualizado, msg_info

def procesar_carga_masiva_excel(email, plan, archivo_excel):
    if archivo_excel is None:
        return "❌ Por favor sube un archivo Excel válido.", gr.update(), gr.update(), gr.update()
    
    ruta_file = archivo_excel.name if hasattr(archivo_excel, 'name') else archivo_excel
    try:
        df_excel = pd.read_excel(ruta_file, engine='openpyxl')
    except Exception as e:
        return f"❌ Error al leer el archivo Excel: {str(e)}", gr.update(), gr.update(), gr.update()

    df_excel.columns = [str(c).strip().capitalize() for c in df_excel.columns]
    col_map_inversa = {
        "Rfc": "RFC", "Periodo_mes": "Periodo_Mes", "Periodo_anio": "Periodo_Anio", 
        "Ejercicio": "Periodo_Anio", "Tipo_declaracion": "Tipo_Declaracion", 
        "Num_operacion": "Num_Operacion", "Fecha_presentacion": "Fecha_Presentacion", 
        "Saldo_original": "Saldo_Original", "Remanente": "Saldo_Disponible",
        "Saldo_disponible": "Saldo_Disponible"
    }
    df_excel = df_excel.rename(columns=col_map_inversa)

    columnas_requeridas = ["RFC", "Periodo_Mes", "Periodo_Anio", "Tipo_Declaracion", "Num_Operacion", "Fecha_Presentacion", "Saldo_Original"]
    for col in columnas_requeridas:
        if col not in df_excel.columns:
            return f"❌ Formato incorrecto. Falta la columna obligatoria: '{col}'. Descarga la plantilla guía actualizada.", gr.update(), gr.update(), gr.update()

    rfcs_actuales = obtener_rfcs_unicos(email)
    plan_lower = str(plan).lower()
    if "ilimitado" in plan_lower:
        limite_rfc = 999999
    elif "plus" in plan_lower:
        limite_rfc = 10
    else:
        limite_rfc = 5

    registros_creados = 0
    registros_omitidos = 0

    for idx, row in df_excel.iterrows():
        try:
            rfc_limpio = str(row["RFC"]).upper().strip()
            num_op_limpio = str(row["Num_Operacion"]).replace(".0", "").strip()
            mes = str(row["Periodo_Mes"]).capitalize().strip()
            anio = int(row["Periodo_Anio"])
            tipo_dec = str(row["Tipo_Declaracion"]).strip()
            fecha_pres = str(row["Fecha_Presentacion"]).split()[0]
            saldo_orig = float(row["Saldo_Original"])
            
            if "Saldo_Disponible" in df_excel.columns and pd.notna(row["Saldo_Disponible"]):
                saldo_disp = float(row["Saldo_Disponible"])
            else:
                saldo_disp = saldo_orig

            estatus_inicial = "Agotado" if saldo_disp <= 0 else "Vigente"

            if not rfc_limpio or rfc_limpio == "NAN" or not num_op_limpio or num_op_limpio == "NAN":
                registros_omitidos += 1
                continue

            if rfc_limpio not in rfcs_actuales and len(rfcs_actuales) >= limite_rfc:
                registros_omitidos += 1
                continue

            check_existente = supabase.table("saldos_iva").select("id").eq("usuario_email", email).eq("rfc", rfc_limpio).eq("periodo_mes", mes).eq("periodo_anio", anio).execute()
            if check_existente.data:
                for reg_ext in check_existente.data:
                    supabase.table("saldos_iva").delete().eq("id", reg_ext["id"]).execute()

            supabase.table("saldos_iva").insert({
                "usuario_email": email, "rfc": rfc_limpio, "periodo_mes": mes,
                "periodo_anio": anio, "tipo_declaracion": tipo_dec, "num_operacion": num_op_limpio,
                "fecha_presentacion": fecha_pres, "saldo_original": saldo_orig,
                "saldo_disponible": saldo_disp, "estatus": estatus_inicial
            }).execute()

            registros_creados += 1
            if rfc_limpio not in rfcs_actuales:
                rfcs_actuales.append(rfc_limpio)

        except Exception:
            registros_omitidos += 1

    registrar_log(email, "CARGA_MASIVA_EXCEL", f"Registros ingresados: {registros_creados} | Omitidos: {registros_omitidos}")
    rfcs_actualizados = obtener_rfcs_unicos(email)
    val_init = rfcs_actualizados[0] if rfcs_actualizados else None

    msg = f"✅ **Carga Masiva Finalizada:** {registros_creados} declaraciones registradas exitosamente."
    upd = gr.update(choices=rfcs_actualizados, value=val_init)
    return msg, upd, upd, upd

def guardar_declaracion_pdf(email, plan, rfc, mes, anio, tipo_dec, num_op, fecha_pres, saldo_orig, confirma_mod):
    rfc_limpio = rfc.upper().strip()
    num_op_limpio = str(num_op).replace(".0", "").strip()
    
    if not num_op_limpio:
        return "❌ El número de operación es obligatorio.", gr.update(), gr.update(), gr.update()
    
    try:
        check_existente = supabase.table("saldos_iva").select("id, tipo_declaracion, num_operacion").eq("usuario_email", email).eq("rfc", rfc_limpio).eq("periodo_mes", mes).eq("periodo_anio", int(anio)).execute()
        
        if check_existente.data and not confirma_mod:
            reg_prev = check_existente.data[0]
            return f"⚠️ Ya existe una declaración registrada para {mes} {anio} ({reg_prev.get('tipo_declaracion')} - Op: {reg_prev.get('num_operacion')}). Si estás subiendo una Complementaria, marca la casilla correspondiente.", gr.update(), gr.update(), gr.update()

        if check_existente.data and confirma_mod:
            for reg_prev in check_existente.data:
                supabase.table("saldos_iva").delete().eq("id", reg_prev["id"]).execute()

        supabase.table("saldos_iva").insert({
            "usuario_email": email, "rfc": rfc_limpio, "periodo_mes": mes,
            "periodo_anio": int(anio), "tipo_declaracion": tipo_dec, "num_operacion": num_op_limpio,
            "fecha_presentacion": str(fecha_pres), "saldo_original": float(saldo_orig),
            "saldo_disponible": float(saldo_orig), "estatus": "Vigente"
        }).execute()
        
        registrar_log(email, "CARGA_DECLARACION_PDF", f"RFC: {rfc_limpio} | {mes} {anio} | Monto: ${saldo_orig} MXN")
        rfcs_nuevos = obtener_rfcs_unicos(email)
        upd = gr.update(choices=rfcs_nuevos, value=rfc_limpio)
        
        return "¡Declaración registrada correctamente!", upd, upd, upd
    except Exception as e:
        return f"Error al registrar: {e}", gr.update(), gr.update(), gr.update()

def eliminar_registro_boveda(email, id_saldo, rfc_actual):
    if not id_saldo:
        return "❌ Selecciona un ID válido para eliminar.", *actualizar_vista_resumen(email, rfc_actual)[0:5]
    try:
        supabase.table("saldos_iva").delete().eq("id", int(id_saldo)).eq("usuario_email", email).execute()
        registrar_log(email, "ELIMINAR_SALDO_BOVEDA", f"Eliminado registro ID: {id_saldo}")
        msg = f"🗑️ El registro con ID {id_saldo} fue eliminado exitosamente de la bóveda."
        res_act = actualizar_vista_resumen(email, rfc_actual)
        return msg, res_act[0], res_act[1], res_act[2], res_act[3], res_act[4], res_act[5]
    except Exception as e:
        return f"Error al eliminar registro: {e}", *actualizar_vista_resumen(email, rfc_actual)[0:5]

def eliminar_cliente_completo(email, rfc_a_borrar):
    if not rfc_a_borrar:
        return "❌ Por favor selecciona un RFC de cliente válido para eliminar.", gr.update(choices=[], value=None), gr.update(choices=[], value=None), gr.update(choices=[], value=None), "### Selecciona o registra un cliente.", pd.DataFrame(), None, gr.update(choices=[], value=None), gr.update(choices=[], value=None)
    try:
        supabase.table("saldos_iva").delete().eq("usuario_email", email).eq("rfc", rfc_a_borrar).execute()
        supabase.table("historial_acreditamientos").delete().eq("usuario_email", email).eq("rfc", rfc_a_borrar).execute()
        
        registrar_log(email, "ELIMINAR_CLIENTE_COMPLETO", f"Cliente RFC {rfc_a_borrar} eliminado totalmente.")
        
        nuevos_rfcs = obtener_rfcs_unicos(email)
        val_ini = nuevos_rfcs[0] if nuevos_rfcs else None
        
        msg = f"🗑️ El cliente con RFC **{rfc_a_borrar}** y todos sus registros asociados fueron eliminados permanentemente."
        upd_res = gr.update(choices=nuevos_rfcs, value=val_ini)
        
        if val_ini:
            res_act = actualizar_vista_resumen(email, val_ini)
            return msg, upd_res, upd_res, upd_res, res_act[0], res_act[1], res_act[2], res_act[3], res_act[4]
        else:
            return msg, upd_res, upd_res, upd_res, "### Sin clientes registrados.", pd.DataFrame(), None, gr.update(choices=[], value=None), gr.update(choices=[], value=None)
            
    except Exception as e:
        return f"Error al eliminar cliente: {e}", gr.update(), gr.update(), gr.update(), "### Error", pd.DataFrame(), None, gr.update(), gr.update()

def eliminar_registro_historial(email, id_historial, rfc_hist):
    if not id_historial:
        return "❌ Selecciona un ID de historial válido para eliminar.", pd.DataFrame(), None
    try:
        supabase.table("historial_acreditamientos").delete().eq("id", int(id_historial)).eq("usuario_email", email).execute()
        registrar_log(email, "ELIMINAR_HISTORIAL", f"Eliminado registro historial ID: {id_historial}")
        msg = f"🗑️ El movimiento de historial ID {id_historial} fue eliminado con éxito."
        df_h, ruta_ex, _ = obtener_historial_vista(email, rfc_hist)
        return msg, df_h, ruta_ex
    except Exception as e:
        return f"Error al eliminar historial: {e}", *obtener_historial_vista(email, rfc_hist)

def generar_pdf_expediente_fed_real(datos_saldo, logo_path=None):
    rfc_raw = str(datos_saldo.get("RFC", "N/A"))
    rfc = re.sub(r'[^a-zA-Z0-9]', '_', rfc_raw)
    id_reg = str(datos_saldo.get("ID", "0"))
    num_op_origen = str(datos_saldo.get("Num_Operacion", "N/A"))
    periodo_origen_str = f"{datos_saldo.get('Periodo_Mes')} {datos_saldo.get('Periodo_Anio')}"
    
    filename = f"./Expediente_FED_{rfc}_{id_reg}.pdf"

    doc = SimpleDocTemplate(
        filename, pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )
    styles = getSampleStyleSheet()
    story = []

    primary_color = colors.HexColor("#1e3c72")
    accent_color = colors.HexColor("#dc2626")
    light_bg = colors.HexColor("#f8fafc")
    dark_text = colors.HexColor("#0f172a")

    style_title = ParagraphStyle('DocTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=15, textColor=primary_color, leading=18)
    style_subtitle = ParagraphStyle('DocSubTitle', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, textColor=colors.HexColor("#475569"), leading=11)
    style_h2 = ParagraphStyle('SectionHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=primary_color, spaceBefore=10, spaceAfter=5, leading=12)
    style_body = ParagraphStyle('BodyDark', parent=styles['Normal'], fontName='Helvetica', fontSize=8, textColor=dark_text, leading=11)
    style_th = ParagraphStyle('TableHead', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, leading=10)
    style_badge = ParagraphStyle('BadgeText', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=1)

    header_elements = []
    if logo_path and os.path.exists(logo_path):
        try:
            img_logo = RLImage(logo_path, width=1.5*72, height=0.6*72)
            header_elements.append(img_logo)
        except Exception:
            header_elements.append(Paragraph("<b>BÓVEDA IVA PRO</b>", style_title))
    else:
        header_elements.append(Paragraph("<b>BÓVEDA IVA PRO</b><br/><font size=7 color='#64748b'>SISTEMA DE AUDITORÍA E INTEGRIDAD FISCAL</font>", style_title))

    header_table_data = [
        [
            header_elements[0],
            Paragraph(f"<font size=8><b>DICTAMEN TÉCNICO FED</b><br/>SOLICITUD DE DEVOLUCIÓN DE IVA<br/><b>ESTATUS: {datos_saldo.get('Estatus', 'EN TRÁMITE FED')}</b></font>", ParagraphStyle('RHeader', parent=style_subtitle, alignment=2))
        ]
    ]
    t_header = Table(header_table_data, colWidths=[280, 260])
    t_header.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
    story.append(t_header)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=6))

    banner_text = f"🔒 <b>ESTATUS: SALDO BLOQUEADO EN BÓVEDA POR TRÁMITE FED EN PROCESO</b>" if "TRÁMITE" in str(datos_saldo.get('Estatus')).upper() else f"<b>ESTATUS DEL SALDO: {datos_saldo.get('Estatus')}</b>"
    banner_bg = accent_color if "TRÁMITE" in str(datos_saldo.get('Estatus')).upper() else primary_color
    t_banner = Table([[Paragraph(banner_text, style_badge)]], colWidths=[540])
    t_banner.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), banner_bg),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(t_banner)
    story.append(Spacer(1, 8))

    monto_orig = float(datos_saldo.get("Saldo_Original", 0))
    monto_disp = float(datos_saldo.get("Saldo_Disponible", 0))

    datos_gen = [
        [Paragraph("<b>RFC Contribuyente:</b>", style_body), Paragraph(str(rfc_raw), style_body), Paragraph("<b>Folio Interno Bóveda:</b>", style_body), Paragraph(f"FED-{id_reg}", style_body)],
        [Paragraph("<b>Periodo / Ejercicio Origen:</b>", style_body), Paragraph(periodo_origen_str, style_body), Paragraph("<b>Fecha de Ingreso SAT:</b>", style_body), Paragraph(str(datos_saldo.get('Fecha_Ingreso_FED', datetime.now().strftime('%Y-%m-%d'))), style_body)],
        [Paragraph("<b>Tipo de Declaración:</b>", style_body), Paragraph(str(datos_saldo.get('Tipo_Declaracion', 'Normal')), style_body), Paragraph("<b>Número de Operación SAT:</b>", style_body), Paragraph(num_op_origen, style_body)],
        [Paragraph("<b>Fecha de Presentación:</b>", style_body), Paragraph(str(datos_saldo.get('Fecha_Presentacion', 'N/A')), style_body), Paragraph("<b>Folio Trámite FED SAT:</b>", style_body), Paragraph(str(datos_saldo.get('Folio_FED', 'En Proceso')), style_body)],
        [Paragraph("<b>Monto Original Declarante:</b>", style_body), Paragraph(f"${monto_orig:,.2f} MXN", style_body), Paragraph("<b>Monto Solicitado FED:</b>", style_body), Paragraph(f"<font color='#16a34a'><b>${monto_disp:,.2f} MXN</b></font>", style_body)]
    ]
    t_datos_gen = Table(datos_gen, colWidths=[120, 150, 120, 150])
    t_datos_gen.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), light_bg),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_datos_gen)
    story.append(Spacer(1, 8))

    story.append(Paragraph("1. FUNDAMENTACIÓN E INTEGRACIÓN JURÍDICA", style_h2))
    texto_ley = (
        "El presente expediente respalda la solicitud de devolución del saldo a favor de Impuesto al Valor Agregado conforme a los "
        "<b>Artículos 22 e integración del 22-D del Código Fiscal de la Federación (CFF)</b>, así como el <b>Artículo 6 de la Ley del Impuesto al Valor Agregado (LIVA)</b>. "
        "El saldo deriva de operaciones reales efectivamente pagadas, contando con acuse de presentación oficial ante el SAT."
    )
    story.append(Paragraph(texto_ley, style_body))
    story.append(Spacer(1, 8))

    story.append(Paragraph("2. DETERMINACIÓN ARITMÉTICA E HISTORIAL DE APLICACIONES", style_h2))
    fifo_table_data = [
        [Paragraph("Concepto / Evento", style_th), Paragraph("Folio / Referencia SAT", style_th), Paragraph("Saldo Orig.", style_th), Paragraph("Monto Aplicado", style_th), Paragraph("Remanente Saldo", style_th)]
    ]
    fifo_table_data.append([
        Paragraph(f"<b>Declaración Origen ({periodo_origen_str})</b>", style_body),
        Paragraph(num_op_origen, style_body),
        Paragraph(f"${monto_orig:,.2f}", style_body),
        Paragraph("$0.00", style_body),
        Paragraph(f"${monto_orig:,.2f}", style_body)
    ])

    remanente_corredor = monto_orig
    total_acreditado_prev = 0

    try:
        if supabase and num_op_origen != "N/A":
            res_hist = supabase.table("historial_acreditamientos").select("*").eq("num_operacion_origen", num_op_origen).order("id").execute()
            if res_hist.data:
                for reg in res_hist.data:
                    monto_apl = float(reg.get("monto_aplicado", 0))
                    dest_str = str(reg.get("periodo_destino", "Declaración Destino"))
                    total_acreditado_prev += monto_apl
                    remanente_corredor -= monto_apl
                    fifo_table_data.append([
                        Paragraph(f"(-) Aplicación en <b>{dest_str}</b>", style_body),
                        Paragraph("", style_body),
                        Paragraph(f"${monto_orig:,.2f}", style_body),
                        Paragraph(f"<font color='#dc2626'>-${monto_apl:,.2f}</font>", style_body),
                        Paragraph(f"${remanente_corredor:,.2f}", style_body)
                    ])
    except Exception:
        pass

    fifo_table_data.append([
        Paragraph("<b>🔒 SOLICITUD FED / BLOQUEO EN BÓVEDA</b>", style_body),
        Paragraph(str(datos_saldo.get('Folio_FED', 'TRÁMITE FED')), style_body),
        Paragraph(f"<b>${monto_orig:,.2f}</b>", style_body),
        Paragraph("<b>$0.00</b>", style_body),
        Paragraph(f"<font color='#16a34a'><b>${monto_disp:,.2f}</b></font>", style_body)
    ])

    t_fifo = Table(fifo_table_data, colWidths=[160, 100, 95, 90, 95])
    t_fifo.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), primary_color),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0,0), (-1,-1), 3.5), ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
    ]))
    story.append(t_fifo)
    story.append(Spacer(1, 10))

    doc.build(story)
    return filename

# --- FUNCIÓN DE EXTRACCIÓN DE PDF ---
def extraer_datos_pdf(file_obj):
    if file_obj is None:
        return "", "", 0, "Enero", 2026, datetime.now().strftime("%Y-%m-%d"), "Normal"
    
    texto = ""
    try:
        path = file_obj.name if hasattr(file_obj, 'name') else str(file_obj)
        reader = pypdf.PdfReader(path)
        for page in reader.pages:
            texto += page.extract_text() or ""
    except Exception:
        pass

    rfc, num_operacion, saldo_favor = "", "", 0
    mes, anio = "Enero", 2026
    fecha_pres = datetime.now().strftime("%Y-%m-%d")
    tipo_declaracion = "Normal"
    
    try:
        match_rfc = re.search(r"RFC[:\s]*([A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3})", texto, re.IGNORECASE)
        if match_rfc: rfc = match_rfc.group(1).upper()
    except Exception: pass

    try:
        match_op = re.search(r"Número\s+de\s+operación[:\s]*([0-9]+(?:\.[0-9]+)?)", texto, re.IGNORECASE)
        if match_op:
            raw_op = match_op.group(1)
            num_operacion = str(int(float(raw_op))) if "." in raw_op else raw_op
    except Exception: pass

    try:
        match_fecha = re.search(r"Fecha\s+y\s+hora\s+de\s+presentación[:\s]*(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
        if match_fecha:
            dt_p = datetime.strptime(match_fecha.group(1), "%d/%m/%Y")
            fecha_pres = dt_p.strftime("%Y-%m-%d")
    except Exception: pass

    try:
        match_anio = re.search(r"Ejercicio[:\s]*(\d{4})", texto, re.IGNORECASE)
        if match_anio: anio = int(match_anio.group(1))
    except Exception: pass

    try:
        meses_validos = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        for m in meses_validos:
            if re.search(rf"(?:Período|Periodo)[^\n]*?{m}", texto, re.IGNORECASE):
                mes = m; break
        else:
            for m in meses_validos:
                if re.search(rf"\b{m}\b", texto, re.IGNORECASE):
                    mes = m; break
    except Exception: pass

    try:
        if re.search(r"dejar\s+sin\s+efecto", texto, re.IGNORECASE):
            tipo_declaracion = "Complementaria - Dejar sin Efecto"
        elif re.search(r"complementaria|modificación|modificacion", texto, re.IGNORECASE):
            tipo_declaracion = "Complementaria - Modificación"
    except Exception: pass

    try:
        if "Impuesto al Valor Agregado" in texto:
            partes_iva = texto.split("Impuesto al Valor Agregado")
            if len(partes_iva) > 1:
                bloque_iva = partes_iva[1][:300]
                match_afavor = re.search(r"A\s+favor[:\s]*([\d,\.]+)", bloque_iva, re.IGNORECASE)
                if match_afavor:
                    val_str = match_afavor.group(1).replace(",", "").split(".")[0]
                    saldo_favor = int(val_str) if val_str.isdigit() else 0
    except Exception: pass

    return rfc, num_operacion, saldo_favor, mes, anio, fecha_pres, tipo_declaracion

# --- SESIÓN, AUTENTICACIÓN Y CAMBIO DE CONTRASEÑA ---
def login_usuario(email, password):
    email = email.strip().lower()
    if not email or not password:
        return "❌ Ingresa usuario y contraseña.", gr.update(visible=True), gr.update(visible=False), "", "", ""
    if not supabase:
        return "❌ Error de conexión con Supabase.", gr.update(visible=True), gr.update(visible=False), "", "", ""
    try:
        res = supabase.table("usuarios_saas").select("*").eq("email", email).execute()
        usuarios = res.data
        if not usuarios:
            return "❌ Usuario no registrado.", gr.update(visible=True), gr.update(visible=False), "", "", ""
        
        user_data = usuarios[0]
        if user_data.get("password") == password:
            if user_data.get("activo") == False:
                return "❌ Suscripción suspendida.", gr.update(visible=True), gr.update(visible=False), "", "", ""
            
            # VALIDACIÓN DE FECHA DE EXPIRACIÓN
            fecha_exp_val = (
                user_data.get("fecha_expiración") or 
                user_data.get("fecha_expiracion") or 
                user_data.get("fecha_vencimiento") or 
                user_data.get("expiracion")
            )
            
            if fecha_exp_val and str(fecha_exp_val).strip() not in ["None", "null", ""]:
                fecha_exp_str = str(fecha_exp_val).split()[0]
                try:
                    dt_exp = datetime.strptime(fecha_exp_str, "%Y-%m-%d").date()
                    if date.today() > dt_exp:
                        return f"❌ Tu suscripción venció el {fecha_exp_str}. Por favor renueva tu plan para continuar.", gr.update(visible=True), gr.update(visible=False), "", "", ""
                except Exception:
                    pass
            else:
                fecha_exp_str = "Indefinida"
            
            tipo_plan = user_data.get("plan", "Plan Básico")
            codigo_usuario = calcular_codigo_invitacion(email)
            
            header_html = f'''
            <div style="background: linear-gradient(135deg, #8BC4B9 0%, #6BA89B 100%); padding: 18px 22px; border-radius: 10px; color: #0f172a; margin-bottom: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                    <div>
                        <h2 style="margin:0; font-size: 1.8rem; font-weight: bold; color: #0f172a;">🏛️ Bóveda IVA Pro</h2>
                        <p style="margin:5px 0 0 0; color: #1e293b; font-size: 0.95rem;">
                            Bienvenido, <b>{email}</b> &nbsp;|&nbsp; 
                            Plan: <b>{tipo_plan}</b> &nbsp;|&nbsp; 
                            Vence: <b style="color: #065f46;">{fecha_exp_str}</b>
                        </p>
                    </div>
                    <div style="background: rgba(255, 255, 255, 0.4); padding: 8px 16px; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.6); text-align: right;">
                        <span style="font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; color: #1e293b; display: block; font-weight: 600;">Mi Código de Referido:</span>
                        <span style="font-size: 1.3rem; font-weight: bold; color: #0f172a; font-family: monospace;">{codigo_usuario}</span>
                    </div>
                </div>
            </div>
            '''

            return (
                "¡Acceso concedido!", gr.update(visible=False), gr.update(visible=True),
                header_html, email, tipo_plan
            )
        else:
            return "❌ Contraseña incorrecta.", gr.update(visible=True), gr.update(visible=False), "", "", ""
    except Exception as e:
        return f"Error al validar acceso: {e}", gr.update(visible=True), gr.update(visible=False), "", "", ""

def logout_usuario():
    return gr.update(visible=True), gr.update(visible=False), "", ""

def cambiar_contrasena(email, pass_actual, pass_nueva, pass_conf):
    if not email:
        return "❌ Sesión no válida."
    if not pass_actual or not pass_nueva or not pass_conf:
        return "❌ Todos los campos de contraseña son obligatorios."
    if pass_nueva != pass_conf:
        return "❌ Las nuevas contraseñas no coinciden."
    if len(pass_nueva) < 6:
        return "❌ La nueva contraseña debe tener al menos 6 caracteres."
    
    try:
        res = supabase.table("usuarios_saas").select("password").eq("email", email).execute()
        if not res.data:
            return "❌ Usuario no encontrado."
        
        if res.data[0].get("password") != pass_actual:
            return "❌ La contraseña actual es incorrecta."
        
        supabase.table("usuarios_saas").update({"password": pass_nueva}).eq("email", email).execute()
        registrar_log(email, "CAMBIO_CONTRASEÑA", "El usuario actualizó su contraseña con éxito.")
        return "✅ ¡Contraseña actualizada exitosamente en Supabase!"
    except Exception as e:
        return f"❌ Error al actualizar contraseña: {e}"

def inicializar_panel_usuario(email):
    rfcs = obtener_rfcs_unicos(email)
    val_inicial = rfcs[0] if rfcs else None
    html_pagos_interno = generar_html_tabla_planes("")
    upd = gr.update(choices=rfcs, value=val_inicial)
    return upd, upd, upd, upd, html_pagos_interno

def actualizar_vista_resumen(email, rfc):
    if not rfc:
        return "### Selecciona o registra un cliente.", pd.DataFrame(), gr.update(choices=[], value=None), None, gr.update(choices=[], value=None), gr.update(choices=[], value=None)
    df = cargar_saldos(email)
    if df.empty:
        return "### No hay datos registrados.", pd.DataFrame(), gr.update(choices=[], value=None), None, gr.update(choices=[], value=None), gr.update(choices=[], value=None)
    
    df_cliente = df[df["RFC"] == rfc].copy()
    if df_cliente.empty:
        return f"### Sin registros para {rfc}", pd.DataFrame(), gr.update(choices=[], value=None), None, gr.update(choices=[], value=None), gr.update(choices=[], value=None)
    
    df_cliente["Mes_Num"] = df_cliente["Periodo_Mes"].apply(mes_a_numero)
    df_cliente = df_cliente.sort_values(by=["Periodo_Anio", "Mes_Num"]).drop(columns=["Mes_Num"])
    
    total_disp = int(df_cliente[df_cliente["Estatus"] == "Vigente"]["Saldo_Disponible"].sum()) if not df_cliente.empty else 0
    metric_html = f"<h3>SALDO TOTAL VIGENTE — {rfc}: <span style='color:#16a34a;'>${total_disp:,} MXN</span></h3>"
    
    ids_lista = df_cliente["ID"].tolist()
    ids_fed = df_cliente[df_cliente["Estatus"].isin(["Vigente", "En Trámite FED"])]["ID"].tolist()
    ruta_excel = exportar_dataframe_excel(df_cliente, f"Resumen_Boveda_{rfc}")
    
    upd_ids = gr.update(choices=ids_lista, value=ids_lista[0] if ids_lista else None)
    upd_fed = gr.update(choices=ids_fed, value=ids_fed[0] if ids_fed else None)
    upd_ids_del = gr.update(choices=ids_lista, value=ids_lista[0] if ids_lista else None)
    
    return metric_html, df_cliente, upd_ids, ruta_excel, upd_fed, upd_ids_del

def procesar_solicitud_fed(email, id_saldo, folio_fed, fecha_ingreso, obs, logo_file):
    if not id_saldo:
        return "❌ Selecciona un saldo válido.", None
    try:
        res = supabase.table("saldos_iva").select("*").eq("id", int(id_saldo)).execute()
        if not res.data:
            return "❌ No se encontró el saldo.", None
        
        row = res.data[0]
        datos_saldo = {
            "ID": row.get("id"), "RFC": row.get("rfc"), "Periodo_Mes": row.get("periodo_mes"),
            "Periodo_Anio": row.get("periodo_anio"), "Tipo_Declaracion": row.get("tipo_declaracion"),
            "Num_Operacion": row.get("num_operacion"), "Fecha_Presentacion": row.get("fecha_presentacion"),
            "Saldo_Original": row.get("saldo_original", 0), "Saldo_Disponible": row.get("saldo_disponible", 0),
            "Estatus": "En Trámite FED", "Folio_FED": folio_fed if folio_fed else f"FED-{id_saldo}",
            "Fecha_Ingreso_FED": fecha_ingreso, "Observaciones_FED": obs
        }
        
        supabase.table("saldos_iva").update({
            "estatus": "En Trámite FED", "folio_fed": datos_saldo["Folio_FED"],
            "fecha_ingreso_fed": str(fecha_ingreso), "observaciones_fed": str(obs)
        }).eq("id", int(id_saldo)).execute()

        logo_path = logo_file.name if hasattr(logo_file, 'name') else logo_file
        pdf_path = generar_pdf_expediente_fed_real(datos_saldo, logo_path)
        registrar_log(email, "CONGELAR_FED", f"Saldo ID: {id_saldo} congelado por trámite FED {folio_fed}")
        return f"✅ Saldo con ID {id_saldo} congelado exitosamente para Trámite FED.", pdf_path
    except Exception as e:
        return f"Error al congelar saldo para FED: {e}", None

def resolver_tramite_fed(email, id_saldo, accion_resolucion, num_deposito, confirma_accion):
    if not confirma_accion:
        return "❌ Debes confirmar la casilla de verificación antes de procesar la resolución."
    if not id_saldo:
        return "❌ Selecciona un ID de saldo en trámite."

    try:
        if accion_resolucion == "Aprobado / Devuelto por el SAT":
            if not num_deposito:
                return "❌ Por favor ingresa el Número de Depósito / Autorización del SAT."
            
            supabase.table("saldos_iva").update({
                "saldo_disponible": 0, "estatus": "Devuelto / Pagado",
                "observaciones_fed": f"Aprobado SAT. Depósito: {num_deposito}"
            }).eq("id", int(id_saldo)).execute()

            registrar_log(email, "PAGO_FED_APROBADO", f"Saldo ID: {id_saldo} devuelto por el SAT.")
            return f"🎉 Saldo ID {id_saldo} marcado como DEVUELTO Y PAGADO por el SAT."

        elif accion_resolucion == "Rechazado / Desistido (Descongelar)":
            supabase.table("saldos_iva").update({"estatus": "Vigente"}).eq("id", int(id_saldo)).execute()
            registrar_log(email, "DESCONGELAR_FED", f"Saldo ID: {id_saldo} descongelado.")
            return f"🔄 Saldo ID {id_saldo} ha sido DESCONGELADO y reincorporado como Vigente."

        return "Acción no reconocida."
    except Exception as e:
        return f"Error al resolver trámite FED: {e}"

def ejecutar_fifo(email, rfc, monto, mes_dest, anio_dest):
    if not rfc: return "❌ Selecciona un RFC.", pd.DataFrame(), ""
    if monto <= 0: return "❌ Ingresa un monto mayor a cero.", pd.DataFrame(), ""
    
    df_saldos = cargar_saldos(email)
    df_vigentes = df_saldos[(df_saldos["RFC"] == rfc) & (df_saldos["Estatus"] == "Vigente")].copy()
    if df_vigentes.empty:
        return "❌ No hay saldos vigentes disponibles para este cliente.", pd.DataFrame(), ""
    
    df_vigentes["Mes_Num"] = df_vigentes["Periodo_Mes"].apply(mes_a_numero)
    df_vigentes = df_vigentes.sort_values(by=["Periodo_Anio", "Mes_Num"]).drop(columns=["Mes_Num"])
    
    if monto > df_vigentes["Saldo_Disponible"].sum():
        return "❌ El monto excede el saldo total disponible.", pd.DataFrame(), ""
    
    remanente_por_aplicar = int(monto)
    periodo_destino_str = f"{mes_dest} {anio_dest}"
    desglose_sat = []
    datos_sat_lista = []

    try:
        for idx, row in df_vigentes.iterrows():
            if remanente_por_aplicar <= 0: break
            saldo_anterior = int(row["Saldo_Disponible"])
            saldo_original = int(row.get("Saldo_Original", saldo_anterior))
            usar = min(saldo_anterior, remanente_por_aplicar)
            remanente_nuevo = saldo_anterior - usar
            remanente_por_aplicar -= usar
            folio_limpio = str(row['Num_Operacion']).replace(".0", "")
            tipo_dec = str(row.get("Tipo_Declaracion", "Normal"))
            fecha_pres = str(row.get("Fecha_Presentacion", ""))
            ejercicio_origen = int(row.get("Periodo_Anio", anio_dest))
            periodo_origen = str(row.get("Periodo_Mes", ""))
            nuevo_estatus = "Agotado" if remanente_nuevo == 0 else "Vigente"
            
            supabase.table("saldos_iva").update({
                "saldo_disponible": float(remanente_nuevo), "estatus": nuevo_estatus
            }).eq("id", int(row["ID"])).execute()
            
            payload_historial = {
                "usuario_email": email, "fecha_aplicacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "rfc": rfc, "periodo_origen": f"{periodo_origen} {ejercicio_origen}",
                "num_operacion_origen": folio_limpio, "saldo_anterior": float(saldo_anterior),
                "monto_aplicado": float(usar), "remanente_nuevo": float(remanente_nuevo),
                "periodo_destino": periodo_destino_str
            }
            supabase.table("historial_acreditamientos").insert(payload_historial).execute()
            
            desglose_sat.append({
                "Declaración Destino": periodo_destino_str, "Periodo Origen": f"{periodo_origen} {ejercicio_origen}",
                "Folio SAT": folio_limpio, "Monto Acreditado": f"${usar:,} MXN", "Remanente": f"${remanente_nuevo:,} MXN"
            })

            datos_sat_lista.append(
                f"📌 **DATOS PARA EL SAT (Origen: {periodo_origen} {ejercicio_origen})**:\n"
                f"- **Ejercicio:** {ejercicio_origen}\n- **Periodo:** {periodo_origen}\n"
                f"- **Saldo por aplicar:** ${usar:,} MXN\n- **Tipo de declaración:** {tipo_dec}\n"
                f"- **Número de operación:** {folio_limpio}\n- **Fecha en que se presentó:** {fecha_pres}\n"
                f"- **Monto del saldo a favor original:** ${saldo_original:,} MXN\n"
                f"- **Remanente histórico antes de la aplicación:** ${saldo_anterior:,} MXN\n"
            )

        registrar_log(email, "EJECUCION_FIFO", f"RFC: {rfc} | Aplicado en {periodo_destino_str} | Monto: ${monto} MXN")
        return f"¡Acreditamiento aplicado con éxito!", pd.DataFrame(desglose_sat), "\n\n".join(datos_sat_lista)
    except Exception as e:
        return f"Error al ejecutar: {e}", pd.DataFrame(), ""

def obtener_historial_vista(email, rfc):
    df_hist = cargar_historial(email)
    if df_hist.empty: return pd.DataFrame(), None, gr.update(choices=[], value=None)
    df_cliente = df_hist[df_hist["RFC"] == rfc] if rfc else df_hist
    if df_cliente.empty: return pd.DataFrame(), None, gr.update(choices=[], value=None)
    
    cols = [c for c in ["ID", "Fecha_Aplicacion", "RFC", "Periodo_Origen", "Declaracion_Aplicada_Destino", "Num_Operacion_Origen", "Saldo_Anterior", "Monto_Aplicado", "Remanente_Nuevo"] if c in df_cliente.columns]
    df_disp = df_cliente[cols]
    ruta_excel_hist = exportar_dataframe_excel(df_disp, f"Historial_Acreditamientos_{rfc if rfc else 'General'}")
    ids_hist = df_disp["ID"].tolist()
    upd_ids_h = gr.update(choices=ids_hist, value=ids_hist[0] if ids_hist else None)
    return df_disp, ruta_excel_hist, upd_ids_h

# --- INTERFAZ GRADIO ---
with gr.Blocks(title="Bóveda IVA Pro") as demo:
    
    state_email = gr.State("")
    state_plan = gr.State("")

    # 1. Panel Público (Login + Sistema de Referidos + Planes)
    with gr.Column(visible=True) as panel_login:
        gr.Markdown("""
            <div style="max-width: 480px; margin: 20px auto 10px auto; padding: 20px; background: white; border-radius: 12px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <h2 style="color: #1e3c72; margin-bottom: 5px;">🏛️ Bóveda IVA Pro</h2>
                <p style="color: #64748b; font-size: 0.9rem;">Plataforma inteligente de gestión y acreditamiento de IVA.</p>
            </div>
        """)
        with gr.Row():
            with gr.Column(scale=1): pass
            with gr.Column(scale=2):
                txt_user = gr.Textbox(label="Usuario (Correo)", placeholder="correo@ejemplo.com")
                txt_pass = gr.Textbox(label="Contraseña", type="password")
                btn_ingresar = gr.Button("Iniciar Sesión", variant="primary")
                lbl_msg = gr.Markdown()
            with gr.Column(scale=1): pass

        with gr.Row():
            with gr.Column(scale=1): pass
            with gr.Column(scale=2):
                gr.Markdown("---")
                gr.Markdown("### 🤝 ¿Tienes un código de referido?")
                txt_referido_input = gr.Textbox(label="Ingresa el código de referido de tu colega", placeholder="ej. contador08")
                lbl_referido_info = gr.Markdown("ℹ️ Al contratar un paquete anual con un código de referido válido, recibes **+1 Mes Gratis** y tu colega recibe **+2 Meses Gratis**.")
            with gr.Column(scale=1): pass

        html_tabla_planes_pub = gr.HTML(value=generar_html_tabla_planes(""))

    # 2. Panel Privado (App para usuarios autenticados)
    with gr.Column(visible=False) as panel_app:
        with gr.Row():
            with gr.Column(scale=4):
                html_header = gr.HTML()
            with gr.Column(scale=1, min_width=120):
                btn_logout = gr.Button("🚪 Cerrar Sesión", variant="stop")
        
        with gr.Tabs():
            with gr.TabItem("📊 Resumen y Bóveda"):
                with gr.Row():
                    drop_rfc_resumen = gr.Dropdown(label="Seleccionar RFC del Cliente", choices=[], interactive=True)
                    btn_actualizar_resumen = gr.Button("🔄 Actualizar Datos")
                
                html_metricas = gr.HTML()
                tabla_saldos_resumen = gr.DataFrame(label="Saldos Registrados en la Bóveda")
                
                with gr.Row():
                    file_descargar_resumen = gr.File(label="📥 Descargar Resumen en Excel", interactive=False)

                gr.Markdown("---")
                gr.Markdown("### 🗑️ Gestión / Eliminar Cliente Completo")
                with gr.Row():
                    drop_rfc_eliminar_cliente = gr.Dropdown(label="Seleccionar RFC de Cliente a Eliminar", choices=[], interactive=True)
                    btn_eliminar_cliente = gr.Button("🗑️ Eliminar Cliente Completo", variant="stop")
                lbl_eliminar_cliente_res = gr.Markdown()

                gr.Markdown("---")
                gr.Markdown("### 🗑️ Gestión de Registros Individuales (Bóveda)")
                with gr.Row():
                    drop_id_eliminar_boveda = gr.Dropdown(label="Seleccionar ID de Declaración a Eliminar", choices=[])
                    btn_eliminar_boveda = gr.Button("🗑️ Eliminar Registro Seleccionado", variant="stop")
                lbl_eliminar_boveda_res = gr.Markdown()

            with gr.TabItem("🏛️ Módulo FED (Devoluciones)"):
                gr.Markdown("### 🏛️ Formato Electrónico de Devoluciones — Devolución de IVA")
                with gr.Row():
                    drop_id_fed = gr.Dropdown(label="Seleccionar ID de Saldo a Solicitar en Devolución FED", choices=[])
                    txt_folio_fed = gr.Textbox(label="Folio de Trámite SAT / Registro Único", placeholder="AV2026101899211")
                    date_ingreso_fed = gr.Textbox(label="Fecha de Ingreso SAT", value=datetime.now().strftime("%Y-%m-%d"))
                
                with gr.Row():
                    file_logo_fed = gr.File(label="Subir Logo del Despacho / Empresa (Opcional para PDF)", file_types=[".png", ".jpg", ".jpeg"])
                    txt_obs_fed = gr.Textbox(label="Observaciones o Referencia Interna", placeholder="Trámite de devolución ejercicio 2025")

                with gr.Row():
                    btn_congelar_fed = gr.Button("🔒 Congelar Saldo y Generar Expediente FED (PDF)", variant="primary")
                    file_pdf_fed_descarga = gr.File(label="📄 Descargar / Visualizar Expediente FED (PDF)", interactive=False)
                
                lbl_fed_res = gr.Markdown()

                gr.Markdown("---")
                gr.Markdown("#### ⚖️ Resolución del Trámite FED")
                with gr.Row():
                    rad_resolucion_fed = gr.Radio(choices=["Aprobado / Devuelto por el SAT", "Rechazado / Desistido (Descongelar)"], label="Seleccionar Resultado del SAT", value="Aprobado / Devuelto por el SAT")
                    txt_deposito_sat = gr.Textbox(label="Número de Depósito / Autorización SAT", placeholder="DEP-9821873")
                    chk_confirma_resolucion = gr.Checkbox(label="Confirmo aplicar esta resolución definitiva")
                    btn_resolver_fed = gr.Button("⚙️ Procesar Resolución FED", variant="stop")
                
                lbl_resolucion_res = gr.Markdown()

            with gr.TabItem("📥 Carga de Declaraciones (PDF / Excel)"):
                gr.Markdown("### 1. Carga Individual por PDF del SAT")
                file_pdf = gr.File(label="Subir Declaración PDF del SAT", file_types=[".pdf"])
                with gr.Row():
                    txt_rfc_pdf = gr.Textbox(label="RFC Contribuyente")
                    drop_mes_pdf = gr.Dropdown(label="Periodo (Mes)", choices=["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"], value="Enero")
                    num_anio_pdf = gr.Number(label="Ejercicio (Año)", value=2026, precision=0)
                with gr.Row():
                    drop_tipo_pdf = gr.Dropdown(label="Tipo Declaración", choices=["Normal", "Complementaria - Modificación", "Complementaria - Dejar sin Efecto"], value="Normal")
                    txt_num_op_pdf = gr.Textbox(label="Número de Operación SAT")
                    date_pres_pdf = gr.Textbox(label="Fecha Presentación (YYYY-MM-DD)", value=datetime.now().strftime("%Y-%m-%d"))
                with gr.Row():
                    num_saldo_pdf = gr.Number(label="Saldo a Favor ($)", value=0)
                    chk_mod_pdf = gr.Checkbox(label="Sustituir declaración anterior (si ya existe una para el mismo mes/ejercicio)")
                
                btn_guardar_pdf = gr.Button("💾 Registrar Declaración Individual", variant="primary")
                lbl_guardar_pdf_res = gr.Markdown()

                gr.Markdown("---")
                gr.Markdown("### 2. Carga Masiva para Despachos (vía Excel)")
                with gr.Row():
                    file_plantilla_descarga = gr.File(label="📥 Descargar Plantilla Guía en Excel", value=PLANTILLA_EXCEL_PATH, interactive=False)
                    file_excel_masivo = gr.File(label="📤 Cargar Plantilla Excel de Declaraciones", file_types=[".xlsx", ".xls"])
                
                btn_procesar_masivo = gr.Button("🚀 Importar Declaraciones Masivas a la Bóveda", variant="primary")
                lbl_masivo_res = gr.Markdown()

            with gr.TabItem("⚙️ Motor / Acreditamiento"):
                with gr.Row():
                    drop_rfc_fifo = gr.Dropdown(label="Seleccionar RFC", choices=[], interactive=True)
                    num_monto_fifo = gr.Number(label="Monto a Aplicar ($)")
                with gr.Row():
                    drop_mes_dest = gr.Dropdown(label="Periodo Destino (Mes)", choices=["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"], value="Enero")
                    num_anio_dest = gr.Number(label="Ejercicio Destino (Año)", value=2026, precision=0)
                
                btn_ejecutar_fifo = gr.Button("🚀 Ejecutar Acreditamiento Automático", variant="primary")
                lbl_fifo_res = gr.Markdown()
                
                gr.Markdown("---")
                gr.Markdown("### 📋 Datos Exactos para Llenar el Formulario del SAT")
                txt_datos_sat_guia = gr.Markdown("*Aquí aparecerán los datos detallados tras ejecutar el acreditamiento*")
                tabla_fifo_desglose = gr.DataFrame(label="Desglose Acreditamiento")

            with gr.TabItem("📜 Historial"):
                with gr.Row():
                    drop_rfc_hist = gr.Dropdown(label="Filtrar por RFC", choices=[], interactive=True)
                    btn_ver_hist = gr.Button("🔍 Consultar Historial")
                
                tabla_historial = gr.DataFrame(label="Historial de Acreditamientos")
                file_descargar_historial = gr.File(label="📥 Descargar Historial en Excel", interactive=False)

                gr.Markdown("---")
                gr.Markdown("### 🗑️ Gestión de Historial (Eliminar Acreditamiento)")
                with gr.Row():
                    drop_id_eliminar_hist = gr.Dropdown(label="Seleccionar ID de Historial a Eliminar", choices=[])
                    btn_eliminar_hist = gr.Button("🗑️ Eliminar Movimiento de Historial", variant="stop")
                lbl_eliminar_hist_res = gr.Markdown()

            with gr.TabItem("💳 Planes y Suscripciones"):
                html_vista_pagos_interno = gr.HTML()
                
                gr.Markdown("---")
                gr.Markdown("### 🔒 Cambiar Contraseña")
                with gr.Row():
                    txt_pass_actual = gr.Textbox(label="Contraseña Actual", type="password")
                    txt_pass_nueva = gr.Textbox(label="Nueva Contraseña (mínimo 6 caracteres)", type="password")
                    txt_pass_conf = gr.Textbox(label="Confirmar Nueva Contraseña", type="password")
                btn_cambiar_pass = gr.Button("🔑 Actualizar Contraseña en Supabase", variant="primary")
                lbl_cambiar_pass_res = gr.Markdown()

    # --- EVENTOS Y VÍNCULOS ---
    btn_ingresar.click(
        fn=login_usuario, inputs=[txt_user, txt_pass],
        outputs=[lbl_msg, panel_login, panel_app, html_header, state_email, state_plan]
    ).then(
        fn=inicializar_panel_usuario, inputs=[state_email],
        outputs=[drop_rfc_resumen, drop_rfc_fifo, drop_rfc_hist, drop_rfc_eliminar_cliente, drop_id_fed, html_vista_pagos_interno]
    )

    btn_logout.click(
        fn=logout_usuario, inputs=[],
        outputs=[panel_login, panel_app, state_email, state_plan]
    )

    btn_cambiar_pass.click(
        fn=cambiar_contrasena, inputs=[state_email, txt_pass_actual, txt_pass_nueva, txt_pass_conf],
        outputs=[lbl_cambiar_pass_res]
    )

    txt_referido_input.change(
        fn=actualizar_enlace_referido, inputs=[txt_referido_input],
        outputs=[html_tabla_planes_pub, lbl_referido_info]
    )

    drop_rfc_resumen.change(
        fn=actualizar_vista_resumen, inputs=[state_email, drop_rfc_resumen],
        outputs=[html_metricas, tabla_saldos_resumen, drop_id_fed, file_descargar_resumen, drop_id_fed, drop_id_eliminar_boveda]
    )

    btn_actualizar_resumen.click(
        fn=actualizar_vista_resumen, inputs=[state_email, drop_rfc_resumen],
        outputs=[html_metricas, tabla_saldos_resumen, drop_id_fed, file_descargar_resumen, drop_id_fed, drop_id_eliminar_boveda]
    )

    btn_eliminar_cliente.click(
        fn=eliminar_cliente_completo, inputs=[state_email, drop_rfc_eliminar_cliente],
        outputs=[
            lbl_eliminar_cliente_res, drop_rfc_resumen, drop_rfc_fifo, drop_rfc_hist, 
            drop_rfc_eliminar_cliente, html_metricas, tabla_saldos_resumen, 
            file_descargar_resumen, drop_id_fed, drop_id_eliminar_boveda
        ]
    )

    btn_eliminar_boveda.click(
        fn=eliminar_registro_boveda, inputs=[state_email, drop_id_eliminar_boveda, drop_rfc_resumen],
        outputs=[lbl_eliminar_boveda_res, html_metricas, tabla_saldos_resumen, drop_id_fed, file_descargar_resumen, drop_id_fed, drop_id_eliminar_boveda]
    )

    btn_congelar_fed.click(
        fn=procesar_solicitud_fed, inputs=[state_email, drop_id_fed, txt_folio_fed, date_ingreso_fed, txt_obs_fed, file_logo_fed],
        outputs=[lbl_fed_res, file_pdf_fed_descarga]
    ).then(
        fn=actualizar_vista_resumen, inputs=[state_email, drop_rfc_resumen],
        outputs=[html_metricas, tabla_saldos_resumen, drop_id_fed, file_descargar_resumen, drop_id_fed, drop_id_eliminar_boveda]
    )

    btn_resolver_fed.click(
        fn=resolver_tramite_fed, inputs=[state_email, drop_id_fed, rad_resolucion_fed, txt_deposito_sat, chk_confirma_resolucion],
        outputs=[lbl_resolucion_res]
    ).then(
        fn=actualizar_vista_resumen, inputs=[state_email, drop_rfc_resumen],
        outputs=[html_metricas, tabla_saldos_resumen, drop_id_fed, file_descargar_resumen, drop_id_fed, drop_id_eliminar_boveda]
    )

    file_pdf.change(
        fn=extraer_datos_pdf, inputs=[file_pdf],
        outputs=[txt_rfc_pdf, txt_num_op_pdf, num_saldo_pdf, drop_mes_pdf, num_anio_pdf, date_pres_pdf, drop_tipo_pdf]
    )

    btn_guardar_pdf.click(
        fn=guardar_declaracion_pdf, inputs=[state_email, state_plan, txt_rfc_pdf, drop_mes_pdf, num_anio_pdf, drop_tipo_pdf, txt_num_op_pdf, date_pres_pdf, num_saldo_pdf, chk_mod_pdf],
        outputs=[lbl_guardar_pdf_res, drop_rfc_resumen, drop_rfc_fifo, drop_rfc_hist]
    )

    btn_procesar_masivo.click(
        fn=procesar_carga_masiva_excel, inputs=[state_email, state_plan, file_excel_masivo],
        outputs=[lbl_masivo_res, drop_rfc_resumen, drop_rfc_fifo, drop_rfc_hist]
    )

    btn_ejecutar_fifo.click(
        fn=ejecutar_fifo, inputs=[state_email, drop_rfc_fifo, num_monto_fifo, drop_mes_dest, num_anio_dest],
        outputs=[lbl_fifo_res, tabla_fifo_desglose, txt_datos_sat_guia]
    )

    btn_ver_hist.click(
        fn=obtener_historial_vista, inputs=[state_email, drop_rfc_hist],
        outputs=[tabla_historial, file_descargar_historial, drop_id_eliminar_hist]
    )

    btn_eliminar_hist.click(
        fn=eliminar_registro_historial, inputs=[state_email, drop_id_eliminar_hist, drop_rfc_hist],
        outputs=[lbl_eliminar_hist_res, tabla_historial, file_descargar_historial, drop_id_eliminar_hist]
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port, theme=gr.themes.Soft())
