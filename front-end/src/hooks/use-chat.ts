import { useCallback, useEffect, useRef, useState } from 'react'
import { api, apiUrl, historyMessages, historyTools, toolCall } from '@/lib/api'
import type { CodexEvent, Message, ThreadHistory, ThreadSummary, ToolCall, Turn } from '@/lib/api'

export function useChat() {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [selected, setSelected] = useState<ThreadSummary | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [tools, setTools] = useState<ToolCall[]>([])
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [turn, setTurn] = useState<Turn | null>(null)
  const [connection, setConnection] = useState('')
  const stream = useRef<EventSource | null>(null)
  const generation = useRef(0)
  const sending = useRef(false)
  const fail = (err: unknown) =>
    setError(err instanceof Error ? err.message : 'Có lỗi xảy ra. Vui lòng thử lại.')

  const refresh = useCallback(async () => {
    const page = await api<{ data: ThreadSummary[]; nextCursor: string | null }>(
      '/threads?limit=30',
    )
    setThreads(page.data)
    setCursor(page.nextCursor)
  }, [])
  const cleanup = useCallback(() => {
    stream.current?.close()
    generation.current++
  }, [])
  useEffect(() => {
    let disposed = false
    api<{ data: ThreadSummary[]; nextCursor: string | null }>('/threads?limit=30')
      .then((page) => {
        if (!disposed) {
          setThreads(page.data)
          setCursor(page.nextCursor)
        }
      })
      .catch((err) => {
        if (!disposed) fail(err)
      })
    return () => {
      disposed = true
      cleanup()
    }
  }, [cleanup])

  const loadMore = async () => {
    if (!cursor) return
    try {
      const page = await api<{ data: ThreadSummary[]; nextCursor: string | null }>(
        `/threads?limit=30&cursor=${encodeURIComponent(cursor)}`,
      )
      setThreads((old) => [
        ...old,
        ...page.data.filter((row) => !old.some((existing) => existing.id === row.id)),
      ])
      setCursor(page.nextCursor)
    } catch (err) {
      fail(err)
    }
  }

  const hydrate = async (id: string) => {
    const epoch = generation.current
    const history = await api<ThreadHistory>(`/threads/${encodeURIComponent(id)}?includeTurns=true`)
    if (generation.current === epoch) {
      setMessages(historyMessages(history))
      setTools(historyTools(history))
    }
    return history
  }

  const listen = (active: Turn, epoch: number, replay = true): void => {
    stream.current?.close()
    const query = new URLSearchParams({ threadId: active.threadId, turnId: active.turnId })
    if (replay) query.set('after', active.eventCursor)
    const source = new EventSource(apiUrl(`/events?${query}`))
    stream.current = source
    source.onopen = () => {
      if (generation.current === epoch) setConnection('Đang nhận phản hồi')
    }
    source.addEventListener('codex', (message) => {
      if (generation.current !== epoch) return
      const event = JSON.parse(message.data) as CodexEvent
      const data = event.data
      if (event.type === 'item/agentMessage/delta') {
        const id = data.itemId ?? `${active.turnId}-assistant`
        setMessages((old) => {
          if (old.some((item) => item.id === id))
            return old.map((item) =>
              item.id === id ? { ...item, text: item.text + (data.delta ?? '') } : item,
            )
          return [...old, { id, turnId: active.turnId, role: 'assistant', text: data.delta ?? '' }]
        })
      }
      if (event.type === 'item/started' || event.type === 'item/completed') {
        const item = data.item
        if (item?.type === 'agentMessage')
          setMessages((old) => {
            const record: Message = {
              id: item.id,
              turnId: active.turnId,
              role: 'assistant',
              text: item.text ?? '',
              phase: item.phase,
            }
            if (event.type === 'item/started' && !item.text) return old
            return old.some((existing) => existing.id === item.id)
              ? old.map((existing) => (existing.id === item.id ? record : existing))
              : [...old, record]
          })
        if (item?.type === 'mcpToolCall')
          setTools((old) => {
            const tool = toolCall(item, event.type === 'item/completed', active.turnId)
            return old.some((existing) => existing.id === item.id)
              ? old.map((existing) => (existing.id === item.id ? tool : existing))
              : [...old, tool]
          })
      }
      if (event.type === 'turn/completed' || event.type === 'backend/error') {
        source.close()
        setBusy(false)
        setTurn(null)
        setConnection('')
        if (event.type === 'backend/error' || data.turn?.status === 'failed')
          setError(
            data.turn?.error?.message ?? data.message ?? 'Codex không hoàn tất được yêu cầu.',
          )
        if (data.turn?.status === 'interrupted') setConnection('Đã dừng phản hồi')
        // Stored history is authoritative and removes any partial stream duplicates.
        hydrate(active.threadId).catch(fail)
        refresh().catch(fail)
      }
    })
    const recover = async () => {
      source.close()
      if (generation.current !== epoch) return
      setConnection('Đang khôi phục kết nối…')
      try {
        const history = await hydrate(active.threadId)
        if (generation.current !== epoch) return
        const last = history.thread.turns.find((item) => item.id === active.turnId)
        if (last?.status === 'inProgress') {
          // Retry live after reconciliation; cursor errors require a fresh subscription.
          setError('Kết nối stream bị gián đoạn. Đã tải lại lịch sử; đang theo dõi phản hồi mới.')
          listen(active, epoch, false)
        } else {
          setBusy(false)
          setTurn(null)
          setConnection('')
          refresh().catch(fail)
        }
      } catch (err) {
        fail(err)
        setBusy(false)
        setTurn(null)
        setConnection('')
      }
    }
    source.addEventListener('reset', recover)
    let recovering = false
    source.onerror = () => {
      if (generation.current === epoch && !recovering) {
        recovering = true
        source.close()
        setTimeout(() => {
          if (generation.current === epoch) void recover()
        }, 1500)
      }
    }
  }

  const select = async (thread: ThreadSummary) => {
    if (busy || sending.current) return
    const epoch = ++generation.current
    stream.current?.close()
    setSelected(thread)
    setTools([])
    setMessages([])
    setError(null)
    setLoading(true)
    setConnection('')
    try {
      const history = await api<ThreadHistory>(
        `/threads/${encodeURIComponent(thread.id)}?includeTurns=true`,
      )
      if (generation.current !== epoch) return
      setMessages(historyMessages(history))
      setTools(historyTools(history))
      const active = history.thread.turns.findLast((item) => item.status === 'inProgress')
      if (active) {
        const current: Turn = {
          threadId: thread.id,
          turnId: active.id,
          status: 'inProgress',
          eventCursor: '',
        }
        setTurn(current)
        setBusy(true)
        listen(current, epoch, false)
      }
    } catch (err) {
      fail(err)
    } finally {
      if (generation.current === epoch) setLoading(false)
    }
  }

  const newChat = () => {
    if (busy || sending.current) return
    generation.current++
    stream.current?.close()
    setSelected(null)
    setMessages([])
    setTools([])
    setError(null)
    setConnection('')
    setLoading(false)
  }

  const send = async (prompt: string) => {
    if (!prompt.trim() || loading || sending.current) return false
    sending.current = true
    setError(null)
    try {
      if (busy && turn) {
        await api(`/threads/${turn.threadId}/turns/${turn.turnId}/steer`, { prompt })
        setMessages((old) => [
          ...old,
          { id: crypto.randomUUID(), turnId: turn.turnId, role: 'user', text: prompt },
        ])
        return true
      }
      setBusy(true)
      setConnection('Đang bắt đầu…')
      let thread = selected
      if (!thread) {
        thread = await api<ThreadSummary>('/threads', { prompt })
        setSelected(thread)
        await refresh()
      }
      const active = await api<Turn>(`/threads/${thread.id}/turns`, { prompt })
      setMessages((old) => [
        ...old,
        { id: crypto.randomUUID(), turnId: active.turnId, role: 'user', text: prompt },
      ])
      setTurn(active)
      listen(active, generation.current)
      return true
    } catch (err) {
      fail(err)
      if (!turn) {
        setBusy(false)
        setConnection('')
      }
      return false
    } finally {
      sending.current = false
    }
  }

  const deleteThread = async (thread: ThreadSummary) => {
    if (busy || loading || sending.current) return false
    try {
      await api<void>(`/threads/${encodeURIComponent(thread.id)}`, undefined, 'DELETE')
      setThreads((old) => old.filter((item) => item.id !== thread.id))
      if (selected?.id === thread.id) newChat()
      await refresh().catch(fail)
      return true
    } catch (err) {
      fail(err)
      return false
    }
  }

  const stop = async () => {
    if (!turn) return
    try {
      await api(`/threads/${turn.threadId}/turns/${turn.turnId}/interrupt`, {})
      setConnection('Đang dừng…')
    } catch (err) {
      fail(err)
    }
  }
  return {
    threads,
    selected,
    messages,
    tools,
    busy,
    loading,
    error,
    connection,
    cursor,
    refresh,
    loadMore,
    select,
    newChat,
    send,
    stop,
    deleteThread,
    dismissError: () => setError(null),
  }
}
