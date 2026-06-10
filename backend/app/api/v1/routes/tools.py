from fastapi import APIRouter

from app.schemas.tools import (
    SshCommandRequest,
    SshCommandResponse,
    SshPythonCodeRequest,
    SshPythonScriptRequest,
    SshReadFileRequest,
    SshReadFileResponse,
    WakePcResponse,
)
from app.services.ssh_service import read_ssh_file, run_ssh_command, run_ssh_python_code, run_ssh_python_script
from app.services.wake_on_lan_service import send_wake_on_lan_packet

router = APIRouter()


@router.post("/wake-pc", response_model=WakePcResponse)
def wake_pc() -> WakePcResponse:
    return send_wake_on_lan_packet()


@router.post("/ssh/run", response_model=SshCommandResponse)
def run_ssh(payload: SshCommandRequest) -> SshCommandResponse:
    return run_ssh_command(payload.command)


@router.post("/ssh/read-file", response_model=SshReadFileResponse)
def read_file(payload: SshReadFileRequest) -> SshReadFileResponse:
    return read_ssh_file(payload.path)


@router.post("/ssh/python", response_model=SshCommandResponse)
def run_python(payload: SshPythonCodeRequest) -> SshCommandResponse:
    return run_ssh_python_code(payload.code)


@router.post("/ssh/python-script", response_model=SshCommandResponse)
def run_python_script(payload: SshPythonScriptRequest) -> SshCommandResponse:
    return run_ssh_python_script(payload.path, payload.args)
