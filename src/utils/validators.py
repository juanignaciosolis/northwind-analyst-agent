from .errors import TypePromptError, EmptyPromptError, TemperatureTypeError, TemperatureLimitsError


def prompt_validator(prompt: str) -> str:
    if prompt in (None, ""):
        raise EmptyPromptError
    if not isinstance(prompt, str):
        raise TypePromptError
    
    clean_prompt = prompt.strip()
    
    return clean_prompt


def temperature_validator(temperature: float | int) -> float | int:

    if not isinstance(temperature, (float,int)):
        raise TemperatureTypeError

    if temperature < 0 or temperature > 2:
        raise TemperatureLimitsError
    
    return temperature
