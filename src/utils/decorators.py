import logging

logger = logging.getLogger("agent_logger.tokenomics")

import functools
import time
from typing import Callable, Any
import requests

def retry_backoff(intentos: int, delay: int) -> Callable:
    
    def decorator(func: function) -> Callable:

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:

            max_intentos = intentos
            intento = 1

            logger.info("Realizando llamada..")

            while intento <= max_intentos:

                try:
                    resultado = func(*args, **kwargs)
                    logger.info(f"Llama exitosa en {intento} intentos")
                    return resultado
                except Exception as e:
                    logger.warning(f"Llamada fallida: {e}, intento {intento}, se vuelve a intentar...")
                    potencia = delay ** intento
                    if intento == max_intentos:
                        break
                    intento += 1
                    logger.warning(f"Se esperan {potencia} segundos antes de reintentar")
                    time.sleep(potencia)
            
            logger.error(f"Se acabaron todos lo intentos. En total {max_intentos}")
            raise Exception("Máximo de intentos fallidos en la API.")
        
        return wrapper
    return decorator
          


if __name__ == "__main__":

    URL = "https://randomuser.me/api/"
    @retry_backoff(2,2)
    def funcion_prueba():
        respuesta = requests.get(URL)
        return respuesta
        
    

    for i in range(0,20):

        print(f"\n Intento {i}: ",funcion_prueba(),"\n")

    print("Prueba terminada")


    

                    

            

