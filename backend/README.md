# walt-agent backend

API FastAPI com PostgreSQL, SQLAlchemy e integracao com a OpenAI Responses API.

## Rodando com Docker

Na raiz do projeto:

```powershell
copy backend\.env.example backend\.env
docker compose up --build
```

Se voce usar `deploy.py`, os campos vazios do `backend/.env` local nao sobrescrevem secrets e configuracoes ja existentes no `.env` remoto. Quando a chave nao existe em nenhum dos dois lados, ela e omitida para evitar falha de bootstrap do FastAPI em variaveis booleanas e numericas opcionais.

No deploy de producao, a API roda com o override `docker-compose.prod.yml` em rede de host. Isso e necessario para Wake-on-LAN sair pela LAN do servidor em vez da bridge do Docker.

## Rodando sem Docker

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## URLs

- API: http://127.0.0.1:8000
- Docs: http://127.0.0.1:8000/docs
- Healthcheck: http://127.0.0.1:8000/api/v1/health

## Chat

`POST /api/v1/chat`

```json
{
  "message": "Oi, Walt. Verifique o status do meu PC.",
  "conversation_id": null,
  "system_prompt": null
}
```

Se `conversation_id` for omitido ou `null`, uma nova conversa sera criada. Para continuar uma conversa, envie o mesmo `conversation_id` retornado na primeira resposta.

Quando `system_prompt` nao e enviado, a API usa `AGENT_SYSTEM_PROMPT` do ambiente. Por padrao, o agent se chama Walt e atua como assistente para gestao do PC e tarefas.

`POST /api/v1/chat/stream` aceita o mesmo payload e retorna `text/event-stream`. O frontend usa essa rota para mostrar status operacional, chamadas de tool e resumos de resultado enquanto o Walt executa a tarefa. O stream nao deve expor raciocinio interno literal do modelo.

Consultas:

- `GET /api/v1/chat/conversations`
- `GET /api/v1/chat/conversations/{conversation_id}/messages`
- `DELETE /api/v1/chat/conversations/{conversation_id}`

## Function calling

O chat usa function calling nativo da OpenAI. A API nao usa mais parsers por prefixo como `execute no pc:` ou `python no pc:`. O usuario pede naturalmente e o modelo decide quando chamar as tools.

O prompt operacional do backend instrui o Walt a lidar com tarefas em varias etapas: planejar internamente, executar chamadas sucessivas, observar os resultados, verificar se cada etapa foi concluida e finalizar apenas quando a tarefa estiver completa ou houver um bloqueio real.

Tools disponiveis em `app/services/openai_chat_service.py`:

- `run_command`: comando Windows CMD via SSH.
- `run_python_script`: script Python existente, com `background=true` para daemons/GUI.
- `run_python_code`: codigo Python temporario.
- `read_file`: leitura de arquivo texto via SFTP.
- `wake_pc`: Wake-on-LAN.

As chamadas feitas pelo assistant sao salvas em `tool_calls_json`.

## Tools diretas

### Wake-on-LAN

`POST /api/v1/tools/wake-pc`

```env
WAKE_ON_LAN_ENABLED=true
WAKE_TARGET_MAC=AA:BB:CC:DD:EE:FF
WAKE_BROADCAST_IP=192.168.0.255
WAKE_PORT=9
WAKE_VERIFY_SSH_TIMEOUT=90
WAKE_VERIFY_SSH_INTERVAL=5
```

`WAKE_SOURCE_IP` e opcional. Se informado, a API tenta fixar a interface de origem; se esse IP nao existir dentro do runtime atual, o envio continua sem bind explicito em vez de derrubar o endpoint.

Quando SSH esta configurado, `wake_pc` tambem aguarda a porta SSH responder por ate `WAKE_VERIFY_SSH_TIMEOUT` segundos antes de retornar. Isso permite que fluxos de chat continuem para comandos SSH com menos tentativas prematuras.

### SSH

`POST /api/v1/tools/ssh/run`

```json
{
  "command": "hostname"
}
```

Configure:

```env
SSH_ENABLED=true
SSH_HOST=192.168.0.4
SSH_PORT=22
SSH_USERNAME=walt
SSH_PASSWORD=sua_senha
SSH_KEY_PATH=
SSH_COMMAND_TIMEOUT=120
SSH_OUTPUT_LIMIT=6000
SSH_FILE_TEXT_LIMIT=12000
SSH_PYTHON_COMMAND=python
```

O usuario SSH e `walt`, mas os arquivos do Luigi ficam em `C:\Users\luigi`. Use caminhos completos e prefira barras normais em scripts Python, por exemplo `C:/Users/luigi/script.py`.

Arquivos e Python:

- `POST /api/v1/tools/ssh/read-file` com `{"path":"C:\\Users\\luigi\\arquivo.txt"}`
- `POST /api/v1/tools/ssh/python` com `{"code":"print('oi')"}`
- `POST /api/v1/tools/ssh/python-script` com `{"path":"C:/Users/luigi/script.py","args":"--flag valor"}`

## Testes

```powershell
cd backend
pip install -r requirements-dev.txt
python -m pytest
```
