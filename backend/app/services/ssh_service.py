from pathlib import Path
from uuid import uuid4

import paramiko

from app.core.config import get_settings
from app.schemas.tools import SshCommandResponse, SshReadFileResponse


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}\n...[saida truncada em {limit} caracteres]"


def _client_or_error(command: str) -> tuple[paramiko.SSHClient | None, SshCommandResponse | None]:
    settings = get_settings()
    if not settings.ssh_enabled:
        return None, SshCommandResponse(
            ok=False,
            command=command,
            message=(
                "SSH esta desativado no momento. "
                "Para habilitar, adicione SSH_ENABLED=true no arquivo backend/.env "
                "junto com SSH_HOST, SSH_USERNAME e SSH_PASSWORD (ou SSH_KEY_PATH)."
            ),
        )
    if not settings.ssh_host or not settings.ssh_username:
        return None, SshCommandResponse(
            ok=False,
            command=command,
            message=(
                "SSH esta habilitado, mas faltam credenciais. "
                "Configure SSH_HOST e SSH_USERNAME no arquivo backend/.env."
            ),
        )
    if not settings.ssh_password and not settings.ssh_key_path:
        return None, SshCommandResponse(
            ok=False,
            command=command,
            message=(
                "SSH esta habilitado, mas sem autenticacao configurada. "
                "Adicione SSH_PASSWORD ou SSH_KEY_PATH no arquivo backend/.env."
            ),
        )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs = {
        "hostname": settings.ssh_host,
        "port": settings.ssh_port,
        "username": settings.ssh_username,
        "timeout": settings.ssh_command_timeout,
        "banner_timeout": settings.ssh_command_timeout,
        "auth_timeout": settings.ssh_command_timeout,
    }
    if settings.ssh_password:
        connect_kwargs["password"] = settings.ssh_password
    if settings.ssh_key_path:
        connect_kwargs["key_filename"] = str(Path(settings.ssh_key_path))

    try:
        client.connect(**connect_kwargs)
        return client, None
    except Exception as exc:
        client.close()
        err_str = str(exc).lower()
        if "unable to connect" in err_str or "connection refused" in err_str or "timed out" in err_str or "no route" in err_str:
            message = (
                f"Não consegui conectar ao PC ({settings.ssh_host}:{settings.ssh_port}). "
                "Parece que ele está desligado ou fora da rede. "
                "Se quiser, peça para eu ligar o PC via Wake-on-LAN antes de tentar novamente."
            )
        else:
            message = f"Falha ao conectar via SSH: {exc}"
        return None, SshCommandResponse(
            ok=False,
            command=command,
            message=message,
        )


def _run_ssh_command_with_client(client: paramiko.SSHClient, command: str) -> SshCommandResponse:
    settings = get_settings()
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=settings.ssh_command_timeout)
        stdin.close()
        exit_status = stdout.channel.recv_exit_status()
        stdout_text = _truncate(stdout.read().decode("utf-8", errors="replace"), settings.ssh_output_limit)
        stderr_text = _truncate(stderr.read().decode("utf-8", errors="replace"), settings.ssh_output_limit)
    except Exception as exc:
        return SshCommandResponse(
            ok=False,
            command=command,
            message=f"Falha ao executar comando via SSH: {exc}",
        )

    return SshCommandResponse(
        ok=exit_status == 0,
        command=command,
        exit_status=exit_status,
        stdout=stdout_text,
        stderr=stderr_text,
        message="Comando SSH executado." if exit_status == 0 else "Comando SSH retornou erro.",
    )


def run_ssh_command(command: str) -> SshCommandResponse:
    command = command.strip()

    if not command:
        return SshCommandResponse(ok=False, command=command, message="Comando SSH vazio.")

    client, error = _client_or_error(command)
    if error:
        return error
    if client is None:
        return SshCommandResponse(ok=False, command=command, message="Cliente SSH nao inicializado.")

    try:
        return _run_ssh_command_with_client(client, command)
    finally:
        client.close()


def read_ssh_file(path: str) -> SshReadFileResponse:
    settings = get_settings()
    remote_path = path.strip()
    filename = Path(remote_path.replace("\\", "/")).name or remote_path
    if not remote_path:
        return SshReadFileResponse(ok=False, path=remote_path, filename="", message="Caminho vazio.")

    client, error = _client_or_error(f"read-file {remote_path}")
    if error:
        return SshReadFileResponse(ok=False, path=remote_path, filename=filename, message=error.message)
    if client is None:
        return SshReadFileResponse(ok=False, path=remote_path, filename=filename, message="Cliente SSH nao inicializado.")

    try:
        sftp = client.open_sftp()
        try:
            stat = sftp.stat(remote_path)
            with sftp.open(remote_path, "rb") as remote_file:
                data = remote_file.read(settings.ssh_file_text_limit + 1)
        finally:
            sftp.close()
    except Exception as exc:
        return SshReadFileResponse(
            ok=False,
            path=remote_path,
            filename=filename,
            message=f"Falha ao ler arquivo via SFTP: {exc}",
        )
    finally:
        client.close()

    truncated = len(data) > settings.ssh_file_text_limit
    data = data[: settings.ssh_file_text_limit]
    content = data.decode("utf-8", errors="replace")

    return SshReadFileResponse(
        ok=True,
        path=remote_path,
        filename=filename,
        size_bytes=stat.st_size,
        content=content,
        truncated=truncated,
        message="Arquivo lido do PC via SSH.",
    )


def run_ssh_python_code(code: str) -> SshCommandResponse:
    settings = get_settings()
    code = code.strip()
    if not code:
        return SshCommandResponse(ok=False, command="", message="Codigo Python vazio.")

    remote_path = f"walt_python_{uuid4().hex}.py"
    command = f'{settings.ssh_python_command} "{remote_path}"'
    client, error = _client_or_error(command)
    if error:
        return error
    if client is None:
        return SshCommandResponse(ok=False, command=command, message="Cliente SSH nao inicializado.")

    try:
        sftp = client.open_sftp()
        try:
            with sftp.open(remote_path, "wb") as remote_file:
                remote_file.write(code.encode("utf-8"))
        finally:
            sftp.close()

        result = _run_ssh_command_with_client(client, command)
        cleanup = _run_ssh_command_with_client(client, f'del "{remote_path}"')
        if cleanup.exit_status not in (0, None):
            result.stderr = "\n".join(part for part in (result.stderr, cleanup.stderr) if part)
        return result
    finally:
        client.close()


def run_ssh_python_script(path: str, args: str = "") -> SshCommandResponse:
    settings = get_settings()
    remote_path = path.strip()
    if not remote_path:
        return SshCommandResponse(ok=False, command="", message="Caminho do script Python vazio.")
    command = f'{settings.ssh_python_command} "{remote_path}" {args.strip()}'.strip()
    return run_ssh_command(command)
