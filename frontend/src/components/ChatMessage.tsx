import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'

interface Props {
  role: 'user' | 'assistant'
  content: string
}

export default function ChatMessage({ role, content }: Props) {
  const isUser = role === 'user'

  return (
    <div className={cn('flex gap-3 max-w-3xl', isUser ? 'ml-auto flex-row-reverse' : 'mr-auto')}>
      <div
        className={cn(
          'flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-semibold',
          isUser ? 'bg-indigo-600 text-white' : 'bg-white/10 text-gray-400'
        )}
      >
        {isUser ? 'U' : 'AI'}
      </div>
      <div
        className={cn(
          'px-4 py-3 rounded-2xl text-sm leading-relaxed max-w-[85%]',
          isUser
            ? 'bg-indigo-600 text-white rounded-tr-sm'
            : 'bg-white/[0.05] border border-white/[0.08] text-gray-200 rounded-tl-sm'
        )}
      >
        {isUser ? (
          content
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              ul: ({ children }) => <ul className="list-disc list-outside pl-5 space-y-1 my-2">{children}</ul>,
              ol: ({ children }) => <ol className="list-decimal list-outside pl-5 space-y-1 my-2">{children}</ol>,
              li: ({ children }) => <li className="text-gray-200">{children}</li>,
              strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
            }}
          >{content}</ReactMarkdown>
        )}
      </div>
    </div>
  )
}
