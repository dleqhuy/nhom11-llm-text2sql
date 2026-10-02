export interface ThreadSummary {
  id: string
  name: string | null
  createdAt: string
}

export interface Turn {
  threadId: string
  turnId: string
  status: string
  eventCursor: string
}

export interface Message {
  id: string
  turnId: string
  role: 'user' | 'assistant'
  text: string
  phase?: string
}

export interface ToolCall {
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

export interface CodexEvent {
  type: string
  data: {
    itemId?: string
    delta?: string
    item?: Record<string, any>
    turn?: { status?: string; error?: { message?: string } }
    message?: string
  }
}

export interface ThreadHistory {
  thread: {
    turns: Array<{
      id: string
      status: string
      items?: Array<Record<string, any>>
    }>
  }
}

export function apiUrl(path: string): string {
  return `/v1${path.startsWith('/') ? path : `/${path}`}`
}

export async function api<T = unknown>(
  path: string,
  body?: unknown,
  method?: string,
): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: method ?? (body === undefined ? 'GET' : 'POST'),
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const payload = await response.json()
      if (typeof payload.detail === 'string') detail = payload.detail
    } catch {
      // Keep the HTTP status when the server doesn't return a JSON error body.
    }
    throw new Error(detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function toolCall(
  item: Record<string, any>,
  completed: boolean,
  turnId: string,
): ToolCall {
  const result = item.result ?? item.structuredContent ?? item.content
  const error = item.error
  return {
    id: item.id,
    turnId,
    name: item.tool ?? item.name ?? item.toolName ?? 'database tool',
    server: item.server ?? item.serverName,
    status: !completed ? 'running' : error ? 'failed' : 'done',
    arguments: item.arguments ?? item.input,
    result,
    error,
    durationMs: item.durationMs,
  }
}

export function historyMessages(history: ThreadHistory): Message[] {
  return (history.thread.turns ?? []).flatMap((turn) =>
    (turn.items ?? []).flatMap((item): Message[] => {
      if (item.type === 'userMessage') {
        const text = (item.content ?? [])
          .filter((part: any) => part.type === 'text')
          .map((part: any) => part.text ?? '')
          .join('')
        return [{ id: item.id, turnId: turn.id, role: 'user', text }]
      }
      if (item.type === 'agentMessage') {
        return [{
          id: item.id,
          turnId: turn.id,
          role: 'assistant',
          text: item.text ?? '',
          phase: item.phase,
        }]
      }
      return []
    }),
  )
}

export function historyTools(history: ThreadHistory): ToolCall[] {
  return (history.thread.turns ?? []).flatMap((turn) =>
    (turn.items ?? [])
      .filter((item) => item.type === 'mcpToolCall')
      .map((item) => toolCall(item, true, turn.id)),
  )
}

export function conversationEntries(messages: Message[], tools: ToolCall[]) {
  const entries: Array<
    | { type: 'message'; id: string; message: Message }
    | { type: 'activity'; id: string; tools: ToolCall[] }
  > = messages.map((message) => ({ type: 'message', id: message.id, message }))
  const grouped = new Map<string, ToolCall[]>()
  for (const tool of tools) {
    const group = grouped.get(tool.turnId) ?? []
    group.push(tool)
    grouped.set(tool.turnId, group)
  }
  for (const [turnId, turnTools] of grouped) {
    const lastMessage = entries.findLastIndex(
      (entry) => entry.type === 'message' && entry.message.turnId === turnId,
    )
    entries.splice(lastMessage + 1, 0, {
      type: 'activity',
      id: `activity-${turnId}`,
      tools: turnTools,
    })
  }
  return entries
}
