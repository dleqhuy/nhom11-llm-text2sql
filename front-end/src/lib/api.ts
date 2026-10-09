export type ThreadSummary = {
  id: string
  name: string | null
  createdAt: string
}

export type Message = {
  id: string
  turnId: string
  role: 'user' | 'assistant'
  text: string
  phase?: string
}

export type ToolCall = {
  id: string
  turnId: string
  name: string
  server?: string
  status: 'running' | 'done' | 'failed'
  arguments?: unknown
  result?: unknown
  error?: unknown
  durationMs?: number
}

export type Turn = {
  threadId: string
  turnId: string
  status: string
  eventCursor: string
}

type HistoryItem = Record<string, any>
type HistoryTurn = { id: string; status: string; items: HistoryItem[] }
export type ThreadHistory = {
  thread: { id: string; name: string | null; status: unknown; turns: HistoryTurn[] }
}

export type CodexEvent = {
  type: string
  data: Record<string, any>
}

export function apiUrl(path: string): string {
  const base = import.meta.env.VITE_API_URL?.replace(/\/$/, '') ?? ''
  return `${base}${path}`
}

export async function api<T = unknown>(
  path: string,
  body?: unknown,
  method = body === undefined ? 'GET' : 'POST',
): Promise<T> {
  const response = await fetch(apiUrl(`/v1${path}`), {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const payload = await response.json()
      if (typeof payload.detail === 'string') message = payload.detail
    } catch {
      // Keep the HTTP status when the server returned a non-JSON error page.
    }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function itemText(item: HistoryItem): string {
  if (typeof item.text === 'string') return item.text
  return (item.content ?? [])
    .filter((part: HistoryItem) => part.type === 'text')
    .map((part: HistoryItem) => part.text ?? '')
    .join('')
}

export function historyMessages(history: ThreadHistory): Message[] {
  const messages: Message[] = []
  for (const turn of history.thread.turns) {
    for (const item of turn.items) {
      if (item.type === 'userMessage')
        messages.push({ id: item.id, turnId: turn.id, role: 'user', text: itemText(item) })
      if (item.type === 'agentMessage')
        messages.push({
          id: item.id,
          turnId: turn.id,
          role: 'assistant',
          text: itemText(item),
          phase: item.phase,
        })
    }
  }
  return messages
}

export function toolCall(item: HistoryItem, completed: boolean, turnId = ''): ToolCall {
  const error = item.error ?? item.failure
  return {
    id: item.id,
    turnId,
    name: item.tool ?? item.name ?? 'MCP tool',
    server: item.server,
    status: error ? 'failed' : completed ? 'done' : 'running',
    arguments: item.arguments,
    result: item.result,
    error,
    durationMs: item.durationMs,
  }
}

export function historyTools(history: ThreadHistory): ToolCall[] {
  return history.thread.turns.flatMap((turn) =>
    turn.items
      .filter((item) => item.type === 'mcpToolCall')
      .map((item) => toolCall(item, item.status !== 'inProgress', turn.id)),
  )
}

export function conversationEntries(messages: Message[], tools: ToolCall[]) {
  const entries: Array<
    | { id: string; type: 'message'; message: Message }
    | { id: string; type: 'activity'; tools: ToolCall[] }
  > = []
  const toolsByTurn = new Map<string, ToolCall[]>()
  for (const tool of tools) {
    const calls = toolsByTurn.get(tool.turnId) ?? []
    calls.push(tool)
    toolsByTurn.set(tool.turnId, calls)
  }
  const emitted = new Set<string>()
  const lastMessageByTurn = new Map<string, string>()
  for (const message of messages) lastMessageByTurn.set(message.turnId, message.id)
  for (const message of messages) {
    entries.push({ id: message.id, type: 'message', message })
    const calls = toolsByTurn.get(message.turnId)
    if (
      calls?.length &&
      !emitted.has(message.turnId) &&
      lastMessageByTurn.get(message.turnId) === message.id
    ) {
      entries.push({ id: `${message.turnId}-activity`, type: 'activity', tools: calls })
      emitted.add(message.turnId)
    }
  }
  for (const [turnId, calls] of toolsByTurn) {
    if (!emitted.has(turnId))
      entries.push({ id: `${turnId}-activity`, type: 'activity', tools: calls })
  }
  return entries
}
