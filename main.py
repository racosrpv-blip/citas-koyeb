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
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio

# ===========================================
# CONFIGURACIÓN
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
def health(): return "Bot Activo", 200

def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        logging.error(f"Error Telegram: {e}")

# ===========================================
# LÓGICA DE BÚSQUEDA (CORREGIDA PARA LINUX)
# ===========================================
def buscar_citas():
    global ultima_verificacion, ultimo_estado, citas_encontradas_total
    ultima_verificacion = time.strftime('%Y-%m-%d %H:%M:%S')
    
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.binary_location = "/usr/bin/google-chrome" # Ruta en Docker

    driver = None
    try:
        # En Docker usamos el driver del sistema directamente
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 20)
        
        driver.get(URL)
        time.sleep(8)
        
        # 1. Seleccionar Servicio
        try:
            # Click en mostrar más si existe
            btn_mas = driver.find_elements(By.XPATH, "//button[contains(text(), 'Mostrar más')]")
            if btn_mas: driver.execute_script("arguments[0].click();", btn_mas[0])
            time.sleep(2)

            titulos = driver.find_elements(By.CSS_SELECTOR, "div.XNuah")
            for titulo in titulos:
                if NOMBRE_SERVICIO.lower() in titulo.text.lower():
                    radio = titulo.find_element(By.XPATH, "./ancestor::li//input[@type='radio']")
                    driver.execute_script("arguments[0].click();", radio)
                    break
        except: pass

        time.sleep(5)
        
        # 2. Buscar Días (Tu lógica local que funciona)
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

    except Exception as e:
        ultimo_estado = f"⚠ Error: {str(e)[:50]}"
        logging.error(f"Error en búsqueda: {e}")
    finally:
        if driver: driver.quit()

# ===========================================
# TELEGRAM BOT & RUN
# ===========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🤖 Bot Monitoreando: {NOMBRE_SERVICIO}\nEstado: {ultimo_estado}")

async def run_tg():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PUERTO), daemon=True).start()
    threading.Thread(target=lambda: asyncio.run(run_tg()), daemon=True).start()
    
    enviar_telegram("🚀 Bot Reiniciado y Monitoreando...")
    while True:
        buscar_citas()
        time.sleep(REVISAR_CADA)
