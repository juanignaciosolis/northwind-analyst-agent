from src.settings import settings
from src.agent.llm import build_provider
from src.agent.llm.contract import LLMProvider


def estimate_tokens(text: str, client: LLMProvider) -> int:
    """Estima u obtiene el conteo exacto de tokens delegándolo 
    al cliente correspondiente según el proveedor configurado.
    """
    text = str(text)
    if not text:
        return 0

    return client.count_tokens(text)



if __name__ == "__main__":
    client = build_provider(settings)
    texto = "Hola como va?"
    print("Total", estimate_tokens(texto,client))