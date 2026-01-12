import logging
import logging.handlers
import os
import sys

def setup_logger():
    # 1. Crear carpeta de logs si no existe
    if not os.path.exists("logs"):
        os.makedirs("logs")

    # 2. Obtener el logger principal
    logger = logging.getLogger("bot")
    logger.setLevel(logging.INFO)

    # 3. Definir el formato: [HORA] [NIVEL] MENSAJE
    formatter = logging.Formatter(
        '[{asctime}] [{levelname:<8}] {name}: {message}',
        style='{',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 4. Handler de Consola (Para verlo en Bloom Host)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 5. Handler de Archivo (Guarda historial)
    # RotatingFileHandler: Si el archivo llega a 5MB, crea uno nuevo y guarda 1 backup.
    # Así no llenas el disco de Bloom Host.
    file_handler = logging.handlers.RotatingFileHandler(
        filename="logs/bot.log",
        encoding="utf-8",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=1
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Opcional: Limpiar logs ruidosos de librerías externas
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)

    return logger