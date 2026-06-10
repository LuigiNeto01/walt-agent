from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "walt-agent"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./walt_agent.db"
    init_db_on_startup: bool = True
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    agent_system_prompt: str = (
        "Voce se chama Walt. Voce e responsavel pela gestao do PC do Luigi "
        "e pelo apoio nas tarefas dele. Seja amigavel, prestativo, claro e proativo. "
        "Quando uma tarefa envolver a gestao do PC, use as tools disponiveis quando apropriado. "
        "O PC do Luigi roda Windows; ao executar comandos via SSH, use sintaxe CMD: "
        "'dir' em vez de 'ls' e 'type' em vez de 'cat'. A conexao SSH usa o usuario tecnico "
        "'walt', mas os arquivos do Luigi ficam em C:\\Users\\luigi. Nunca use %USERPROFILE%, "
        "~ ou $HOME para arquivos do Luigi. Para scripts Python, prefira caminhos com barras "
        "normais, como C:/Users/luigi/script.py. Use run_python_script com background=true para "
        "scripts longos, daemons ou scripts com interface grafica."
    )
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    wake_on_lan_enabled: bool = False
    wake_target_mac: str | None = None
    wake_broadcast_ip: str = "255.255.255.255"
    wake_source_ip: str | None = None
    wake_port: int = 9
    wake_verify_ssh_timeout: int = 90
    wake_verify_ssh_interval: int = 5
    ssh_enabled: bool = False
    ssh_host: str | None = None
    ssh_port: int = 22
    ssh_username: str | None = None
    ssh_password: str | None = None
    ssh_key_path: str | None = None
    ssh_command_timeout: int = 120
    ssh_output_limit: int = 6000
    ssh_file_text_limit: int = 12000
    ssh_python_command: str = "python"
    ssh_desktop_username: str | None = None
    ssh_desktop_password: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
