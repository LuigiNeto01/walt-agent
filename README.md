# walt-agent

Aplicacao com frontend React, backend FastAPI, PostgreSQL em Docker Compose e integracao com a OpenAI para conversar com o Walt.

O Walt e um agent para ajudar Luigi com tarefas e gestao do PC. Ele usa a OpenAI Responses API com function calling nativo para decidir quando executar tools como Wake-on-LAN, SSH, Python e leitura de arquivos.

## Subindo a stack

```powershell
copy backend\.env.example backend\.env
```

Edite `backend\.env` e preencha `OPENAI_API_KEY`. Para as tools do PC, configure tambem Wake-on-LAN e SSH.

```powershell
docker compose up --build
```

Servicos:

- Frontend: http://127.0.0.1:5173
- API: http://127.0.0.1:8000
- Docs: http://127.0.0.1:8000/docs
- PostgreSQL: `localhost:5432`

## Frontend

O frontend fica em `frontend/` e usa React + Vite. No Docker, o Nginx do frontend faz proxy de `/api` para o container da API, entao as chamadas usam `/api/v1`.

No deploy do servidor, o frontend acessa a API via `host.docker.internal:8000` e o `docker-compose.prod.yml` coloca a API em rede de host para que o Wake-on-LAN saia pela LAN real da maquina.

Rodando fora do Docker:

```powershell
cd frontend
copy .env.example .env
npm install
npm run dev
```

## Endpoints principais

- `GET /api/v1/health`
- `POST /api/v1/chat`
- `POST /api/v1/chat/stream`
- `GET /api/v1/chat/conversations`
- `GET /api/v1/chat/conversations/{conversation_id}/messages`
- `DELETE /api/v1/chat/conversations/{conversation_id}`
- `POST /api/v1/tools/wake-pc`
- `POST /api/v1/tools/ssh/run`
- `POST /api/v1/tools/ssh/read-file`
- `POST /api/v1/tools/ssh/python`
- `POST /api/v1/tools/ssh/python-script`

## Chat e memoria

As conversas e mensagens sao persistidas no PostgreSQL. Ao iniciar uma conversa, a API gera um titulo curto localmente a partir da primeira mensagem.

O chat nao depende de comandos por prefixo. O usuario pode pedir naturalmente, inclusive tarefas com varias etapas, por exemplo:

```text
Walt, ligue meu PC e depois veja o hostname.
Walt, ligue o PC, entre em Documentos, liste tudo, se existir uma pasta GitHub liste ela tambem e no fim desligue o PC.
```

A OpenAI decide se deve chamar alguma tool. O prompt operacional do backend instrui o Walt a planejar internamente, executar chamadas sucessivas, observar resultados, verificar etapas e so responder quando concluir ou encontrar um bloqueio real. As chamadas executadas ficam salvas em `tool_calls_json` na mensagem do assistant.

O frontend usa `POST /api/v1/chat/stream` para exibir uma linha de execucao enquanto o Walt trabalha. Esse stream mostra status operacional, tools iniciadas, tools concluidas e resumos de saida; ele nao expoe raciocinio interno literal do modelo.

## Tools do Walt

Tools disponiveis no chat:

- `run_command`: executa comando Windows CMD no PC do Luigi via SSH.
- `run_python_script`: executa script Python existente. Use `background=true` para scripts longos, daemons ou GUI.
- `run_python_code`: executa codigo Python inline temporario.
- `read_file`: le arquivo texto do PC via SFTP.
- `wake_pc`: envia Wake-on-LAN para ligar o PC.

O usuario SSH e `walt`, mas os arquivos do Luigi ficam em `C:\Users\luigi`. O prompt do agent instrui o Walt a nunca usar `%USERPROFILE%`, `~` ou `$HOME` para arquivos do Luigi.

## Wake-on-LAN

Configure no `backend\.env`:

```env
WAKE_ON_LAN_ENABLED=true
WAKE_TARGET_MAC=AA:BB:CC:DD:EE:FF
WAKE_BROADCAST_IP=192.168.0.255
WAKE_PORT=9
WAKE_VERIFY_SSH_TIMEOUT=90
WAKE_VERIFY_SSH_INTERVAL=5
```

Opcionalmente voce pode configurar `WAKE_SOURCE_IP` para tentar fixar a interface de origem do envio. Em deploys com Docker bridge, esse hint pode nao existir dentro do container; nesse caso o Walt faz fallback e continua enviando o broadcast sem falhar o endpoint.

Quando SSH tambem estiver configurado, `wake_pc` aguarda a porta SSH responder por ate `WAKE_VERIFY_SSH_TIMEOUT` segundos antes de devolver o resultado. Isso ajuda o agent a nao tentar executar comandos enquanto o Windows ainda esta subindo.

Teste direto:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/tools/wake-pc
```

## SSH e Python

Configure no `backend\.env`:

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

Endpoints diretos:

- `POST /api/v1/tools/ssh/run` com `{"command":"hostname"}`
- `POST /api/v1/tools/ssh/read-file` com `{"path":"C:\\Users\\luigi\\arquivo.txt"}`
- `POST /api/v1/tools/ssh/python` com `{"code":"print('oi')"}`
- `POST /api/v1/tools/ssh/python-script` com `{"path":"C:/Users/luigi/script.py","args":"--flag valor"}`

## Scripts com interface grafica

Scripts como `pyautogui` e `tkinter` precisam rodar na sessao interativa do desktop. O Walt faz isso usando `run_python_script` com `background=true`:

1. Envia `walt_launcher.py` para `C:\Users\walt\` no PC.
2. Cria uma tarefa agendada como SYSTEM.
3. O launcher usa `WTSQueryUserToken` e `CreateProcessAsUserW` para iniciar o processo na sessao Console do Luigi.

Prerequisito: Luigi precisa estar logado na sessao interativa. Para funcionar apos Wake-on-LAN sem intervencao manual, deixe o auto-login configurado no Windows.

## Deploy

O `deploy.py` envia o projeto para o servidor por SSH e sobe o Docker Compose remoto. Ele nao guarda secrets no codigo; le `backend/.env` local para gerar o `.env` de producao no servidor.

Ao montar o `.env` de producao, o script envia apenas chaves com valor preenchido. Se uma chave estiver vazia no `backend/.env` local, o deploy preserva o valor remoto atual quando ele ja existir; se nao existir, a chave e omitida para o backend usar defaults quando apropriado.

No servidor, o deploy usa `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`. O override de producao coloca a API em `network_mode: host` para permitir Wake-on-LAN pela interface LAN da maquina hospedeira.

```powershell
$env:DEPLOY_HOST="192.168.0.12"
$env:DEPLOY_USER="luigi"
$env:DEPLOY_PASSWORD="sua_senha"
python deploy.py
```

Se `DEPLOY_PASSWORD` nao for definido, o script pede a senha no terminal.

### Deploy via Tailscale

O servidor pode ficar acessivel pela tailnet com Tailscale. No servidor Ubuntu:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo systemctl enable --now tailscaled
sudo tailscale up --ssh
tailscale ip -4
```

Depois de autenticar o link exibido pelo `tailscale up`, use o IP Tailscale como `DEPLOY_HOST`:

```powershell
$env:DEPLOY_HOST="100.x.y.z"
$env:DEPLOY_USER="luigi"
$env:DEPLOY_PASSWORD="sua_senha"
python deploy.py
```

Se a maquina que roda o deploy ainda nao estiver na tailnet, use o IP LAN em `DEPLOY_HOST` e adicione o IP Tailscale em `DEPLOY_PUBLIC_HOSTS` para liberar CORS:

```powershell
$env:DEPLOY_HOST="192.168.0.12"
$env:DEPLOY_PUBLIC_HOSTS="100.x.y.z"
python deploy.py
```

URLs pela tailnet:

- Frontend: `http://100.x.y.z:5173`
- API: `http://100.x.y.z:8000/api/v1`

## Testes

```powershell
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

Build do frontend:

```powershell
cd frontend
npm run build
```
