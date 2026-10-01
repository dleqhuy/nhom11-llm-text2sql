import { conversationEntries } from '@/lib/api'
import { DatabaseActivity } from '@/components/database-activity'
import { useEffect, useRef, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleAlert,
  Code2,
  Copy,
  Database,
  History,
  Loader2,
  Menu,
  MessageSquare,
  Plus,
  Search,
  SlidersHorizontal,
  Sparkles,
  Square,
  Terminal,
  Trash2,
  X,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
} from '@/components/ui/alert-dialog'
import type { ThreadSummary } from '@/lib/api'
import { useChat } from '@/hooks/use-chat'

const suggestions = [
  {
    icon: Database,
    title: 'Khám phá dữ liệu',
    description: 'Tìm hiểu các bảng và cấu trúc database',
    prompt: 'Liệt kê các bảng trong database và giải thích ngắn gọn dữ liệu của từng bảng.',
  },
  {
    icon: SlidersHorizontal,
    title: 'Phân tích & so sánh',
    description: 'Tìm câu trả lời từ những con số',
    prompt: 'Tỷ lệ khách hàng thanh toán bằng EUR so với CZK là bao nhiêu?',
  },
  {
    icon: Code2,
    title: 'Viết truy vấn SQL',
    description: 'Biến câu hỏi thành truy vấn rõ ràng',
    prompt:
      'Khám phá schema và giúp tôi viết một truy vấn SQL thống kê số khách hàng theo quốc gia.',
  },
]

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      size="icon-sm"
      variant="ghost"
      title="Sao chép câu trả lời"
      aria-label="Sao chép câu trả lời"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {
          setCopied(false)
        }
      }}
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
    </Button>
  )
}

export default function App() {
  const chat = useChat()
  const [deleteTarget, setDeleteTarget] = useState<ThreadSummary | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [draft, setDraft] = useState('')
  const [search, setSearch] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  const textarea = useRef<HTMLTextAreaElement>(null)
  const scrollArea = useRef<HTMLDivElement>(null)
  const follow = useRef(true)
  const visibleThreads = chat.threads.filter((thread) =>
    (thread.name ?? '').toLocaleLowerCase().includes(search.toLocaleLowerCase()),
  )
  useEffect(() => {
    if (follow.current)
      bottom.current?.scrollIntoView({ behavior: chat.busy ? 'instant' : 'smooth' })
  }, [chat.messages, chat.tools, chat.busy])
  const submit = async (prompt = draft) => {
    if (submitting || !prompt.trim()) return
    setSubmitting(true)
    follow.current = true
    if (await chat.send(prompt.trim())) setDraft('')
    setSubmitting(false)
    textarea.current?.focus()
  }
  const reset = () => {
    chat.newChat()
    setDraft('')
    setSidebarOpen(false)
    follow.current = true
    textarea.current?.focus()
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-background text-foreground">
      {sidebarOpen && (
        <button
          aria-label="Đóng menu"
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-sm md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        className={`sidebar fixed inset-y-0 left-0 z-40 flex w-72 shrink-0 flex-col text-white transition-transform md:relative md:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <div className="flex h-24 items-center gap-3 px-6">
          <div className="flex size-10 items-center justify-center rounded-xl bg-[#e88a5b] text-[#242a25]">
            <Database className="size-5" strokeWidth={2.2} />
          </div>
          <div>
            <div className="text-lg font-semibold tracking-tight">
              query<span className="text-[#e99a72]">desk</span>
              <span className="ml-1 text-[#e99a72]">.</span>
            </div>
            <div className="mt-0.5 text-[10px] font-medium uppercase tracking-[0.2em] text-white/40">
              Your data, in conversation
            </div>
          </div>
          <button
            className="ml-auto text-white/60 md:hidden"
            aria-label="Đóng menu"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="size-5" />
          </button>
        </div>
        <div className="px-4">
          <Button
            className="h-11 w-full justify-start rounded-lg border border-white/15 bg-white/5 text-white hover:bg-white/10"
            disabled={chat.busy}
            onClick={reset}
          >
            <Plus className="size-4" /> Cuộc trò chuyện mới{' '}
            <span className="ml-auto rounded border border-white/15 px-1.5 text-[10px] text-white/40">
              NEW
            </span>
          </Button>
          <div className="mt-6 flex items-center gap-2 rounded-md border border-white/10 bg-black/10 px-3">
            <Search className="size-3.5 text-white/35" />
            <input
              aria-label="Tìm cuộc trò chuyện"
              placeholder="Tìm cuộc trò chuyện…"
              className="h-9 w-full bg-transparent text-xs outline-none placeholder:text-white/30"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>
        <div className="mt-7 flex items-center justify-between px-6 text-[10px] font-semibold uppercase tracking-[0.15em] text-white/35">
          <span>Cuộc trò chuyện</span>
          <History className="size-3.5" />
        </div>
        <nav className="mt-3 flex-1 overflow-y-auto px-3" aria-label="Danh sách cuộc trò chuyện">
          {visibleThreads.map((thread) => (
            <div key={thread.id} className="group relative">
              <button
                disabled={chat.busy || chat.loading}
                className={`mb-1 flex w-full items-start gap-2.5 rounded-lg px-3 pr-10 py-3 text-left transition-colors disabled:opacity-50 ${chat.selected?.id === thread.id ? 'bg-white/10 text-white' : 'text-white/55 hover:bg-white/5 hover:text-white'}`}
                onClick={() => {
                  void chat.select(thread)
                  setDraft('')
                  setSidebarOpen(false)
                  follow.current = true
                }}
              >
                <MessageSquare className="mt-0.5 size-3.5 shrink-0" />
                <div className="min-w-0">
                  <div className="truncate text-xs font-medium">
                    {thread.name ?? 'Cuộc trò chuyện chưa có tên'}
                  </div>
                  <div className="mt-1 text-[10px] text-white/30">
                    {new Date(thread.createdAt).toLocaleDateString('vi-VN', {
                      day: 'numeric',
                      month: 'short',
                    })}
                  </div>
                </div>
              </button>
              <button
                type="button"
                aria-label={`Xóa ${thread.name ?? 'cuộc trò chuyện'}`}
                title="Xóa cuộc trò chuyện"
                disabled={chat.busy || chat.loading || deleting}
                className="absolute right-2 top-3 rounded-md p-1.5 text-white/35 opacity-100 transition-opacity hover:bg-white/10 hover:text-red-300 focus-visible:opacity-100 disabled:opacity-25 md:opacity-0 md:group-hover:opacity-100"
                onClick={() => {
                  chat.dismissError()
                  setDeleteTarget(thread)
                }}
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
          {!visibleThreads.length && (
            <div className="px-3 py-5 text-xs leading-6 text-white/30">
              {search
                ? 'Không tìm thấy cuộc trò chuyện.'
                : 'Các cuộc trò chuyện của bạn sẽ xuất hiện ở đây.'}
            </div>
          )}
          {chat.cursor && (
            <button
              className="w-full py-3 text-xs text-white/50 hover:text-white"
              onClick={() => void chat.loadMore()}
            >
              Xem thêm
            </button>
          )}
        </nav>
        <div className="mx-5 mb-6 mt-3">
          <div className="rounded-xl border border-white/10 bg-white/[0.025] p-4">
            <div className="flex items-center gap-2 text-xs font-medium text-white/75">
              <Terminal className="size-3.5 text-[#e99a72]" /> Powered by Codex
            </div>
            <p className="mt-2 text-[11px] leading-5 text-white/35">
              Khám phá database bằng ngôn ngữ tự nhiên, ngay trong workspace của bạn.
            </p>
          </div>
          <div className="mt-5 flex items-center gap-2 text-[10px] text-white/35">
            <span className="size-1.5 rounded-full bg-[#e99a72]" /> Workspace local{' '}
            <span className="ml-auto">v1.0</span>
          </div>
        </div>
      </aside>
      <main className="relative flex min-w-0 flex-1 flex-col">
        <header className="flex h-[76px] shrink-0 items-center justify-between gap-3 border-b border-border/70 px-5 lg:px-10">
          <div className="flex min-w-0 items-center gap-3 text-xs">
            <Button
              className="md:hidden"
              size="icon-sm"
              variant="ghost"
              aria-label="Mở menu"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu />
            </Button>
            <span className="hidden text-muted-foreground sm:block">Workspace</span>
            <ChevronRight className="hidden size-3 text-muted-foreground/60 sm:block" />
            <span className="truncate font-medium">
              {chat.selected?.name ?? 'Cuộc trò chuyện mới'}
            </span>
          </div>
          <Badge
            variant="outline"
            className="shrink-0 gap-1.5 rounded-full border-[#d9ded6] bg-[#edf0e9] px-3 py-1.5 text-[10px] font-medium text-[#5d6954]"
          >
            <Database className="size-3" /> PostgreSQL <span className="text-[#5d6954]/40">/</span>{' '}
            MCP
          </Badge>
        </header>
        <div
          className="flex-1 overflow-y-auto"
          ref={scrollArea}
          onScroll={() => {
            const el = scrollArea.current
            if (el) follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120
          }}
        >
          <div className="mx-auto w-full max-w-4xl px-5 pb-8 pt-8 lg:px-12">
            {chat.error && (
              <div
                role="alert"
                className="mb-6 flex items-start gap-3 rounded-xl border border-[#e8b9a8] bg-[#fff2ed] px-4 py-3 text-xs leading-5 text-[#99472d]"
              >
                <CircleAlert className="mt-0.5 size-4 shrink-0" />
                <span className="flex-1">{chat.error}</span>
                <button aria-label="Đóng thông báo lỗi" onClick={chat.dismissError}>
                  <X className="size-4" />
                </button>
              </div>
            )}
            {chat.loading ? (
              <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Đang tải cuộc trò chuyện…
              </div>
            ) : chat.messages.length === 0 && !chat.busy ? (
              <section className="animate-in pt-10 sm:pt-20">
                <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-[#e6d6c8] bg-[#f5ece3] px-3 py-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-[#9b6b4c]">
                  <Sparkles className="size-3" /> Một cách mới để hiểu dữ liệu
                </div>
                <h1 className="hero-title text-[42px] leading-[1.15] tracking-tight sm:text-[58px]">
                  Dữ liệu của bạn.
                  <br />
                  <span className="text-[#a86542]">Câu trả lời rõ ràng.</span>
                </h1>
                <p className="mt-5 max-w-lg text-sm leading-7 text-muted-foreground">
                  Đặt câu hỏi, khám phá cấu trúc và tìm insight từ database.
                  <br className="hidden sm:block" /> Codex giúp bạn đi từ câu hỏi đến câu trả lời.
                </p>
                <div className="mb-4 mt-12 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.15em] text-muted-foreground">
                  <span className="h-px w-5 bg-border" /> Bắt đầu từ một ý tưởng
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  {suggestions.map(({ icon: Icon, ...suggestion }) => (
                    <button
                      key={suggestion.title}
                      className="suggestion group rounded-xl border border-border bg-white/55 p-5 text-left transition-all hover:-translate-y-1 hover:border-[#d6b39a] hover:bg-white hover:shadow-sm"
                      onClick={() => {
                        setDraft(suggestion.prompt)
                        textarea.current?.focus()
                      }}
                    >
                      <div className="mb-5 flex items-center justify-between">
                        <Icon className="size-5 text-[#927052]" strokeWidth={1.5} />
                        <ArrowUpRight className="size-3.5 text-muted-foreground/40 transition-colors group-hover:text-[#a86542]" />
                      </div>
                      <h2 className="text-xs font-semibold">{suggestion.title}</h2>
                      <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
                        {suggestion.description}
                      </p>
                    </button>
                  ))}
                </div>
              </section>
            ) : (
              <div className="space-y-8">
                {conversationEntries(chat.messages, chat.tools).map((entry) => {
                  if (entry.type === 'activity')
                    return <DatabaseActivity key={entry.id} tools={entry.tools} />
                  const message = entry.message
                  return message.role === 'user' ? (
                    <div key={message.id} className="flex justify-end">
                      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-[#eaece5] px-5 py-3.5 text-sm leading-6 whitespace-pre-wrap">
                        {message.text}
                      </div>
                    </div>
                  ) : (
                    <div key={message.id} className="flex gap-3 sm:gap-4">
                      <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-[#e6d6c8] bg-[#f5ece3]">
                        <Sparkles className="size-4 text-[#a86542]" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="mb-2 flex items-center gap-2 text-xs font-semibold">
                          Codex{' '}
                          {message.phase === 'commentary' && (
                            <span className="text-[10px] font-normal text-muted-foreground">
                              Đang phân tích
                            </span>
                          )}
                        </div>
                        <div
                          className={`markdown ${message.phase === 'commentary' ? 'text-muted-foreground' : ''}`}
                        >
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown>
                        </div>
                        {!chat.busy && message.phase !== 'commentary' && (
                          <div className="mt-2 text-muted-foreground">
                            <CopyButton text={message.text} />
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
                {chat.busy && (
                  <div
                    role="status"
                    className="ml-11 flex items-center gap-2 text-xs text-muted-foreground"
                  >
                    <span className="flex gap-1">
                      <i className="thinking-dot" />
                      <i className="thinking-dot" />
                      <i className="thinking-dot" />
                    </span>
                    {chat.connection || 'Codex đang xử lý…'}
                  </div>
                )}
              </div>
            )}
            <div ref={bottom} />
          </div>
        </div>
        <footer className="shrink-0 px-5 pb-5 pt-3 lg:px-12">
          <div className="mx-auto max-w-3xl">
            <form
              className="rounded-2xl border border-[#dcded5] bg-white shadow-[0_4px_24px_-10px_#343f2925] transition-shadow focus-within:border-[#bbaa98] focus-within:shadow-[0_4px_24px_-8px_#343f2930]"
              onSubmit={(event) => {
                event.preventDefault()
                void submit()
              }}
            >
              <Textarea
                ref={textarea}
                value={draft}
                maxLength={20000}
                disabled={chat.loading || submitting}
                aria-label={chat.busy ? 'Bổ sung hướng dẫn' : 'Câu hỏi về dữ liệu'}
                placeholder={
                  chat.busy
                    ? 'Bổ sung hướng dẫn cho Codex…'
                    : 'Bạn muốn tìm hiểu điều gì từ dữ liệu?'
                }
                className="min-h-[76px] max-h-48 resize-none rounded-2xl border-0 bg-transparent px-5 pt-5 text-sm shadow-none focus-visible:ring-0"
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                    event.preventDefault()
                    void submit()
                  }
                }}
              />
              <div className="flex items-center justify-between px-3 pb-3 pl-5">
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                  <Database className="size-3.5" />
                  <span>Database workspace</span>
                  <Separator orientation="vertical" className="mx-1 h-3" />
                  <span className="hidden sm:inline">
                    {chat.busy ? 'Bổ sung vào lượt đang chạy' : 'Codex'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {chat.busy && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="rounded-lg text-xs"
                      onClick={() => void chat.stop()}
                      disabled={!chat.selected || submitting}
                    >
                      <Square className="size-3 fill-current" /> Dừng
                    </Button>
                  )}
                  <Button
                    type="submit"
                    size="icon"
                    className="size-9 rounded-lg bg-[#303b30] text-white hover:bg-[#445044]"
                    disabled={
                      !draft.trim() || submitting || chat.loading || (chat.busy && !chat.selected)
                    }
                    aria-label={chat.busy ? 'Bổ sung hướng dẫn' : 'Gửi câu hỏi'}
                  >
                    {submitting ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <ArrowUp className="size-4" />
                    )}
                  </Button>
                </div>
              </div>
            </form>
            <div className="mt-3 flex items-center justify-between gap-2 text-[10px] text-muted-foreground/70">
              <span>Codex có thể mắc lỗi. Hãy kiểm tra kết quả quan trọng.</span>
              <span className="hidden sm:inline">
                Enter để gửi <span className="mx-1.5">·</span> Shift + Enter xuống dòng
              </span>
            </div>
            {!chat.busy && chat.connection && (
              <div className="mt-2 text-center text-[10px] text-muted-foreground">
                {chat.connection}
              </div>
            )}
          </div>
        </footer>
        {chat.messages.length > 4 && (
          <Button
            className="absolute bottom-48 right-6 rounded-full bg-background shadow-sm"
            variant="outline"
            size="icon-sm"
            aria-label="Đến tin nhắn mới nhất"
            onClick={() => {
              follow.current = true
              bottom.current?.scrollIntoView({ behavior: 'smooth' })
            }}
          >
            <ArrowDown className="size-4" />
          </Button>
        )}
      </main>
      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open && !deleting) setDeleteTarget(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Xóa cuộc trò chuyện?</AlertDialogTitle>
            <AlertDialogDescription>
              “{deleteTarget?.name ?? 'Cuộc trò chuyện chưa có tên'}” và toàn bộ lịch sử sẽ bị xóa
              vĩnh viễn khỏi Codex, kể cả thread con nếu có. Không thể hoàn tác.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {chat.error && (
            <p role="alert" className="text-sm text-destructive">
              {chat.error}
            </p>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Hủy</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={deleting}
              onClick={async () => {
                if (!deleteTarget) return
                setDeleting(true)
                if (await chat.deleteThread(deleteTarget)) {
                  if (chat.selected?.id === deleteTarget.id) setDraft('')
                  setDeleteTarget(null)
                }
                setDeleting(false)
              }}
            >
              {deleting ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Trash2 className="size-4" />
              )}
              {deleting ? 'Đang xóa…' : 'Xóa vĩnh viễn'}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
