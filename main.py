from dotenv import load_dotenv
import os

load_dotenv()

from src.core.llm import get_llm_client


if __name__ == "__main__":
        client = get_llm_client()
        print("¡Éxito! Cliente instanciado")

        print("\nEnviando mensaje de prueba...")
        respuesta = client.send_message(prompt="Hola soy juan, que modelo sos?")

        print(respuesta)
              
