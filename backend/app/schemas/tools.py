from pydantic import BaseModel


class WakePcResponse(BaseModel):
    ok: bool
    message: str
    target_mac: str | None = None
    broadcast_ip: str | None = None
    source_ip: str | None = None
    port: int | None = None
    ssh_ready: bool | None = None
    ssh_check_seconds: int | None = None


class SshCommandRequest(BaseModel):
    command: str


class SshCommandResponse(BaseModel):
    ok: bool
    command: str
    exit_status: int | None = None
    stdout: str = ""
    stderr: str = ""
    message: str


class SshReadFileRequest(BaseModel):
    path: str


class SshReadFileResponse(BaseModel):
    ok: bool
    path: str
    filename: str
    size_bytes: int | None = None
    content: str = ""
    encoding: str = "utf-8"
    truncated: bool = False
    message: str


class SshPythonCodeRequest(BaseModel):
    code: str


class SshPythonScriptRequest(BaseModel):
    path: str
    args: str = ""
