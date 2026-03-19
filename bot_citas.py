import threading
from flask import Flask
import time
import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from telegram import Bot

# --- Configuración ---
TOKEN = os.environ.get("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "TU_CHAT_ID_AQUI")
URL_CITAS = os.environ.get("URL_CITAS", "https://pagina-de-citas.com")
INTERVALO_MINUTOS = 5
PUERTO = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Servidor Web Flask (Para mantener el bot vivo y hacer health checks) ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

def run_web_server():
    app.run(host="0.0.0.0", port=PUERTO, debug=False, use_reloader=False)

# --- Lógica del Bot con Selenium ---
def verificar_cita():
    logging.info("🌐 Iniciando verificación de cita...")
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1280,720")

        driver = webdriver.Chrome(options=chrome_options)
        driver.get(URL_CITAS)

        # --- ¡AQUÍ VA TU LÓGICA DE DETECCIÓN ESPECÍFICA! ---
        # Adapta esto a cómo se ve la página de citas
        if "no hay citas" not in driver.page_source.lower():
            mensaje = f"🔔 ¡CITA DISPONIBLE! {URL_CITAS}"
            Bot(token=TOKEN).send_message(chat_id=CHAT_ID, text=mensaje)
            logging.info("✅ Cita disponible.")
        else:
            logging.info("❌ No hay citas.")
        # --- FIN DE TU LÓGICA ---

    except Exception as e:
        logging.error(f"🔥 Error en verificación: {e}")
    finally:
        if driver:
            driver.quit()
            logging.info("🧹 Navegador cerrado.")

def bucle_principal():
    logging.info("🤖 Bucle principal iniciado.")
    while True:
        verificar_cita()
        logging.info(f"⏱️ Esperando {INTERVALO_MINUTOS} minutos...")
        time.sleep(INTERVALO_MINUTOS * 60)

# --- Punto de entrada principal ---
if __name__ == "__main__":
    # Iniciamos el servidor web en un hilo separado
    hilo_web = threading.Thread(target=run_web_server, daemon=True)
    hilo_web.start()
    logging.info("✅ Servidor web iniciado en segundo plano.")

    # Ejecutamos el bucle principal del bot
    bucle_principal()