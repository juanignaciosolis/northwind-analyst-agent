class EmptyPromptError(Exception):
    def __init__(self,message = "El prompt del usuario no puede estar vacio"):
        super().__init__(message)

class TypePromptError(Exception):
    def __init__(self,message = "El prompt del usuario debe ser de tipo String"):
        super().__init__(message)

class ShorterLenghtPromptError(Exception):
    def __init__(self,message = "El prompt del usuario es demasiado corto"):
        super().__init__(message)

class LongerLenghtPromptError(Exception):
    def __init__(self,message = "El prompt del usuario es demasiado largo"):
        super().__init__(message)
        
class TemperatureLimitsError(Exception):
    def __init__(self,message = "La temperatura debe estar entre 0 y 2"):
        super().__init__(message)

class TemperatureTypeError(Exception):
    def __init__(self,message = "La temperatura debe ser un numero"):
        super().__init__(message)

class EmptyRespondError(Exception):
    def __init__(self,message = "La respuesta del modelo es vacia (None)"):
        super().__init__(message)