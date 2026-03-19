import threading
from flask import Flask
import time
import os
import logging
import requests
import asyncio
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===========================================
# CONFIGURACIÓN - VARIABLES DE ENTORNO
# ===========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
URL = os.environ.get("URL_CITAS", "https://outlook.office365.com/book/Atencinalpblico@cancilleria.gov.co/?ismsaljsauthenabled=true")
NOMBRE_SERVICIO = os.environ.get("SERVICIO", "Autenticación de copia")
REVISAR_CADA = int(os.environ.get("INTERVALO", 300))  # segundos
PUERTO = int(os.environ.get("PORT", 8080))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ===========================================
# SERVIDOR WEB (health checks)
# ===========================================
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot de citas funcionando!", 200

@app.route('/health')
def health():
    return "OK", 200

def run_web_server():
    app.run(host="0.0.0.0", port=PUERTO, debug=False, use_reloader=False)

# ===========================================
# BOT DE TELEGRAM (con comandos)
# ===========================================

# Variable global para saber cuándo fue la última verificación
ultima_verificacion = "Nunca"
ultimo_estado = "Sin verificaciones"
citas_encontradas_total = 0

# Comando /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde al comando /start con información del bot"""
    user = update.effective_user
    mensaje = (
        f"🤖 <b>Bot de Citas - Cónsulado de Colombia</b>\n\n"
        f"👋 ¡Hola {user.first_name}!\n\n"
        f"📋 <b>Servicio monitoreado:</b> {NOMBRE_SERVICIO}\n"
        f"🕒 <b>Última verificación:</b> {ultima_verificacion}\n"
        f"📊 <b>Estado:</b> {ultimo_estado}\n"
        f"✅ <b>Citas encontradas:</b> {citas_encontradas_total}\n\n"
        f"⏱️ Revisando cada {REVISAR_CADA//60} minutos\n"
        f"🔍 <b>Live:</b> 🟢 Bot activo"
    )
    await update.message.reply_text(mensaje, parse_mode='HTML')

# Comando /status (opcional, para más detalles)
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el estado detallado"""
    mensaje = (
        f"📊 <b>ESTADO DETALLADO</b>\n\n"
        f"🕒 Última verificación: {ultima_verificacion}\n"
        f"📌 Último estado: {ultimo_estado}\n"
        f"✅ Total citas encontradas: {citas_encontradas_total}\n"
        f"🔧 Servicio: {NOMBRE_SERVICIO}\n"
        f"🌐 URL: {URL[:50]}...\n"
        f"⏱️ Intervalo: {REVISAR_CADA//60} minutos\n"
        f"💡 Memoria: Activo"
    )
    await update.message.reply_text(mensaje, parse_mode='HTML')

# Función para actualizar el estado global
def actualizar_estado(verificacion, estado, encontro_cita=False):
    global ultima_verificacion, ultimo_estado, citas_encontradas_total
    ultima_verificacion = verificacion
    ultimo_estado = estado
    if encontro_cita:
        citas_encontradas_total += 1

# ===========================================
# FUNCIONES DE UTILIDAD
# ===========================================

def enviar_telegram(mensaje):
    """Envía un mensaje a Telegram (síncrono)"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("⚠ Telegram no configurado")
        return
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        datos = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": mensaje,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=datos, timeout=10)
        if response.status_code == 200:
            logging.info("✅ Notificación enviada a Telegram")
        else:
            logging.error(f"❌ Error Telegram: {response.status_code}")
    except Exception as e:
        logging.error(f"❌ Error enviando a Telegram: {e}")

def obtener_fecha_actual():
    """Retorna la fecha actual formateada"""
    return time.strftime('%Y-%m-%d %H:%M:%S')

# ===========================================
# FUNCIÓN PRINCIPAL DE BÚSQUEDA
# ===========================================

def buscar_citas():
    global ultima_verificacion, ultimo_estado
    
    fecha_actual = obtener_fecha_actual()
    ultima_verificacion = fecha_actual
    logging.info(f"\n{'='*50}")
    logging.info(f"🔍 REVISIÓN: {fecha_actual}")
    logging.info(f"{'='*50}")
    
    # Configurar Chrome para servidor
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    driver = None
    try:
        # Iniciar driver
        logging.info("🌐 Iniciando Chrome...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        wait = WebDriverWait(driver, 15)
        
        # ========== PASO 1: CARGAR PÁGINA ==========
        logging.info(f"📡 Accediendo a URL...")
        driver.get(URL)
        time.sleep(5)
        
        # ========== PASO 2: MOSTRAR MÁS SERVICIOS ==========
        logging.info("🔘 Buscando 'Mostrar más servicios'...")
        try:
            boton = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(text(), 'Mostrar más servicios')]"
            )))
            driver.execute_script("arguments[0].click();", boton)
            logging.info("   ✅ Clic en 'Mostrar más servicios'")
            time.sleep(2)
        except:
            try:
                boton = driver.find_element(By.CSS_SELECTOR, "button.OM013")
                driver.execute_script("arguments[0].click();", boton)
                logging.info("   ✅ Clic en botón 'Mostrar más' (selector alternativo)")
                time.sleep(2)
            except:
                logging.warning("   ⚠ No se encontró el botón 'Mostrar más servicios'")
        
        # ========== PASO 3: SELECCIONAR SERVICIO ==========
        logging.info(f"🎯 Buscando servicio: '{NOMBRE_SERVICIO}'")
        
        servicio_seleccionado = False
        
        # Buscar por título exacto
        try:
            titulos = driver.find_elements(By.CSS_SELECTOR, "div.XNuah")
            for titulo in titulos:
                if titulo.text.strip() == NOMBRE_SERVICIO:
                    logging.info(f"   ✅ Encontrado título: '{titulo.text}'")
                    radio = titulo.find_element(By.XPATH, "./ancestor::li//input[@type='radio']")
                    driver.execute_script("arguments[0].click();", radio)
                    logging.info(f"   ✅ Servicio seleccionado")
                    servicio_seleccionado = True
                    break
        except Exception as e:
            logging.debug(f"   Error: {e}")
        
        if not servicio_seleccionado:
            ultimo_estado = f"❌ Servicio '{NOMBRE_SERVICIO}' no encontrado"
            logging.error(ultimo_estado)
            return
        
        time.sleep(4)
        
        # ========== PASO 4: BUSCAR DÍAS HABILITADOS ==========
        logging.info("📅 Buscando días disponibles...")
        time.sleep(3)
        
        dias_habilitados = []
        dias = driver.find_elements(By.CSS_SELECTOR, "div.omApa[data-value]")
        
        for dia in dias:
            try:
                numero = dia.text.strip()
                if numero and numero.isdigit():
                    aria_disabled = dia.get_attribute("aria-disabled")
                    if aria_disabled != "true":
                        dias_habilitados.append({
                            'elemento': dia,
                            'numero': numero,
                            'fecha': dia.get_attribute("data-value")
                        })
            except:
                continue
        
        if not dias_habilitados:
            ultimo_estado = "❌ No hay días con citas"
            logging.info(ultimo_estado)
            return
        
        logging.info(f"✅ DÍAS CON CITAS: {len(dias_habilitados)}")
        
        # ========== PASO 5: VERIFICAR HORAS ==========
        logging.info(f"⏰ Verificando horas...")
        
        citas_encontradas = False
        dias_con_horas = []
        
        for dia_info in dias_habilitados[:3]:
            try:
                logging.info(f"   📅 Probando día {dia_info['numero']}")
                driver.execute_script("arguments[0].click();", dia_info['elemento'])
                time.sleep(3)
                
                horas = []
                selectores = [
                    "div[role='button'] span",
                    "button span",
                    ".fGGgr",
                    "[class*='time'] span"
                ]
                
                for selector in selectores:
                    try:
                        elementos = driver.find_elements(By.CSS_SELECTOR, selector)
                        for elem in elementos:
                            texto = elem.text.strip()
                            if texto and (':' in texto or 'AM' in texto or 'PM' in texto):
                                if len(texto) < 20 and texto not in horas:
                                    horas.append(texto)
                    except:
                        continue
                
                if horas:
                    citas_encontradas = True
                    dias_con_horas.append({
                        'dia': dia_info['numero'],
                        'horas': sorted(horas)[:3]
                    })
                    logging.info(f"      ✅ {len(horas)} horarios")
                else:
                    logging.info(f"      ❌ Sin horas")
                    
            except Exception as e:
                logging.debug(f"      Error: {e}")
                continue
        
        # ========== PASO 6: NOTIFICAR ==========
        if citas_encontradas:
            ultimo_estado = f"✅ CITAS DISPONIBLES ({len(dias_con_horas)} días)"
            mensaje = f"<b>🔔 ¡CITAS DISPONIBLES!</b>\n\n"
            mensaje += f"<b>Servicio:</b> {NOMBRE_SERVICIO}\n"
            mensaje += f"<b>Fecha:</b> {fecha_actual}\n\n"
            
            for item in dias_con_horas:
                horas_str = ', '.join(item['horas'])
                mensaje += f"📆 Día {item['dia']}: {horas_str}\n"
            
            mensaje += f"\n🔗 <a href='{URL}'>Reservar ahora</a>"
            
            enviar_telegram(mensaje)
            actualizar_estado(fecha_actual, ultimo_estado, encontro_cita=True)
            logging.info("🎉 ¡CITAS DISPONIBLES ENCONTRADAS! 🎉")
        else:
            ultimo_estado = "❌ Sin citas disponibles"
            actualizar_estado(fecha_actual, ultimo_estado)
            logging.info("✘ No se encontraron citas disponibles")
    
    except Exception as e:
        ultimo_estado = f"⚠ Error: {str(e)[:50]}"
        logging.error(f"⚠ Error general: {e}")
        actualizar_estado(fecha_actual, ultimo_estado)
    
    finally:
        if driver:
            driver.quit()
            logging.info("🧹 Chrome cerrado")

# ===========================================
# CONFIGURACIÓN DEL BOT DE TELEGRAM
# ===========================================

def run_telegram_bot():
    """Ejecuta el bot de Telegram en un hilo separado"""
    if not TELEGRAM_TOKEN:
        logging.error("❌ TELEGRAM_TOKEN no configurado")
        return
    
    # Crear la aplicación
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Agregar handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # Iniciar el bot
    logging.info("🤖 Bot de Telegram iniciado (polling)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# ===========================================
# PROGRAMA PRINCIPAL
# ===========================================

if __name__ == "__main__":
    # Iniciar servidor web
    hilo_web = threading.Thread(target=run_web_server, daemon=True)
    hilo_web.start()
    logging.info(f"✅ Servidor web iniciado en puerto {PUERTO}")
    
    # Iniciar bot de Telegram en otro hilo
    hilo_telegram = threading.Thread(target=run_telegram_bot, daemon=True)
    hilo_telegram.start()
    logging.info("✅ Hilo de Telegram iniciado")
    
    # Mostrar configuración
    logging.info("="*60)
    logging.info("🤖 BOT DE CITAS - VERSIÓN KOYEB")
    logging.info("="*60)
    logging.info(f"📋 CONFIGURACIÓN:")
    logging.info(f"   • Servicio: '{NOMBRE_SERVICIO}'")
    logging.info(f"   • Revisando cada: {REVISAR_CADA//60} minutos")
    logging.info(f"   • Telegram: ✅ ACTIVADO")
    logging.info("="*60)
    
    # Enviar mensaje de inicio
    enviar_telegram(f"🤖 Bot iniciado en Koyeb\nMonitoreando: {NOMBRE_SERVICIO}\nUsa /start para ver estado")
    
    # Bucle principal de monitoreo
    contador = 0
    while True:
        contador += 1
        logging.info(f"\n{'#'*60}")
        logging.info(f"# CICLO DE BÚSQUEDA #{contador}")
        logging.info(f"{'#'*60}")
        
        buscar_citas()
        
        logging.info(f"⏳ Esperando {REVISAR_CADA} segundos...")
        time.sleep(REVISAR_CADA)
