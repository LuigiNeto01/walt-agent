import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Loader2, MessageSquarePlus, PanelLeft, Search, Send, Trash2, UserRound } from "lucide-react";

import { deleteConversation, listConversations, listMessages, sendMessage } from "./api";

const formatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function getConversationInitial(title) {
  return (title ?? "C").trim().charAt(0).toUpperCase() || "C";
}

export function App() {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [error, setError] = useState("");
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
    async function loadInitialConversation() {
      const data = await refreshConversations();
      if (data.length > 0) {
        await loadMessages(data[0].id);
      }
    }

    loadInitialConversation();
  }, [loadMessages, refreshConversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const isMobile = () => window.innerWidth <= 820;

  function startNewConversation() {
    setActiveId(null);
    setMessages([]);
    setError("");
    if (isMobile()) setSidebarOpen(false);
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
    setMessages((current) => [...current, optimisticMessage]);

    try {
      const response = await sendMessage({ message: content, conversationId: activeId });
      setActiveId(response.conversation.id);
      setMessages((current) => [
        ...current.filter((message) => message.id !== optimisticMessage.id),
        response.user_message,
        response.assistant_message,
      ]);
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
            <span className="eyebrow">walt-agent</span>
            <h1>Chat</h1>
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
          <div>
            <span className="eyebrow">{activeConversation ? "conversa ativa" : "nova conversa"}</span>
            <h2>{activeConversation?.title ?? "Comece pelo primeiro prompt"}</h2>
          </div>
        </header>

        <div className="messages">
          {loadingMessages ? (
            <div className="emptyState">
              <Loader2 className="spin" size={24} />
            </div>
          ) : messages.length === 0 ? (
            <div className="emptyState">
              <Bot size={34} />
              <p>Envie uma mensagem para iniciar.</p>
            </div>
          ) : (
            messages.map((message) => <MessageBubble key={message.id} message={message} />)
          )}
          {loading && (
            <div className="typing">
              <Loader2 className="spin" size={18} />
              pensando
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {error && <div className="error">{error}</div>}

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSubmit(event);
              }
            }}
            placeholder="Digite sua mensagem"
            rows={1}
          />
          <button className="sendButton" type="submit" disabled={loading || !draft.trim()} aria-label="Enviar mensagem">
            {loading ? <Loader2 className="spin" size={20} /> : <Send size={20} />}
          </button>
        </form>
      </section>
    </main>
  );
}

const TOOL_LABELS = {
  run_command: "cmd",
  run_python_script: "py script",
  run_python_code: "py code",
  read_file: "read file",
  wake_pc: "wake-on-lan",
};

function ToolBadge({ toolCallsJson }) {
  if (!toolCallsJson) return null;
  let calls;
  try { calls = JSON.parse(toolCallsJson); } catch { return null; }
  if (!calls.length) return null;

  const summary = calls.length === 1
    ? `usou ${TOOL_LABELS[calls[0].name] ?? calls[0].name}`
    : `usou ${calls.length} tools`;

  const tooltip = calls
    .map((c) => {
      const label = TOOL_LABELS[c.name] ?? c.name;
      const detail = c.args.command ?? c.args.path ?? c.args.code ?? "";
      return detail ? `${label}: ${detail}` : label;
    })
    .join("\n");

  return <span className="toolBadge" title={tooltip}>{summary}</span>;
}

function MessageBubble({ message }) {
  const isUser = message.role === "user";
  return (
    <article className={`message ${isUser ? "is-user" : "is-assistant"}`}>
      <div className="avatar">{isUser ? <UserRound size={18} /> : <Bot size={18} />}</div>
      <div className="bubble">
        {!isUser && <ToolBadge toolCallsJson={message.tool_calls_json} />}
        <p>{message.content}</p>
        <time>{formatter.format(new Date(message.created_at))}</time>
      </div>
    </article>
  );
}
