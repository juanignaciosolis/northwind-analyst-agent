import logging
from logging import Logger

logger: Logger = logging.getLogger(__name__)

from google import genai
from google.genai import types
from typing import Optional, Any
import os
import time
import asyncio
from typing import AsyncIterator
import json


from .contract import GenerationResult
from src.utils.validators import temperature_validator,message_validator
from src.prompts.user_prompt import prompt_constructor
from src.utils.tokenomics import auditar_tokenomics
from src.utils.decorators import retry_backoff
from src.utils.errors import (ProviderConfigurationError,
                              RateLimitError, 
                              ProviderTimeoutError, 
                              TransientProviderError,
                              InvalidRequestError)
from src.agent.tools.tools import ToolRegistry, ToolPolicy, Tool, QuerySchema, execute_query_tool, ExecutionContext, pool
from src.prompts.system_prompt import zero_shot_system_prompt, few_shot_system_prompt
from src.settings import settings


class GeminiClient:

    def __init__(self, api_key: str | None, model: str):

        logger.info("Se inicializa el cliente de Gemini...")

        if not api_key:
            raise ProviderConfigurationError("Falta GEMINI_API_KEY")

        self.model = model
        self.client = genai.Client(api_key=api_key)

        logger.info("¡Éxito! Cliente instanciado")

    @staticmethod
    def _map_exception(exc: Exception) -> Exception:
        text = str(exc).lower()
        if "429" in text or "rate limit" in text or "resource exhausted" in text:
            return RateLimitError(str(exc))
        if "timeout" in text or "timed out" in text:
            return ProviderTimeoutError(str(exc))
        if "401" in text or "403" in text or "api key" in text:
            return ProviderConfigurationError(str(exc))
        return TransientProviderError(str(exc))

    @staticmethod
    def _config(system: str | None, temperature: float, max_output_tokens: int | None, available_tools: list[dict[str, Any]] | None = None ):

        if available_tools is not None:
            declarations = [
                types.FunctionDeclaration(
                    name=item["name"],
                    description=item["description"],
                    # Pydantic produce JSON Schema. El campo dedicado evita convertirlo
                    # manualmente al objeto Schema específico del proveedor.
                    parameters_json_schema=item["parameters"],
                )
                for item in available_tools ]
                
            tool_config = types.Tool(function_declarations=declarations)

            return types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature_validator(temperature),
            max_output_tokens = max_output_tokens,
            tools= [tool_config],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True)
                )

        return types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature_validator(temperature),
            max_output_tokens = max_output_tokens
        )

    @staticmethod
    def _usage(response) -> tuple[int, int]:
        
        usage = getattr(response, "usage_metadata", None)
        return (
            int(getattr(usage, "prompt_token_count", 0) or 0),
            int(getattr(usage, "candidates_token_count", 0) or 0),
        )

    def _normalize(self, response, started: float) -> GenerationResult:
        
        input_tokens, output_tokens = self._usage(response)

        function_call = None
        for part in response.candidates[0].content.parts:
            if getattr(part, "function_call", None):
                function_call = part.function_call
                break

        if function_call is None:

            return GenerationResult(
            executed=True,
            tool_name= None,
            tool_arguments= None,
            model=self.model,
            provider="gemini",
            latency=round((time.perf_counter() - started) * 1000, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens= input_tokens + output_tokens,
            final_text= response.text
        )


        return GenerationResult(
            executed= True,
            tool_name= function_call.name,
            tool_arguments= function_call.args,
            model=self.model,
            provider="gemini",
            latency=round((time.perf_counter() - started) * 1000, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens= input_tokens + output_tokens
        )

    #@auditar_tokenomics
    @retry_backoff(3,0.3)
    def generate(self, prompt: str,
                  *, 
                 system: str | None = None, 
                 temperature: float = 0.2, 
                 max_output_tokens: int | None = None, 
                 available_tools: list[dict[str, Any]] | None = None
                 ) -> GenerationResult:

        logger.debug(f"Configuracion:\nSystem Prompt - {"Contiene" if system else "No contiene"}\nTemperature - {temperature}\nMax. Output Tokens - {max_output_tokens}\nMTools- {available_tools}")

        logger.debug(f"[bold yellow]System prompt cargado:[/]\n{system}")

        mesagge = message_validator(prompt)
        prompt = prompt_constructor(mesagge)

        logger.debug("Prompt del usuario: " + f"[orange3]{prompt}[/]")

        logger.info("Se evia el mensaje por API")

        started = time.perf_counter()
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._config(system, temperature, max_output_tokens, available_tools),
            )

            return self._normalize(response, started)
        
        except Exception as exc:
            mapped_exc = self._map_exception(exc)
            raise mapped_exc from exc


    async def agenerate(self, prompt: str,
                         *, 
                         system: str | None = None, 
                         temperature: float = 0.2,
                         available_tools: list[dict[str, Any]] | None = None
                         ) -> GenerationResult:
        if not prompt.strip():
            raise InvalidRequestError("El prompt no puede estar vacío")
        started = time.perf_counter()
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._config(system, temperature),
            )
            return self._normalize(response, started)
        except Exception as exc:
            mapped_exc = self._map_exception(exc)
            raise mapped_exc from exc

if __name__ == "__main__":

    registry = ToolRegistry()
    policy = ToolPolicy()

    support_agent_context = ExecutionContext(
    user_id="support-agent-demo",
    role="support_agent",
    workspace_ids=["support-ops"],
    allow_drafts=True,
    allow_external_writes=False,
    run_id="c9-support-agent-demo")

    registry.register(
    Tool(
        name="execute_query_tool",
        description=(
            "Ejecuta una consulta SQL SELECT sobre PostgreSQL, analiza el resultado "
            "con un DataFrame de pandas y retorna los primeros 10 registros como diccionario."
        ),
        kind="read",
        fn=execute_query_tool,
        args_model=QuerySchema,
        timeout_s=5.0,
        retries=0,          # Las consultas a BD no suelen requerir retries automáticos
        backoff_s=0.05,
        idempotent=True,    # SELECT es una operación de lectura idempotente
    )
)

    function_declarations = registry.function_declarations(
    context=support_agent_context,
    policy=policy,
)
    print(json.dumps(function_declarations, ensure_ascii=False, indent=2))

    client = GeminiClient(settings.api_key_value(), settings.gemini_default_model)

    system_prompt_content = zero_shot_system_prompt()

    system_prompt_content += """\n# TOOLS
    Dispones de tools para consultar la base de datos y obtener respuestas
"""

    print(system_prompt_content)

    prompt = "Dame las ventas por cliente"

    respuesta = client.generate(prompt= prompt, system = system_prompt_content, available_tools= function_declarations)

    print("\n\n","RESPUESTA:\n",respuesta)
    
    pool.close()