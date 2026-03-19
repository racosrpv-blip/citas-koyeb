import threading
from flask import Flask
import time
import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Bot

# ===========================================
# CONFIGURACIÓN (cambia estos valores)
# ===========================================
# Puedes ponerlos directamente aquí o usar variables de entorno (recomendado)
TOKEN = os.environ.get("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "TU_CHAT_ID_AQUI")
URL_CITAS = os.environ.get("URL_CITAS", "https://pagina-de-citas.com")
INTERVALO_MINUTOS = int(os.environ.get("INTERVALO", 5))
PUERTO = int(os.environ.get("PORT", 8080))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ===========================================
# SERVIDOR WEB (para health checks de Koyeb)
# ===========================================
app = Flask(__name__)

@app.route('/')
def health_check():
    """Endpoint que Koyeb usa para verificar que la app está viva"""
    return "Bot de citas funcionando!", 200

@app.route('/health')
def health():
    return "OK", 200

def run_web_server():
    """Ejecuta el servidor Flask en un puerto específico"""
    app.run(host="0.0.0.0", port=PUERTO, debug=False, use_reloader=False)

# ===========================================
# BOT DE CITAS
# ===========================================
class BotCitas:
    def __init__(self):
        self.bot = Bot(token=TOKEN)
        self.chat_id = CHAT_ID
        self.url = URL_CITAS
        self.intervalo = INTERVALO_MINUTOS
        
    def crear_driver(self):
        """Configura Chrome con opciones para servidor"""
        chrome_options = Options()
        
        # Opciones esenciales para servidor
        chrome_options.add_argument("--headless=new")  # Modo sin interfaz gráfica
        chrome_options.add_argument("--no-sandbox")    # Necesario en servidores
        chrome_options.add_argument("--disable-dev-shm-usage")  # Evita problemas de memoria
        chrome_options.add_argument("--disable-gpu")   # Desactiva GPU
        chrome_options.add_argument("--window-size=1280,720")
        
        # Opciones adicionales para ahorrar memoria
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("--disable-software-rasterizer")
        
        # Usar webdriver-manager para obtener ChromeDriver automáticamente
        service = Service(ChromeDriverManager().install())
        
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        return driver
    
    def verificar_disponibilidad(self):
        """Verifica si hay citas disponibles"""
        driver = None
        try:
            logging.info("🌐 Iniciando Chrome...")
            driver = self.crear_driver()
            
            logging.info(f"📡 Accediendo a {self.url}")
            driver.get(self.url)
            
            # Esperar a que cargue la página
            time.sleep(5)
            
            # Obtener el contenido de la página
            contenido = driver.page_source.lower()
            
            # ===========================================
            # 🔴 ADAPTA ESTA LÓGICA A TU PÁGINA DE CITAS
            # ===========================================
            # Ejemplo 1: Buscar texto que indique NO disponibilidad
            if "no hay citas disponibles" in contenido:
                logging.info("❌ No hay citas disponibles")
                return False
            else:
                mensaje = f"🔔 ¡POSIBLE CITA DISPONIBLE! Revisa: {self.url}"
                self.bot.send_message(chat_id=self.chat_id, text=mensaje)
                logging.info("✅ ¡Alerta enviada!")
                return True
                
            # Ejemplo 2: Buscar texto que indique SÍ disponibilidad (descomenta si aplica)
            # if "cita disponible" in contenido or "reservar cita" in contenido:
            #     mensaje = f"🔔 ¡CITA DISPONIBLE! {self.url}"
            #     self.bot.send_message(chat_id=self.chat_id, text=mensaje)
            #     logging.info("✅ ¡Cita encontrada!")
            #     return True
            # else:
            #     logging.info("❌ No hay citas")
            #     return False
            # ===========================================
            
        except Exception as e:
            error_msg = f"Error en verificación: {str(e)}"
            logging.error(f"🔥 {error_msg}")
            try:
                self.bot.send_message(
                    chat_id=self.chat_id,
                    text=f"⚠️ Error en el bot: {error_msg[:100]}"
                )
            except:
                pass
            return False
            
        finally:
            if driver:
                driver.quit()
                logging.info("🧹 Chrome cerrado, memoria liberada")
    
    def ejecutar(self):
        """Bucle principal que se ejecuta cada X minutos"""
        logging.info("🤖 Bot de citas iniciado")
        
        # Enviar mensaje de inicio
        try:
            self.bot.send_message(
                chat_id=self.chat_id,
                text="✅ Bot de citas desplegado en Koyeb"
            )
        except:
            pass
        
        contador = 0
        while True:
            contador += 1
            logging.info(f"🔍 Verificación #{contador}")
            
            self.verificar_disponibilidad()
            
            logging.info(f"⏱️ Esperando {self.intervalo} minutos...")
            time.sleep(self.intervalo * 60)

# ===========================================
# PUNTO DE ENTRADA PRINCIPAL
# ===========================================
if __name__ == "__main__":
    # 1. Iniciar servidor web en un hilo separado (obligatorio para Koyeb)
    hilo_web = threading.Thread(target=run_web_server, daemon=True)
    hilo_web.start()
    logging.info(f"✅ Servidor web iniciado en puerto {PUERTO}")
    
    # 2. Pequeña pausa para que el servidor arranque
    time.sleep(2)
    
    # 3. Iniciar el bot
    bot = BotCitas()
    bot.ejecutar()
