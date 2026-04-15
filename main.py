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
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===========================================
# CONFIGURACIÓN
# ===========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8400265046:AAHA_qjtya3Gf2kqB-16ODGhKKFeIsjN72E")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1003744855469") 
URL = "https://outlook.office365.com/book/Atencinalpblico@cancilleria.gov.co/?ismsaljsauthenabled=true"
NOMBRE_SERVICIO = os.environ.get("SERVICIO", "Registro Civil de Nacimiento")
REVISAR_CADA = int(os.environ.get("INTERVALO", 300))
PUERTO = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ===========================================
# SERVIDOR WEB
# ===========================================
app = Flask(__name__)
ultima_verificacion = "Nunca"
ultimo_estado = "Iniciando..."
citas_encontradas_total = 0

@app.route('/')
def health(): 
    return f"Bot Activo. Última revisión: {ultima_verificacion}. Estado: {ultimo_estado}", 200

def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}, timeout=10)
        logging.info("✅ Mensaje enviado a Telegram")
    except Exception as e:
        logging.error(f"Error Telegram: {e}")

# ===========================================
# LÓGICA DE BÚSQUEDA CORREGIDA
# ===========================================
def buscar_citas():
    global ultima_verificacion, ultimo_estado, citas_encontradas_total
    ultima_verificacion = time.strftime('%Y-%m-%d %H:%M:%S')
    
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.binary_location = "/usr/bin/google-chrome"
    
    # Deshabilitar logs innecesarios de Chrome
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    driver = None
    try:
        # Usar ChromeDriver instalado en el sistema
        service = Service("/usr/local/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 20)
        
        logging.info(f"🔍 Iniciando búsqueda para: {NOMBRE_SERVICIO}")
        driver.get(URL)
        time.sleep(8)
        
        # ========== 1. SELECCIONAR SERVICIO CORRECTAMENTE ==========
        try:
            # Primero, hacer click en "Mostrar más servicios" si existe
            try:
                boton_mostrar = driver.find_element(By.XPATH, "//button[contains(text(), 'Mostrar más servicios')]")
                driver.execute_script("arguments[0].click();", boton_mostrar)
                logging.info("✅ Click en 'Mostrar más servicios'")
                time.sleep(3)
            except:
                logging.info("No se encontró botón 'Mostrar más servicios'")
            
            # Buscar el servicio por el texto EXACTO
            servicios = driver.find_elements(By.CSS_SELECTOR, "div.XNuah")
            servicio_encontrado = False
            
            for servicio in servicios:
                texto_servicio = servicio.text.strip()
                logging.info(f"Servicio encontrado: '{texto_servicio}'")
                
                # Comparación exacta
                if texto_servicio == NOMBRE_SERVICIO:
                    logging.info(f"✅ Servicio exacto encontrado: '{texto_servicio}'")
                    # Buscar el radio button asociado
                    radio = servicio.find_element(By.XPATH, "./ancestor::li//input[@type='radio']")
                    driver.execute_script("arguments[0].click();", radio)
                    servicio_encontrado = True
                    logging.info(f"✅ Servicio seleccionado: {NOMBRE_SERVICIO}")
                    break
            
            if not servicio_encontrado:
                # Intentar con búsqueda parcial si no encuentra exacto
                for servicio in servicios:
                    if NOMBRE_SERVICIO.lower() in servicio.text.lower():
                        logging.info(f"✅ Servicio parcial encontrado: '{servicio.text}'")
                        radio = servicio.find_element(By.XPATH, "./ancestor::li//input[@type='radio']")
                        driver.execute_script("arguments[0].click();", radio)
                        servicio_encontrado = True
                        logging.info(f"✅ Servicio seleccionado (parcial): {servicio.text}")
                        break
            
            if not servicio_encontrado:
                logging.error(f"❌ No se encontró el servicio: {NOMBRE_SERVICIO}")
                ultimo_estado = f"Servicio '{NOMBRE_SERVICIO}' no encontrado"
                return
                
        except Exception as e:
            logging.error(f"Error seleccionando servicio: {e}")
            ultimo_estado = f"Error seleccionando servicio: {str(e)[:50]}"
            return
        
        # Esperar que cargue el calendario
        time.sleep(5)
        
        # ========== 2. BUSCAR DÍAS DISPONIBLES ==========
        # Buscar todos los botones de días
        dias = driver.find_elements(By.CSS_SELECTOR, "div.omApa[data-value]")
        logging.info(f"Total días encontrados en calendario: {len(dias)}")
        
        dias_disponibles = []
        
        for dia in dias:
            try:
                numero = dia.text.strip()
                # Verificar que sea un número (día del mes)
                if numero and numero.isdigit():
                    # Verificar si está habilitado (NO tiene aria-disabled="true")
                    aria_disabled = dia.get_attribute("aria-disabled")
                    if aria_disabled != "true":
                        dias_disponibles.append(numero)
                        logging.info(f"📆 Día disponible encontrado: {numero}")
            except Exception as e:
                continue
        
        # Eliminar duplicados y ordenar
        if dias_disponibles:
            dias_ordenados = sorted(list(set(dias_disponibles)), key=int)
            citas_encontradas_total += 1
            ultimo_estado = f"✅ {len(dias_ordenados)} días con citas"
            
            mensaje = f"<b>🔔 ¡CITAS DISPONIBLES!</b>\n\n"
            mensaje += f"<b>Servicio:</b> {NOMBRE_SERVICIO}\n"
            mensaje += f"<b>📅 Fecha:</b> {ultima_verificacion}\n"
            mensaje += f"<b>✅ Días con citas:</b> {len(dias_ordenados)}\n"
            for d in dias_ordenados:
                mensaje += f"   📆 Día {d}\n"
            mensaje += f"\n🔗 <a href='{URL}'>Reservar ahora</a>"
            
            enviar_telegram(mensaje)
            logging.info(f"🎉 CITAS ENCONTRADAS: {dias_ordenados}")
        else:
            ultimo_estado = "❌ Sin citas disponibles"
            logging.info("❌ No hay citas disponibles en este momento")
            
    except Exception as e:
        ultimo_estado = f"⚠ Error: {str(e)[:100]}"
        logging.error(f"Error en búsqueda: {e}")
    finally:
        if driver:
            driver.quit()

# ===========================================
# TELEGRAM BOT
# ===========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = (
        f"🤖 <b>Bot de Citas - Estado</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 <b>Servicio:</b> {NOMBRE_SERVICIO}\n"
        f"🕒 <b>Última revisión:</b> {ultima_verificacion}\n"
        f"📊 <b>Estado:</b> {ultimo_estado}\n"
        f"🔄 <b>Intervalo:</b> {REVISAR_CADA} segundos"
    )
    await update.message.reply_text(status_msg, parse_mode="HTML")

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /check para buscar citas manualmente"""
    await update.message.reply_text("🔍 Buscando citas... por favor espera.")
    # Ejecutar búsqueda en un hilo separado para no bloquear
    threading.Thread(target=buscar_citas, daemon=True).start()

async def run_tg():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check", check_command))
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    while True:
        await asyncio.sleep(3600)

def loop_busqueda():
    time.sleep(15)  # Esperar a que todo esté listo
    enviar_telegram(f"🚀 Bot Iniciado\n📱 Servicio: {NOMBRE_SERVICIO}\n🔄 Intervalo: {REVISAR_CADA}s")
    while True:
        try:
            buscar_citas()
        except Exception as e:
            logging.error(f"Error en loop: {e}")
        time.sleep(REVISAR_CADA)

# ===========================================
# MAIN
# ===========================================
if __name__ == "__main__":
    logging.info("="*50)
    logging.info("🤖 BOT DE CITAS INICIADO")
    logging.info(f"📱 Servicio: {NOMBRE_SERVICIO}")
    logging.info(f"🔄 Revisando cada {REVISAR_CADA} segundos")
    logging.info("="*50)
    
    # Hilo para Flask
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PUERTO, debug=False, use_reloader=False), daemon=True).start()
    
    # Hilo para Telegram
    threading.Thread(target=lambda: asyncio.run(run_tg()), daemon=True).start()
    
    # Loop principal
    loop_busqueda()
