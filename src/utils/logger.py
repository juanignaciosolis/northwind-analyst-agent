import logging
import os
from pathlib import Path
from rich.logging import RichHandler

def setup_logger(name: str = "agent_logger", log_file: str = "logs/app.log") -> logging.Logger:
    """
    Configura un logger unificado:
    - Consola: Formato estético y con colores usando Rich.
    - Archivo: Formato detallado en texto plano.
    """
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG) 

    if logger.hasHandlers():
        logger.handlers.clear()

   
    file_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    rich_formatter = logging.Formatter(fmt="%(message)s")

    console_handler = RichHandler(
        rich_tracebacks=True,  
        markup=True           
    )
    console_handler.setLevel(logging.INFO)  
    console_handler.setFormatter(rich_formatter)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  
    file_handler.setFormatter(file_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()