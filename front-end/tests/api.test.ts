import { afterEach, describe, expect, it } from 'bun:test'
import { api, conversationEntries, historyMessages, historyTools, toolCall } from '../src/lib/api'
import type { ThreadHistory } from '../src/lib/api'
const originalFetch = globalThis.fetch
afterEach(() => {
  globalThis.fetch = originalFetch
})
describe('v1 API client', () => {
  it('retains tool details from history and distinguishes failed and running calls', () => {
    const item = {
      id: 'tool',
      type: 'mcpToolCall',
      tool: 'execute_sql',
      status: 'completed',
      arguments: { sql: 'SELECT 1' },
      result: { content: [{ type: 'text', text: '1' }] },
      durationMs: 25,
    }
    const history: ThreadHistory = {
      thread: {
        id: 'thread',
        name: null,
        status: { type: 'idle' },
        turns: [{ id: 'turn', status: 'completed', items: [item] }],
      },
    }
    expect(historyTools(history)[0]).toMatchObject({
      name: 'execute_sql',
      status: 'done',
      arguments: item.arguments,
      result: item.result,
      durationMs: 25,
    })
    expect(toolCall({ ...item, status: 'inProgress', result: null }).status).toBe('running')
    expect(toolCall({ ...item, error: { message: 'SQL error' } }, true).status).toBe('failed')
  })
  it('uses same-origin v1 endpoints and POST JSON for mutations', async () => {
    let seenUrl = ''
    let seenOptions: RequestInit | undefined
    globalThis.fetch = (async (url, options) => {
      seenUrl = String(url)
      seenOptions = options
      return new Response(JSON.stringify({ id: 'thread' }))
    }) as typeof fetch
    expect(await api('/threads', { prompt: 'Hello' })).toEqual({ id: 'thread' })
    expect(seenUrl).toBe('/v1/threads')
    expect(seenOptions?.method).toBe('POST')
    expect(JSON.parse(String(seenOptions?.body))).toEqual({ prompt: 'Hello' })
  })
  it('sends DELETE and handles a 204 response without parsing JSON', async () => {
    let method: string | undefined
    globalThis.fetch = (async (_url, options) => {
      method = options?.method
      return new Response(null, { status: 204 })
    }) as typeof fetch
    expect(await api<void>('/threads/id', undefined, 'DELETE')).toBeUndefined()
    expect(method).toBe('DELETE')
  })
  it('surfaces backend conflict messages', async () => {
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ detail: 'Thread đang có turn chạy.' }), {
        status: 409,
      })) as typeof fetch
    expect(api('/threads/id/turns', { prompt: 'Hi' })).rejects.toThrow('Thread đang có turn chạy.')
  })
  it('handles non-JSON backend errors', async () => {
    globalThis.fetch = (async () => new Response('Unavailable', { status: 503 })) as typeof fetch
    expect(api('/threads')).rejects.toThrow('503')
  })
  it('normalizes stored user/agent messages and skips tools', () => {
    const history: ThreadHistory = {
      thread: {
        id: 'thread',
        name: 'Question',
        status: { type: 'idle' },
        turns: [
          {
            id: 'turn',
            status: 'completed',
            items: [
              { id: 'user', type: 'userMessage', content: [{ type: 'text', text: 'Hello' }] },
              { id: 'tool', type: 'mcpToolCall', tool: 'search_objects' },
              { id: 'agent', type: 'agentMessage', text: '**Answer**', phase: 'final_answer' },
            ],
          },
        ],
      },
    }
    expect(historyMessages(history)).toEqual([
      { id: 'user', turnId: 'turn', role: 'user', text: 'Hello' },
      { id: 'agent', turnId: 'turn', role: 'assistant', text: '**Answer**', phase: 'final_answer' },
    ])
  })
})

it('keeps database activity with its turn when a new question arrives', () => {
  const messages = [
    { id: 'q1', turnId: 't1', role: 'user' as const, text: 'First' },
    { id: 'a1', turnId: 't1', role: 'assistant' as const, text: 'Answer' },
    { id: 'q2', turnId: 't2', role: 'user' as const, text: 'Next' },
  ]
  const tools = [toolCall({ id: 'sql1', type: 'mcpToolCall' }, true, 't1')]
  expect(conversationEntries(messages, tools).map((entry) => entry.id)).toEqual([
    'q1',
    'a1',
    't1-activity',
    'q2',
  ])
  tools.push(toolCall({ id: 'sql2', type: 'mcpToolCall' }, false, 't2'))
  const entries = conversationEntries(messages, tools)
  expect(entries.map((entry) => entry.id)).toEqual(['q1', 'a1', 't1-activity', 'q2', 't2-activity'])
  expect(
    entries.filter((entry) => entry.type === 'activity').map((entry) => entry.tools.length),
  ).toEqual([1, 1])
})
