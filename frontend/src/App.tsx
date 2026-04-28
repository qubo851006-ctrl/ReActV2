import { useState, useEffect, useRef } from 'react'
import type { ComponentType } from 'react'
import type { Message, Stage, FlowProps, SkillKey } from './types'
import { getHistory, clearHistory, sendChat, clearLedger, downloadTrainingExcel, downloadLedgerExcel } from './api'
import Sidebar from './components/Sidebar'
import ChatMessage from './components/ChatMessage'
import TrainingFlow from './components/TrainingFlow'
import LedgerFlow from './components/LedgerFlow'
import AuthFlow from './components/AuthFlow'
import LedgerMergeFlow from './components/LedgerMergeFlow'
import AuditFlow from './components/AuditFlow'
import VersionPanel from './components/VersionPanel'

// 新增 Flow 组件：在此表加一行，不改 App 主逻辑
const FLOW_COMPONENTS: Partial<Record<Stage, ComponentType<FlowProps>>> = {
  waiting_files: TrainingFlow,
  waiting_ledger_files: LedgerFlow,
  waiting_auth_file: AuthFlow,
  waiting_ledger_merge_files: LedgerMergeFlow,
  waiting_audit_file: AuditFlow,
}

// 新增下载功能：在此表加一行，不改 App 主逻辑
const DOWNLOAD_ACTIONS: Partial<Record<Stage, { label: string; fn: () => void }>> = {
  download_training_excel: { label: '下载培训统计表 Excel', fn: downloadTrainingExcel },
  download_ledger_excel: { label: '下载案件台账 Excel', fn: downloadLedgerExcel },
}

// 侧边栏技能按钮触发配置（新增技能在此加一行，并在 types.ts 的 SkillKey 里加成员）
const SKILL_TRIGGERS: Record<SkillKey, { msg: string; reply: string; stage: Stage }> = {
  training: {
    msg: '📊 培训统计及归档',
    reply: '好的！请上传以下两个文件：\n\n- 📄 **培训通知**（PDF 格式）\n- ✍️ **签到表**（图片格式：JPG / PNG）',
    stage: 'waiting_files',
  },
  ledger: {
    msg: '⚖️ 案件台账生成',
    reply: '好的！请上传案件的法律文书文件（支持 **PDF / DOCX / DOC**，可多选）。\n\n系统会自动识别文书类型，并判断是否为台账中的已有案件。',
    stage: 'waiting_ledger_files',
  },
  auth: {
    msg: '📝 授权请示起草',
    reply: '好的！请上传**呈批件 PDF**，系统将自动提取关键信息并生成授权请示 Word 文档。\n\n- 支持文字版 PDF（直接提取）\n- 支持扫描版 PDF（自动 OCR 识别）',
    stage: 'waiting_auth_file',
  },
  merge: {
    msg: '🔀 三台账合并',
    reply: '好的！请分别上传三个系统导出的 Excel 台账：\n\n- 📘 **合同系统台账**（必填，作为合并主键）\n- 📗 **采购系统台账**（可选）\n- 📙 **财务系统台账**（可选）\n\n系统将以合同编号为关键字段自动合并，支持大小写、全角括号等差异的模糊匹配。',
    stage: 'waiting_ledger_merge_files',
  },
  audit: {
    msg: '🔍 审计问题分析',
    reply: '好的！请上传**审计发现问题汇总表**（Excel 格式），系统将自动识别问题列，通过 AI 对每条问题进行**双维度分类**：\n\n- 📌 **问题类别**（内控缺陷 / 制度执行 / 资金管理 / 采购管理）\n- 🏢 **业务领域**（工程业务 / 酒店业务 / 物业管理 / 资产管理）\n\n分类完成后可审查修改，并生成可视化分析报告。',
    stage: 'waiting_audit_file',
  },
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [stage, setStage] = useState<Stage>('idle')
  const [input, setInput] = useState('')
  const [useKb, setUseKb] = useState(false)
  const [kbConvId, setKbConvId] = useState('')
  const [sending, setSending] = useState(false)
  const [versionOpen, setVersionOpen] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getHistory().then(({ messages: msgs }) => {
      setMessages(msgs)
    })
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, stage])


  function addMessage(role: 'user' | 'assistant', content: string) {
    setMessages(prev => [...prev, { role, content }])
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || sending || stage !== 'idle') return
    setInput('')
    addMessage('user', text)
    setSending(true)
    setStage('thinking')

    let gotFirstChunk = false
    let accumulated = ''

    try {
      const res = await sendChat(text, useKb, kbConvId, (chunk) => {
        accumulated += chunk
        if (!gotFirstChunk) {
          gotFirstChunk = true
          setStage('idle')
          addMessage('assistant', accumulated)
        } else {
          setMessages(prev => {
            const updated = [...prev]
            updated[updated.length - 1] = { role: 'assistant', content: accumulated }
            return updated
          })
        }
      })

      if (res.reply) {
        if (gotFirstChunk) {
          setMessages(prev => {
            const updated = [...prev]
            updated[updated.length - 1] = { role: 'assistant', content: res.reply }
            return updated
          })
        } else {
          addMessage('assistant', res.reply)
        }
      }

      if (res.kb_conversation_id) setKbConvId(res.kb_conversation_id)
      setStage(res.next_stage as Stage)
    } catch {
      if (gotFirstChunk) {
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = { role: 'assistant', content: '❌ 请求失败，请检查后端服务是否启动。' }
          return updated
        })
      } else {
        addMessage('assistant', '❌ 请求失败，请检查后端服务是否启动。')
      }
      setStage('idle')
    } finally {
      setSending(false)
    }
  }

  function triggerSkill(skill: SkillKey) {
    const { msg, reply, stage: nextStage } = SKILL_TRIGGERS[skill]
    addMessage('user', msg)
    addMessage('assistant', reply)
    setStage(nextStage)
  }

  function handleCancel() {
    addMessage('assistant', '已取消，如需重新操作请告诉我。')
    setStage('idle')
  }

  async function handleClearLedger() {
    const res = await clearLedger()
    addMessage('assistant', res.message)
  }

  async function handleClearChat() {
    await clearHistory()
    setMessages([])
    setKbConvId('')
  }

  function handleToggleKb(v: boolean) {
    setUseKb(v)
    if (!v) setKbConvId('')
  }

  const isIdle = stage === 'idle'
  const isDownloadStage = stage in DOWNLOAD_ACTIONS
  const ActiveFlow = FLOW_COMPONENTS[stage]
  const activeDownload = DOWNLOAD_ACTIONS[stage]

  return (
    <div className="flex h-screen w-full overflow-hidden bg-slate-950">
      <Sidebar
        stage={stage}
        useKb={useKb}
        onSkill={triggerSkill}
        onClearLedger={handleClearLedger}
        onClearChat={handleClearChat}
        onToggleKb={handleToggleKb}
      />

      {/* Main chat area */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Header */}
        <div className="flex-shrink-0 px-6 py-4 border-b border-slate-700/50 bg-slate-900/50 backdrop-blur flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold text-white m-0">法务合规部智能体V2</h1>
            <p className="text-xs text-slate-500 mt-0.5">AI 驱动的企业培训与法务管理系统</p>
          </div>
          <button
            onClick={() => setVersionOpen(true)}
            title="功能说明 &amp; 版本记录"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-700/50 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            功能说明
          </button>
        </div>

        <VersionPanel open={versionOpen} onClose={() => setVersionOpen(false)} />

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {messages.map((msg, i) => (
            <ChatMessage key={i} message={msg} />
          ))}

          {/* Flow 面板：由 FLOW_COMPONENTS 表驱动，新增功能不改此处 */}
          {ActiveFlow && (
            <ActiveFlow
              onComplete={reply => { addMessage('assistant', reply); setStage('idle') }}
              onCancel={handleCancel}
            />
          )}

          {/* 下载按钮：由 DOWNLOAD_ACTIONS 表驱动，新增下载不改此处 */}
          {activeDownload && (
            <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5 my-3">
              <div className="text-sm text-slate-300 mb-3">点击下载：</div>
              <button
                onClick={() => { activeDownload.fn(); setStage('idle') }}
                className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded-lg transition-colors"
              >
                📥 {activeDownload.label}
              </button>
            </div>
          )}

          {stage === 'thinking' && (
            <div className="flex items-center gap-2 text-slate-500 text-sm mb-4">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              思考中…
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="flex-shrink-0 px-6 py-4 border-t border-slate-700/50 bg-slate-900/30">
          <div className="flex gap-3 items-center">
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
              placeholder={isIdle || isDownloadStage ? '有什么可以帮您？' : '请完成当前操作…'}
              disabled={(!isIdle && !isDownloadStage) || sending}
              className="
                flex-1 bg-slate-800 border border-slate-700 rounded-xl
                px-4 py-3 text-sm text-white placeholder-slate-500
                outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30
                disabled:opacity-50 disabled:cursor-not-allowed transition-colors
              "
            />
            <button
              onClick={handleSend}
              disabled={(!isIdle && !isDownloadStage) || !input.trim() || sending}
              className="
                px-4 py-3 bg-indigo-600 hover:bg-indigo-500
                disabled:opacity-40 disabled:cursor-not-allowed
                text-white text-sm rounded-xl transition-colors
                flex items-center gap-2
              "
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
          {useKb && (
            <div className="text-xs text-indigo-400 mt-2 flex items-center gap-1">
              <span>📚</span> 知识库模式已启用
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
