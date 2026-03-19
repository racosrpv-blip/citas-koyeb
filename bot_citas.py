import threading
from flask import Flask
import time
import os
import logging
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio

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
# VARIABLES GLOBALES
# ===========================================
ultima_verificacion = "Nunca"
ultimo_estado = "Sin verificaciones"
citas_encontradas_total = 0

# ===========================================
# FUNCIONES DE UTILIDAD
# ===========================================

def enviar_telegram(mensaje):
    """Envía un mensaje a Telegram usando requests (síncrono)"""
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
    return time.strftime('%Y-%m-%d %H:%M:%S')

def actualizar_estado(verificacion, estado, encontro_cita=False):
    global ultima_verificacion, ultimo_estado, citas_encontradas_total
    ultima_verificacion = verificacion
    ultimo_estado = estado
    if encontro_cita:
        citas_encontradas_total += 1

# ===========================================
# COMANDOS DE TELEGRAM
# ===========================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde al comando /start"""
    user = update.effective_user
    nombre_usuario = user.first_name if user.first_name else "Usuario"
    
    mensaje = (
        f"🤖 Bot de Citas - Cónsulado de Colombia\n\n"
        f"👋 ¡Hola {nombre_usuario}!\n\n"
        f"📋 Servicio monitoreado: {NOMBRE_SERVICIO}\n"
        f"🕒 Última verificación: {ultima_verificacion}\n"
        f"📊 Estado: {ultimo_estado}\n"
        f"✅ Citas encontradas: {citas_encontradas_total}\n\n"
        f"⏱️ Revisando cada {REVISAR_CADA//60} minutos\n"
        f"🔍 Live: 🟢 Bot activo (corriendo en Koyeb)"
    )
    await update.message.reply_text(mensaje)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = (
        f"📊 ESTADO DETALLADO\n\n"
        f"🕒 Última verificación: {ultima_verificacion}\n"
        f"📌 Último estado: {ultimo_estado}\n"
        f"✅ Total citas encontradas: {citas_encontradas_total}\n"
        f"🔧 Servicio: {NOMBRE_SERVICIO}"
    )
    await update.message.reply_text(mensaje)

# ===========================================
# CONFIGURACIÓN DEL BOT DE TELEGRAM
# ===========================================

async def telegram_bot_main():
    """Versión asíncrona del bot de Telegram"""
    if not TELEGRAM_TOKEN:
        logging.error("❌ TELEGRAM_TOKEN no configurado")
        return
    
    # Crear aplicación
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Agregar handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # Inicializar
    await application.initialize()
    await application.start()
    
    # Iniciar polling
    logging.info("🤖 Bot de Telegram iniciado (polling)")
    await application.updater.start_polling()
    
    # Mantener vivo
    while True:
        await asyncio.sleep(3600)  # 1 hora

def run_telegram_bot():
    """Ejecuta el bot en un hilo con su propio event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(telegram_bot_main())

# ===========================================
# FUNCIÓN PRINCIPAL DE BÚSQUEDA
# ===========================================

def buscar_citas():
    global ultima_verificacion, ultimo_estado
    
    fecha_actual = obtener_fecha_actual()
    ultima_verificacion = fecha_actual
    logging.info(f"\n{'='*60}")
    logging.info(f"🔍 REVISIÓN: {fecha_actual}")
    
    # Configurar Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,720")
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        wait = WebDriverWait(driver, 15)
        
        # Cargar página
        driver.get(URL)
        time.sleep(5)
        
        # Click en "Mostrar más"
        try:
            boton = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(text(), 'Mostrar más servicios')]"
            )))
            driver.execute_script("arguments[0].click();", boton)
            time.sleep(2)
        except:
            pass
        
        # Seleccionar servicio
        try:
            titulos = driver.find_elements(By.CSS_SELECTOR, "div.XNuah")
            for titulo in titulos:
                if titulo.text.strip() == NOMBRE_SERVICIO:
                    radio = titulo.find_element(By.XPATH, "./ancestor::li//input[@type='radio']")
                    driver.execute_script("arguments[0].click();", radio)
                    break
        except Exception as e:
            ultimo_estado = f"❌ Servicio no encontrado"
            actualizar_estado(fecha_actual, ultimo_estado)
            return
        
        time.sleep(4)
        
        # Buscar días
        dias = driver.find_elements(By.CSS_SELECTOR, "div.omApa[data-value]")
        dias_habilitados = []
        
        for dia in dias:
            try:
                numero = dia.text.strip()
                if numero and numero.isdigit():
                    aria_disabled = dia.get_attribute("aria-disabled")
                    if aria_disabled != "true":
                        dias_habilitados.append(dia)
            except:
                continue
        
        if not dias_habilitados:
            ultimo_estado = "❌ No hay días con citas"
            actualizar_estado(fecha_actual, ultimo_estado)
            return
        
        logging.info(f"✅ DÍAS CON CITAS: {len(dias_habilitados)}")
        
        # Verificar horas
        citas_encontradas = False
        for dia in dias_habilitados[:3]:
            driver.execute_script("arguments[0].click();", dia)
            time.sleep(3)
            
            # Buscar horas
            horas = driver.find_elements(By.CSS_SELECTOR, "div[role='button'] span")
            if horas:
                citas_encontradas = True
                break
        
        if citas_encontradas:
            ultimo_estado = "✅ CITAS DISPONIBLES"
            enviar_telegram(f"🔔 ¡CITAS DISPONIBLES!\n{NOMBRE_SERVICIO}\n{URL}")
            actualizar_estado(fecha_actual, ultimo_estado, encontro_cita=True)
        else:
            ultimo_estado = "❌ Sin citas disponibles"
            actualizar_estado(fecha_actual, ultimo_estado)
    
    except Exception as e:
        ultimo_estado = f"⚠ Error: {str(e)[:50]}"
        logging.error(f"⚠ Error: {e}")
        actualizar_estado(fecha_actual, ultimo_estado)
    
    finally:
        if driver:
            driver.quit()

# ===========================================
# PROGRAMA PRINCIPAL
# ===========================================

if __name__ == "__main__":
    # Servidor web
    threading.Thread(target=run_web_server, daemon=True).start()
    logging.info(f"✅ Servidor web iniciado")
    
    # Bot de Telegram (en su propio hilo)
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    logging.info("✅ Hilo de Telegram iniciado")
    
    time.sleep(3)
    
    # Mensaje de inicio
    enviar_telegram(f"🤖 Bot iniciado en Koyeb\nMonitoreando: {NOMBRE_SERVICIO}\nUsa /start para ver estado")
    
    # Bucle principal
    contador = 0
    while True:
        contador += 1
        logging.info(f"\n🔍 CICLO #{contador}")
        buscar_citas()
        logging.info(f"⏳ Esperando {REVISAR_CADA//60} minutos...")
        time.sleep(REVISAR_CADA)
