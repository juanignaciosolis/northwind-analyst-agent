import logging
from logging import Logger

logger: Logger = logging.getLogger(__name__)

from openai import OpenAI, AsyncOpenAI
import time
import asyncio
from typing import AsyncIterator
import json


from .contract import GenerationResult
from src.utils.validators import temperature_validator,message_validator
from src.utils.decorators import retry_backoff
from src.prompts.user_prompt import prompt_constructor
from src.utils.tokenomics import auditar_tokenomics
from src.schemas.output_schemas import AnswerOpenAIScheme
from src.utils.errors import (ProviderConfigurationError,
                              RateLimitError, 
                              ProviderTimeoutError, 
                              TransientProviderError,
                              InvalidProviderResponseError,
                              InvalidRequestError)

from src.agent.tools.tools import ToolRegistry, ToolPolicy, Tool, QuerySchema, execute_query_tool, ExecutionContext, pool
from src.prompts.system_prompt import zero_shot_system_prompt, few_shot_system_prompt
from src.settings import settings


class OpenAIClient:
    def __init__(self, api_key: str | None, model: str):

        logger.info("Se inicializa el cliente de OpenAI...")

        if not api_key:
            raise ProviderConfigurationError("Falta OPENAI_API_KEY")

        self.model = model
        self.client = OpenAI(api_key = api_key)
        self.aclient = AsyncOpenAI(api_key=api_key)

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

    from typing import Any


    @staticmethod
    def _normalize_tools(
        function_declarations: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]] | None:
        if not function_declarations:
            return None

        tools = []

        for declaration in function_declarations:
            tool = {
                "type": "function",
                "name": declaration["name"],
                "description": declaration["description"],
                "parameters": declaration["parameters"],
            }
            tools.append(tool)

        return tools

    @staticmethod
    def _usage(response) -> tuple[int, int]:
        usage = getattr(response, "usage", None)
        return (
            int(getattr(usage, "prompt_tokens", 0) or 0),
            int(getattr(usage, "completetion_tokens", 0) or 0),
        )

    def _normalize(self, response, started: float) -> GenerationResult:
                
        input_tokens, output_tokens = self._usage(response)

        tool_call = next(
        (
        item
        for item in response.output
        if item.type == "function_call"
        ),
        None,
        )

        if tool_call:
            return GenerationResult(
                executed=True,
                tool_name=tool_call.name,
                tool_arguments=json.loads(tool_call.arguments),
                model=self.model,
                provider="openai",
                latency=round((time.perf_counter() - started) * 1000, 2),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                final_text=None,
            )
        
        return GenerationResult(
            executed=False,
            tool_name=None,
            tool_arguments=None,
            model=self.model,
            provider="openai",
            latency=round((time.perf_counter() - started) * 1000, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            final_text=response.output_text,
        )

    @retry_backoff(3,0.3)
    def generate(self, prompt: str,
                  *, system: str | None = None, 
                  temperature: float = 0.2, 
                  max_output_tokens: int | None = None,
                  available_tools: list[dict[str, Any]] | None = None) -> GenerationResult:

        logger.debug(f"Configuracion:\nSystem Prompt - {"Contiene" if system else "No contiene"}\nTemperature - {temperature}\nMax. Output Tokens - {max_output_tokens}")

        logger.debug(f"[bold yellow]System prompt cargado:[/]\n{system}")

        tools = self._normalize_tools(available_tools)

        mesagge = message_validator(prompt)
        prompt = prompt_constructor(mesagge)

        logger.debug("Prompt: " + f"[orange3]{prompt}[/]")

        try:
            started = time.perf_counter()
            response = self.client.responses.parse(
                model=self.model,
                instructions=system,
                store=False,
                input=prompt,
                temperature= temperature_validator(temperature),
                max_output_tokens=max_output_tokens,
                tools=tools)

            logger.info("Llamada exitosa!")

            answer = self._normalize(response, started)

            return answer
        
        except Exception as exc:
            mapped_exc = self._map_exception(exc)
            raise mapped_exc from exc


    async def agenerate(self, prompt: str,
                         *, 
                         system: str | None = None, 
                         temperature: float = 0.2,
                         available_tools: list[dict[str, Any]] | None = None) -> GenerationResult:
        if not prompt.strip():
            raise InvalidRequestError("El prompt no puede estar vacío")

        tools = self._normalize_tools(available_tools)

        started = time.perf_counter()
        try:
            response = await self.aclient.responses.parse(
                model=self.model,
                instructions=system,
                store=False,
                input=prompt,
                temperature= temperature_validator(temperature),
                tools=tools)
            
            logger.info("Llamada exitosa!")

            answer = self._normalize(response, started)

            return answer
        
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

    client = OpenAIClient(settings.api_key_value(), settings.openai_default_model)

    system_prompt_content = zero_shot_system_prompt()

    system_prompt_content += """\n# TOOLS
    Dispones de tools para consultar la base de datos y obtener respuestas
"""

    print(system_prompt_content)

    prompt = "Dame las ventas por cliente"

    respuesta = client.generate(prompt= prompt, system = system_prompt_content, available_tools= function_declarations)

    print("\n\n","RESPUESTA:\n",respuesta)
    
    pool.close()