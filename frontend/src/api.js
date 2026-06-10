const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail ?? "Nao foi possivel concluir a requisicao.");
  }
  return payload;
}

export function listConversations() {
  return request("/chat/conversations");
}

export function listMessages(conversationId) {
  return request(`/chat/conversations/${conversationId}/messages`);
}

export function deleteConversation(conversationId) {
  return request(`/chat/conversations/${conversationId}`, {
    method: "DELETE",
  });
}

export function sendMessage({ message, conversationId }) {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      conversation_id: conversationId ?? null,
    }),
  });
}

export async function streamMessage({ message, conversationId, onEvent }) {
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId ?? null,
    }),
  });

  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? "Nao foi possivel iniciar o stream da conversa.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const line = chunk.split("\n").find((part) => part.startsWith("data: "));
      if (!line) continue;
      onEvent(JSON.parse(line.slice(6)));
    }
  }
}
