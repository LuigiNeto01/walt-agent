import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  Bot,
  Code2,
  FileText,
  Loader2,
  MessageSquarePlus,
  PanelLeft,
  Power,
  Search,
  Send,
  Terminal,
  Trash2,
  UserRound,
  Wrench,
} from "lucide-react";
import remarkGfm from "remark-gfm";

import { deleteConversation, listConversations, listMessages, streamMessage } from "./api";

const formatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const EMPTY_PROMPTS = [
  "Ligue meu PC e confira se o SSH voltou.",
  "Leia um arquivo em C:/Users/luigi/Documents.",
  "Rode um script Python em background.",
];

const TOOL_META = {
  run_command: {
    label: "Comando remoto",
    Icon: Terminal,
    tone: "is-command",
  },
  run_python_script: {
    label: "Script Python",
    Icon: Code2,
    tone: "is-script",
  },
  run_python_code: {
    label: "Codigo Python",
    Icon: Code2,
    tone: "is-script",
  },
  read_file: {
    label: "Leitura de arquivo",
    Icon: FileText,
    tone: "is-file",
  },
  wake_pc: {
    label: "Wake-on-LAN",
    Icon: Power,
    tone: "is-power",
  },
};

function getConversationInitial(title) {
  return (title ?? "C").trim().charAt(0).toUpperCase() || "C";
}

function compactText(value, limit = 88) {
  if (!value) return "";
  const text = String(value).replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit - 1).trimEnd()}...`;
}

function parseToolCalls(toolCallsJson) {
  if (!toolCallsJson) return [];
  try {
    const parsed = JSON.parse(toolCallsJson);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function describeToolArgs(tool) {
  const args = tool.args ?? {};

  if (tool.name === "run_command") {
    return compactText(args.command, 120);
  }
  if (tool.name === "run_python_script") {
    const path = compactText(args.path, 72);
    const suffix = args.background ? " em background" : "";
    return [path, suffix].filter(Boolean).join("");
  }
  if (tool.name === "run_python_code") {
    return compactText(args.code, 90);
  }
  if (tool.name === "read_file") {
    return compactText(args.path, 90);
  }
  return "";
}

function formatMessageContent(content) {
  return String(content)
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function App() {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [error, setError] = useState("");
  const [executionEvents, setExecutionEvents] = useState([]);
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 820);
  const bottomRef = useRef(null);

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeId),
    [activeId, conversations],
  );

  const loadMessages = useCallback(async (conversationId) => {
    setActiveId(conversationId);
    setLoadingMessages(true);
    setError("");
    try {
      const data = await listMessages(conversationId);
      setMessages(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingMessages(false);
    }
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      const data = await listConversations();
      setConversations(data);
      return data;
    } catch (err) {
      setError(err.message);
      return [];
    }
  }, []);

  useEffect(() => {
    refreshConversations();
  }, [refreshConversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, executionEvents]);

  const isMobile = () => window.innerWidth <= 820;

  function startNewConversation() {
    setActiveId(null);
    setMessages([]);
    setExecutionEvents([]);
    setError("");
    if (isMobile()) setSidebarOpen(false);
  }

  function usePromptSuggestion(prompt) {
    setDraft(prompt);
  }

  async function handleDeleteConversation(event, conversationId) {
    event.stopPropagation();
    event.preventDefault();
    setError("");

    try {
      await deleteConversation(conversationId);
      setConversations((current) => current.filter((conversation) => conversation.id !== conversationId));
      if (conversationId === activeId) {
        startNewConversation();
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || loading) return;

    const optimisticMessage = {
      id: `draft-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setDraft("");
    setError("");
    setLoading(true);
    setExecutionEvents([{ type: "status", message: "Enviando pedido para o Walt." }]);
    setMessages((current) => [...current, optimisticMessage]);

    try {
      let finalResponse = null;
      await streamMessage({
        message: content,
        conversationId: activeId,
        onEvent: (event) => {
          if (event.type === "user_message") {
            setActiveId(event.conversation.id);
            setMessages((current) => [
              ...current.filter((message) => message.id !== optimisticMessage.id),
              event.user_message,
            ]);
            return;
          }

          if (event.type === "final") {
            finalResponse = event.response;
            setActiveId(event.response.conversation.id);
            setMessages((current) => [
              ...current.filter((message) => message.id !== optimisticMessage.id && message.id !== event.response.user_message.id),
              event.response.user_message,
              event.response.assistant_message,
            ]);
            return;
          }

          if (event.type === "error") {
            throw new Error(event.message);
          }

          setExecutionEvents((current) => [...current, event]);
        },
      });
      if (!finalResponse) {
        throw new Error("O Walt nao retornou uma resposta final.");
      }
      await refreshConversations();
    } catch (err) {
      setMessages((current) => current.filter((message) => message.id !== optimisticMessage.id));
      setDraft(content);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className={`shell ${sidebarOpen ? "" : "is-sidebar-collapsed"}`}>
      {sidebarOpen && <div className="sidebarBackdrop" onClick={() => setSidebarOpen(false)} aria-hidden="true" />}
      <aside className={`sidebar ${sidebarOpen ? "is-open" : ""}`}>
        <div className="brand">
          <div className="brandMark" aria-hidden="true">W</div>
          <div>
            <span className="eyebrow">assistente</span>
            <h1>Walt</h1>
          </div>
          <button className="iconButton" type="button" onClick={() => setSidebarOpen(false)} aria-label="Fechar conversas">
            <PanelLeft size={20} />
          </button>
        </div>

        <button className="newButton" type="button" onClick={startNewConversation}>
          <MessageSquarePlus size={18} />
          Nova conversa
        </button>

        <div className="sidebarSection">
          <span>Conversas</span>
          <strong>{conversations.length}</strong>
        </div>

        <nav className="conversationList" aria-label="Conversas">
          {conversations.length === 0 ? (
            <div className="emptyList">
              <Search size={16} />
              Nenhuma conversa salva.
            </div>
          ) : conversations.map((conversation) => (
            <div
              className={`conversationItem ${conversation.id === activeId ? "is-active" : ""}`}
              key={conversation.id}
              onClick={() => { loadMessages(conversation.id); if (isMobile()) setSidebarOpen(false); }}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  loadMessages(conversation.id);
                  if (isMobile()) setSidebarOpen(false);
                }
              }}
            >
              <span className="conversationGlyph" aria-hidden="true">
                {getConversationInitial(conversation.title)}
              </span>
              <div className="conversationText">
                <span className="conversationTitle" title={conversation.title ?? "Conversa sem titulo"}>
                  {conversation.title ?? "Conversa sem titulo"}
                </span>
                <time>{formatter.format(new Date(conversation.updated_at))}</time>
              </div>
              <button
                className="deleteButton"
                type="button"
                onClick={(event) => handleDeleteConversation(event, conversation.id)}
                aria-label="Excluir conversa"
                title="Excluir conversa"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <button className="iconButton" type="button" onClick={() => setSidebarOpen(true)} aria-label="Abrir conversas">
            <PanelLeft size={20} />
          </button>
          <div className="topbarCopy">
            <span className="eyebrow">{activeConversation ? "conversa ativa" : "nova conversa"}</span>
            <h2>{activeConversation?.title ?? "Nova conversa"}</h2>
          </div>
          <div className="topbarBadge">
            <Wrench size={15} />
            tools nativas
          </div>
        </header>

        <div className="messages">
          <div className="messageRail conversationStage">
            {loadingMessages ? (
              <div className="emptyState is-loading">
                <Loader2 className="spin" size={24} />
                <p>Carregando historico...</p>
              </div>
            ) : messages.length === 0 ? (
              <EmptyConversation onUsePrompt={usePromptSuggestion} />
            ) : (
              messages.map((message) => <MessageBubble key={message.id} message={message} />)
            )}
            {loading && (
              <RuntimeTrace events={executionEvents} />
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        {error && <div className="error">{error}</div>}

        <form className="composer" onSubmit={handleSubmit}>
          <div className="composerShell">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  handleSubmit(event);
                }
              }}
              placeholder="Digite sua mensagem para o Walt"
              rows={1}
            />
            <button className="sendButton" type="submit" disabled={loading || !draft.trim()} aria-label="Enviar mensagem">
              {loading ? <Loader2 className="spin" size={20} /> : <Send size={20} />}
            </button>
          </div>
          <span className="composerHint">Enter envia. Shift + Enter quebra linha.</span>
        </form>
      </section>
    </main>
  );
}

function EmptyConversation({ onUsePrompt }) {
  return (
    <div className="emptyState is-rich">
      <div className="emptyHero">
        <div className="emptyIcon">
          <Bot size={28} />
        </div>
        <div>
          <span className="eyebrow">walt pronto</span>
          <h3>Comece uma nova conversa</h3>
          <p>O Walt pode ligar o PC, rodar comandos, ler arquivos e acionar scripts quando a tarefa pedir.</p>
        </div>
      </div>
      <div className="promptGrid">
        {EMPTY_PROMPTS.map((prompt) => (
          <button key={prompt} className="promptCard" type="button" onClick={() => onUsePrompt(prompt)}>
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

function ToolCallPanel({ toolCallsJson }) {
  const calls = parseToolCalls(toolCallsJson);
  const [isOpen, setIsOpen] = useState(false);
  if (!calls.length) return null;

  return (
    <section className={`toolPanel ${isOpen ? "is-open" : ""}`} aria-label="Ferramentas usadas">
      <button
        className="toolPanelSummary"
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        aria-expanded={isOpen}
      >
        <div className="toolPanelHeaderMain">
          <span className="toolPanelBadge" aria-hidden="true">
            <Wrench size={14} />
          </span>
          <div>
            <span className="toolPanelKicker">Ferramentas acionadas</span>
            <p className="toolPanelDescription">Clique para ver as chamadas executadas pelo Walt.</p>
          </div>
        </div>
        <strong>{calls.length === 1 ? "1 chamada" : `${calls.length} chamadas`}</strong>
      </button>
      {isOpen && (
        <div className="toolList">
          {calls.map((tool, index) => {
            const meta = TOOL_META[tool.name] ?? {
              label: tool.name,
              Icon: Wrench,
              tone: "is-generic",
            };
            const detail = describeToolArgs(tool);
            const Icon = meta.Icon;

            return (
              <article className={`toolRow ${meta.tone}`} key={`${tool.name}-${index}`}>
                <span className="toolRowIcon" aria-hidden="true">
                  <Icon size={15} />
                </span>
                <div className="toolRowBody">
                  <div className="toolRowTopline">
                    <span className="toolRowTitle">{meta.label}</span>
                    <span className="toolRowHandle">{tool.name}</span>
                  </div>
                  {detail && <code className="toolRowDetail">{detail}</code>}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function RuntimeTrace({ events }) {
  const visibleEvents = events.slice(-8);

  return (
    <section className="runtimeTrace" aria-label="Execucao em andamento">
      <div className="runtimeTraceHeader">
        <span className="runtimeTracePulse" aria-hidden="true" />
        <div>
          <span className="runtimeTraceKicker">Linha de execucao</span>
          <strong>Walt esta executando as etapas</strong>
        </div>
      </div>
      <div className="runtimeTraceList">
        {visibleEvents.map((event, index) => {
          const meta = TOOL_META[event.name] ?? { label: event.name, Icon: Wrench, tone: "is-generic" };
          const Icon = event.type === "status" ? Loader2 : meta.Icon;
          const isRunning = event.type === "status" || event.type === "tool_started";
          const title = event.type === "status"
            ? event.message
            : event.type === "tool_started"
              ? `Chamando ${meta.label}`
              : `${meta.label} concluido`;
          const detail = event.type === "tool_finished"
            ? event.summary
            : describeToolArgs(event);

          return (
            <article className={`runtimeTraceItem ${isRunning ? "is-running" : "is-done"}`} key={`${event.type}-${event.index ?? index}-${index}`}>
              <span className="runtimeTraceIcon" aria-hidden="true">
                <Icon className={isRunning ? "spin" : ""} size={15} />
              </span>
              <div className="runtimeTraceBody">
                <span>{title}</span>
                {detail && <code>{detail}</code>}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === "user";
  const parts = formatMessageContent(message.content);

  return (
    <article className={`message ${isUser ? "is-user" : "is-assistant"}`}>
      <div className="avatar">{isUser ? <UserRound size={18} /> : <Bot size={18} />}</div>
      <div className="bubbleStack">
        {!isUser && <ToolCallPanel toolCallsJson={message.tool_calls_json} />}
        <div className="bubble">
          <div className="bubbleHeader">
            <span className="messageRole">{isUser ? "Voce" : "Walt"}</span>
            <time>{formatter.format(new Date(message.created_at))}</time>
          </div>
          <div className="bubbleBody">
            {isUser ? (
              parts.length > 0 ? parts.map((part, index) => <p key={index}>{part}</p>) : <p>{message.content}</p>
            ) : (
              <ReactMarkdown className="markdownBody" remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
