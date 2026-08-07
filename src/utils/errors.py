class LLMError(Exception):
    """Error base de la capa de modelos."""

class EmptyPromptError(LLMError):
    def __init__(self,message = "El prompt del usuario no puede estar vacio"):
        super().__init__(message)

class TypePromptError(LLMError):
    def __init__(self,message = "El prompt del usuario debe ser de tipo String"):
        super().__init__(message)

class ShorterLenghtPromptError(LLMError):
    def __init__(self,message = "El prompt del usuario es demasiado corto"):
        super().__init__(message)

class LongerLenghtPromptError(LLMError):
    def __init__(self,message = "El prompt del usuario es demasiado largo"):
        super().__init__(message)
        
class TemperatureLimitsError(LLMError):
    def __init__(self,message = "La temperatura debe estar entre 0 y 2"):
        super().__init__(message)

class TemperatureTypeError(LLMError):
    def __init__(self,message = "La temperatura debe ser un numero"):
        super().__init__(message)

class EmptyRespondError(LLMError):
    def __init__(self,message = "La respuesta del modelo es vacia (None)"):
        super().__init__(message)


class ProviderConfigurationError(LLMError):
    """Configuración o credenciales inválidas. No se reintenta."""
    def __init__(self,message = "Configuración o credenciales inválidas"):
        super().__init__(message)


class InvalidRequestError(LLMError):
    """Input inválido. No se reintenta."""
    def __init__(self,message = "Input inválido"):
        super().__init__(message)

class InvalidProviderResponseError(LLMError):
    """El proveedor respondió, pero no cumplió el contrato."""
    def __init__(self,message = "El proveedor respondió, pero no cumplió el contrato"):
        super().__init__(message)

class TransientProviderError(LLMError):
    """Falla temporal. Puede reintentarse con límites."""
    def __init__(self,message = "Falla temporal"):
        super().__init__(message)

class RateLimitError(TransientProviderError):
    """Límite temporal de uso."""
    def __init__(self,message = "Limite temporal de uso"):
        super().__init__(message)


class ProviderTimeoutError(TransientProviderError):
    """La llamada superó el tiempo permitido."""
    def __init__(self,message = "La llamada supero el tiempo permitido"):
        super().__init__(message)

class PartialStreamError(LLMError):
    """El stream falló después de emitir contenido."""
    def __init__(self,message = "El stream falló después de emitir contenido."):
        super().__init__(message)


RETRYABLE_DEMO_ERRORS = (
    RateLimitError,
    ProviderTimeoutError,
    TransientProviderError,
)