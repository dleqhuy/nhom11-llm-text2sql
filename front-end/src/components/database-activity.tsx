import { Check, ChevronRight, CircleAlert, Loader2 } from 'lucide-react'
import type { ToolCall } from '@/lib/api'

function Payload({ label, value }: { label: string; value: unknown }) {
  if (value == null) return null
  return (
    <div className="space-y-2">
      <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <pre className="max-h-80 overflow-auto rounded-lg bg-muted/60 p-3 text-[11px] leading-5 whitespace-pre-wrap break-words">
        {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}

export function DatabaseActivity({ tools }: { tools: ToolCall[] }) {
  return (
    <details className="group/activity ml-11 min-w-0 rounded-xl border border-border bg-white/40">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl px-4 py-3 text-xs focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3.5 shrink-0 transition-transform group-open/activity:rotate-90" />
        <span className="font-medium">Hoạt động database</span>
        <span className="ml-auto text-[10px] text-muted-foreground">{tools.length} lần gọi</span>
        {tools.some((tool) => tool.status === 'running') && (
          <Loader2 aria-label="Đang chạy" className="size-3 animate-spin" />
        )}
      </summary>
      <div className="border-t border-border px-4 py-2">
        {tools.map((tool) => (
          <details key={tool.id} className="group/tool border-b border-border last:border-0">
            <summary className="flex cursor-pointer list-none items-center gap-2 rounded py-3 text-xs text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
              <ChevronRight className="size-3 shrink-0 transition-transform group-open/tool:rotate-90" />
              {tool.status === 'running' ? (
                <Loader2 className="size-3 shrink-0 animate-spin" />
              ) : tool.status === 'failed' ? (
                <CircleAlert className="size-3 shrink-0 text-destructive" />
              ) : (
                <Check className="size-3 shrink-0 text-[#6e7d60]" />
              )}
              <code className="min-w-0 break-all text-[11px]">{tool.name}</code>
              <span className="ml-auto shrink-0 text-[10px]">
                {tool.status === 'running'
                  ? 'Đang chạy'
                  : tool.status === 'done'
                    ? 'Hoàn tất'
                    : 'Lỗi'}
              </span>
            </summary>
            <div className="space-y-3 pb-4 pl-5">
              {(tool.server || tool.durationMs != null) && (
                <div className="text-[10px] text-muted-foreground">
                  {[tool.server, tool.durationMs != null ? `${tool.durationMs} ms` : null]
                    .filter(Boolean)
                    .join(' · ')}
                </div>
              )}
              <Payload label="Tham số" value={tool.arguments} />
              <Payload label="Kết quả" value={tool.result} />
              <Payload label="Lỗi" value={tool.error} />
              {tool.result == null && tool.error == null && (
                <p className="text-xs text-muted-foreground">
                  {tool.status === 'running' ? 'Đang chờ kết quả…' : 'Không có kết quả được lưu.'}
                </p>
              )}
            </div>
          </details>
        ))}
      </div>
    </details>
  )
}
