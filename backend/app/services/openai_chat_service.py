import json
import time
import uuid
from pathlib import Path
from typing import Callable

from openai import OpenAI

from app.core.config import get_settings
from app.models.chat import ChatMessage
from app.services.ssh_service import read_ssh_file, run_ssh_command, run_ssh_python_code, run_ssh_python_script
from app.services.wake_on_lan_service import send_wake_on_lan_packet

# Path of the launcher script on the remote PC
_REMOTE_LAUNCHER = "C:/Users/walt/walt_launcher.py"
_REMOTE_LAUNCHER_BAT = "C:/Users/walt/run_launcher.bat"
_REMOTE_LAUNCHER_LOG = "C:/Users/walt/walt_launcher_result.txt"
# Python 3.12 system install (no spaces issue — well, has spaces but we wrap in bat)
_REMOTE_PYTHON = r"C:\Program Files\Python312\python.exe"

_ORCHESTRATION_PROMPT = """

Modo operacional:
- Para pedidos com varias etapas, transforme a intencao do usuario em um plano interno curto e execute as etapas usando quantas chamadas de tool forem necessarias.
- Depois de cada resultado de tool, avalie se a etapa foi concluida, se precisa de uma verificacao adicional ou se deve tentar uma alternativa segura.
- Nao responda ao usuario antes de terminar as etapas solicitadas ou antes de encontrar um bloqueio real.
- Se o PC precisar estar ligado, chame wake_pc e use o resultado para decidir quando tentar SSH. Se SSH ainda nao estiver pronto, faca uma verificacao posterior com run_command antes de prosseguir.
- Para tarefas de arquivos ou pastas, prefira comandos deterministas ou run_python_code quando houver condicoes, filtros ou multiplas listagens. Use caminhos completos em C:\\Users\\luigi.
- Quando o usuario pedir uma acao final como desligar o PC, execute essa acao apenas depois de coletar as informacoes necessarias para a resposta final.
- Ao finalizar, resuma o que foi feito, inclua os resultados relevantes e informe claramente qualquer etapa que falhou.
""".strip()


def _ensure_launcher() -> str | None:
    """Upload walt_launcher.py and run_launcher.bat to the PC.
    Returns None on success, or an error message."""
    launcher_source = Path(__file__).parent / "walt_launcher.py"
    if not launcher_source.exists():
        return "walt_launcher.py não encontrado no diretório de serviços"

    launcher_code = launcher_source.read_text(encoding="utf-8")
    bat_content = f"@echo off\r\n\"{_REMOTE_PYTHON}\" \"{_REMOTE_LAUNCHER.replace('/', chr(92))}\" %*\r\n"

    write_code = (
        f"content = {repr(launcher_code)}\n"
        f"with open({repr(_REMOTE_LAUNCHER)}, 'w', encoding='utf-8') as f:\n"
        f"    f.write(content)\n"
        f"bat = {repr(bat_content)}\n"
        f"with open({repr(_REMOTE_LAUNCHER_BAT)}, 'wb') as f:\n"
        f"    f.write(bat.encode('utf-8'))\n"
        f"print('launcher uploaded')\n"
    )
    r = run_ssh_python_code(write_code)
    if not r.ok:
        return f"Falha ao enviar launcher: {r.stderr or r.message}"
    return None


def _launch_in_desktop_session(cmd_line: str) -> str:
    """Launch cmd_line in luigi's interactive desktop session via SYSTEM Task Scheduler
    + WTSQueryUserToken + CreateProcessAsUserW. Returns status message."""
    err = _ensure_launcher()
    if err:
        return f"Erro ao preparar launcher: {err}"

    task_name = f"Walt_{uuid.uuid4().hex[:10]}"
    create_cmd = (
        f'schtasks /create /f /tn "{task_name}" '
        f'/tr "{_REMOTE_LAUNCHER_BAT} {cmd_line}" '
        f'/sc once /st 00:00 /ru "SYSTEM"'
    )
    r_create = run_ssh_command(create_cmd)
    if not r_create.ok:
        return "Falha ao criar tarefa:\n" + "\n".join(p for p in (r_create.stdout, r_create.stderr) if p)

    r_run = run_ssh_command(f'schtasks /run /tn "{task_name}"')
    run_ssh_command(f'schtasks /delete /f /tn "{task_name}"')

    if not r_run.ok:
        return "Falha ao disparar tarefa:\n" + "\n".join(p for p in (r_run.stdout, r_run.stderr) if p)

    time.sleep(3)

    r_log = run_ssh_command(f'type "{_REMOTE_LAUNCHER_LOG}"')
    log_content = (r_log.stdout or "").strip()

    if log_content.startswith("SUCCESS"):
        pid = log_content.split("PID=")[-1] if "PID=" in log_content else "?"
        return f"Script iniciado na sessão interativa do desktop do Luigi. PID: {pid}"
    return f"Launcher retornou: {log_content or 'sem saída'}"

_TOOLS = [
    {
        "type": "function",
        "name": "run_command",
        "description": (
            "Executa um comando no PC do Luigi via SSH. "
            "O PC roda Windows — use sintaxe CMD. "
            "Os arquivos do Luigi ficam em C:\\Users\\luigi (nunca use %USERPROFILE% ou ~)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Comando Windows CMD (ex: dir C:\\Users\\luigi\\Documents\\GitHub /b)",
                }
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "run_python_script",
        "description": (
            "Executa um script Python existente no PC do Luigi. "
            "Use background=true para scripts que rodam indefinidamente (daemons, always-on, monitores) "
            "ou que precisam de interface gráfica (GUI) — eles são disparados na sessão interativa do "
            "desktop do Luigi e retornam imediatamente."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Caminho completo do script (ex: D:\\Trabalho\\auth\\alwayson.py)",
                },
                "args": {
                    "type": "string",
                    "description": "Argumentos opcionais separados por espaço (pode ser vazio)",
                },
                "background": {
                    "type": "boolean",
                    "description": "Se true, executa em background sem aguardar conclusão",
                },
            },
            "required": ["path", "args", "background"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "run_python_code",
        "description": "Executa código Python inline temporário no PC do Luigi.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Código Python a executar"},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "read_file",
        "description": "Lê o conteúdo de um arquivo texto no PC do Luigi via SFTP.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Caminho completo do arquivo"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "wake_pc",
        "description": "Liga o PC do Luigi via Wake-on-LAN quando ele está desligado.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def _execute_tool(name: str, args: dict) -> str:
    if name == "run_command":
        r = run_ssh_command(args["command"])
        parts = [r.message]
        if r.exit_status is not None:
            parts.append(f"Exit code: {r.exit_status}")
        if r.stdout:
            parts.append(f"STDOUT:\n{r.stdout}")
        if r.stderr:
            parts.append(f"STDERR:\n{r.stderr}")
        return "\n\n".join(parts)

    if name == "run_python_script":
        path = args["path"].replace("\\", "/")
        if args.get("background"):
            script_args = args.get("args", "").strip()
            # Use SYSTEM Task Scheduler + walt_launcher.py (WTSQueryUserToken +
            # CreateProcessAsUserW) to inject the process into luigi's desktop session.
            # This is the only reliable way to show GUI windows from an SSH session.
            return _launch_in_desktop_session(f'pythonw "{path}"' + (f" {script_args}" if script_args else ""))
        else:
            r = run_ssh_python_script(path, args.get("args", ""))
        parts = [r.message]
        if r.exit_status is not None:
            parts.append(f"Exit code: {r.exit_status}")
        if r.stdout:
            parts.append(f"STDOUT:\n{r.stdout}")
        if r.stderr:
            parts.append(f"STDERR:\n{r.stderr}")
        return "\n\n".join(parts)

    if name == "run_python_code":
        r = run_ssh_python_code(args["code"])
        parts = [r.message]
        if r.exit_status is not None:
            parts.append(f"Exit code: {r.exit_status}")
        if r.stdout:
            parts.append(f"STDOUT:\n{r.stdout}")
        if r.stderr:
            parts.append(f"STDERR:\n{r.stderr}")
        return "\n\n".join(parts)

    if name == "read_file":
        r = read_ssh_file(args["path"])
        if r.ok:
            truncated = "\n[arquivo truncado]" if r.truncated else ""
            return f"Arquivo: {r.path}\nTamanho: {r.size_bytes} bytes\n\n{r.content}{truncated}"
        return r.message

    if name == "wake_pc":
        r = send_wake_on_lan_packet()
        if r.ok:
            return f"{r.message} MAC: {r.target_mac} via {r.broadcast_ip}:{r.port}"
        return r.message

    return f"Tool desconhecida: {name}"


def _summarize_tool_result(result: str, limit: int = 520) -> str:
    compact = " ".join(str(result).split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."


class OpenAIChatService:
    _MAX_TOOL_ROUNDS = 16

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None

    @property
    def model(self) -> str:
        return self.settings.openai_model

    def _build_input(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
    ) -> list[dict]:
        resolved = system_prompt or self.settings.agent_system_prompt
        input_messages: list[dict] = []
        if resolved:
            input_messages.append({"role": "system", "content": f"{resolved}\n\n{_ORCHESTRATION_PROMPT}"})
        input_messages.extend(
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in {"user", "assistant"}
        )
        return input_messages

    def generate_reply(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        event_callback: Callable[[dict], None] | None = None,
    ) -> tuple[str, str | None, list[dict]]:
        final_event = None
        for event in self.iter_reply_events(messages, system_prompt):
            if event["type"] == "reply_finished":
                final_event = event
            elif event_callback:
                event_callback(event)

        if final_event is None:
            raise RuntimeError("Resposta final nao gerada pela OpenAI.")

        return (
            final_event["assistant_text"],
            final_event["openai_response_id"],
            final_event["tool_calls"],
        )

    def iter_reply_events(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
    ):
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY nao configurada.")
        if self.client is None:
            raise RuntimeError("Cliente OpenAI nao inicializado.")

        input_messages = self._build_input(messages, system_prompt)
        all_tool_calls: list[dict] = []

        yield {"type": "status", "message": "Analisando pedido e definindo proximas etapas."}

        response = self.client.responses.create(
            model=self.model,
            input=input_messages,
            tools=_TOOLS,
        )

        for _ in range(self._MAX_TOOL_ROUNDS):
            tool_calls = [o for o in response.output if o.type == "function_call"]
            if not tool_calls:
                break

            tool_results = []
            for tc in tool_calls:
                call_index = len(all_tool_calls) + 1
                try:
                    args = json.loads(tc.arguments or "{}")
                    yield {
                        "type": "tool_started",
                        "index": call_index,
                        "name": tc.name,
                        "args": args,
                    }
                    result = _execute_tool(tc.name, args)
                except Exception as exc:
                    args = {}
                    result = f"Falha ao executar tool {tc.name}: {exc}"
                all_tool_calls.append({"name": tc.name, "args": args})
                yield {
                    "type": "tool_finished",
                    "index": call_index,
                    "name": tc.name,
                    "args": args,
                    "summary": _summarize_tool_result(result),
                }
                tool_results.append({
                    "type": "function_call_output",
                    "call_id": tc.call_id,
                    "output": result,
                })

            yield {"type": "status", "message": "Observando resultados e decidindo a proxima etapa."}

            response = self.client.responses.create(
                model=self.model,
                previous_response_id=response.id,
                input=tool_results,
                tools=_TOOLS,
            )

        remaining_tool_calls = [o for o in response.output if o.type == "function_call"]
        if remaining_tool_calls:
            assistant_text = (
                "Nao consegui concluir a tarefa inteira porque atingi o limite de etapas automaticas. "
                "As ferramentas executadas ate aqui ficaram registradas nesta conversa."
            )
        else:
            assistant_text = response.output_text or "Concluido."
        yield {
            "type": "reply_finished",
            "assistant_text": assistant_text,
            "openai_response_id": response.id,
            "tool_calls": all_tool_calls,
        }
