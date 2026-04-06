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
# ← CAMBIO: eliminada la importación de webdriver_manager
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===========================================
# CONFIGURACIÓN (Usa Variables de Entorno en Koyeb)
# ===========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8400265046:AAHA_qjtya3Gf2kqB-16ODGhKKFeIsjN72E")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "278479819")
URL = "https://outlook.office365.com/book/Atencinalpblico@cancilleria.gov.co/?ismsaljsauthenabled=true"
NOMBRE_SERVICIO = os.environ.get("SERVICIO", "Registro Civil de Nacimiento")
REVISAR_CADA = int(os.environ.get("INTERVALO", 300))
PUERTO = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ===========================================
# SERVIDOR WEB & GLOBALES
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
    except Exception as e:
        logging.error(f"Error Telegram: {e}")

# ===========================================
# LÓGICA DE BÚSQUEDA
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
    options.binary_location = "/usr/bin/chromium"  # ← CAMBIO: de google-chrome a chromium

    driver = None
    try:
        service = Service('/usr/bin/chromedriver')  # ← CAMBIO: driver del sistema, sin webdriver-manager
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 20)
        
        logging.info(f"Iniciando búsqueda para: {NOMBRE_SERVICIO}")
        driver.get(URL)
        time.sleep(10)
        
        # 1. Seleccionar Servicio
        try:
            btn_mas = driver.find_elements(By.XPATH, "//button[contains(text(), 'Mostrar más')]")
            if btn_mas: 
                driver.execute_script("arguments[0].click();", btn_mas[0])
                time.sleep(2)
            titulos = driver.find_elements(By.CSS_SELECTOR, "div.XNuah")
            encontrado = False
            for titulo in titulos:
                if NOMBRE_SERVICIO.lower() in titulo.text.lower():
                    radio = titulo.find_element(By.XPATH, "./ancestor::li//input[@type='radio']")
                    driver.execute_script("arguments[0].click();", radio)
                    encontrado = True
                    break
            
            if not encontrado:
                logging.warning(f"No se encontró el servicio: {NOMBRE_SERVICIO}")
        except Exception as e:
            logging.error(f"Error seleccionando servicio: {e}")
        time.sleep(5)
        
        # 2. Buscar Días Disponibles
        dias = driver.find_elements(By.CSS_SELECTOR, "div.omApa[data-value]")
        dias_disponibles = []
        
        for dia in dias:
            numero = dia.text.strip()
if numero.isdigit() and dia.get_attribute("aria-disabled") != "true":
                dias_disponibles.append(numero)
        
        if dias_disponibles:
            dias_ordenados = sorted(list(set(dias_disponibles)), key=int)
            citas_encontradas_total += 1
            ultimo_estado = f"✅ {len(dias_ordenados)} días hallados"
            
            mensaje = f"<b>🔔 ¡CITAS DISPONIBLES!</b>\n\n"
            mensaje += f"<b>Servicio:</b> {NOMBRE_SERVICIO}\n"
            mensaje += f"<b>✅ Días con citas:</b> {len(dias_ordenados)}\n"
            for d in dias_ordenados:
                mensaje += f"    📆 Día {d}\n"
            mensaje += f"\n🔗 <a href='{URL}'>Reservar ahora</a>"
            enviar_telegram(mensaje)
        else:
            ultimo_estado = "❌ Sin citas disponibles"
            logging.info(ultimo_estado)
    except Exception as e:
        ultimo_estado = f"⚠ Error: {str(e)[:100]}"
        logging.error(f"Error en búsqueda: {e}")
    finally:
        if driver:
            driver.quit()

# ===========================================
# TELEGRAM BOT & RUN
# ===========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = (
        f"🤖 <b>Bot Monitoreando:</b> {NOMBRE_SERVICIO}\n"
        f"🕒 <b>Última revisión:</b> {ultima_verificacion}\n"
        f"📊 <b>Estado:</b> {ultimo_estado}"
    )
    await update.message.reply_text(status_msg, parse_mode="HTML")

async def run_tg():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    while True:
        await asyncio.sleep(3600)

def loop_busqueda():
    time.sleep(10)
    while True:
        buscar_citas()
        time.sleep(REVISAR_CADA)

if name == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PUERTO, debug=False, use_reloader=False), daemon=True).start()
    threading.Thread(target=lambda: asyncio.run(run_tg()), daemon=True).start()
    enviar_telegram(f"🚀 Bot Reiniciado\nServicio: {NOMBRE_SERVICIO}")
    loop_busqueda()
