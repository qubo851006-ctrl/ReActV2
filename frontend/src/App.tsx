import { useState, useEffect, useRef } from 'react'
import type { ComponentType } from 'react'
import type { Message, Stage, FlowProps, SkillKey, SessionMeta } from './types'
import {
  getHistory, clearHistory, sendChat, clearLedger, downloadTrainingExcel, downloadLedgerExcel,
  getSessions, createSession, deleteSession,
  getModelRoutes,
  setCurrentSessionId as setApiSessionId,
} from './api'
import Sidebar from './components/Sidebar'
import ChatMessage from './components/ChatMessage'
import TrainingFlow from './components/TrainingFlow'
import LedgerFlow from './components/LedgerFlow'
import AuthFlow from './components/AuthFlow'
import LedgerMergeFlow from './components/LedgerMergeFlow'
import AuditFlow from './components/AuditFlow'
import ComplianceFlow from './components/ComplianceFlow'
import VersionPanel from './components/VersionPanel'
import AuthGate from './components/AuthGate'
import type { AuthUser } from './components/AuthGate'
import UserMenu from './components/UserMenu'
import UserAdminPanel from './components/UserAdminPanel'
import { APP_TITLE } from './appMeta'
import ModelSelect from './components/ModelSelect'
import {
  DEFAULT_CHAT_MODEL,
  DEFAULT_VISION_MODEL,
  CHAT_MODEL_OPTIONS,
  VISION_MODEL_OPTIONS,
  hasModel,
  isChatModel,
  isVisionModel,
  type ChatModel,
  type ModelOption,
  type VisionModel,
} from './modelOptions'

// 新增 Flow 组件：在此表加一行，不改 App 主逻辑
const FLOW_COMPONENTS: Partial<Record<Stage, ComponentType<FlowProps>>> = {
  waiting_files: TrainingFlow,
  waiting_ledger_files: LedgerFlow,
  waiting_auth_file: AuthFlow,
  waiting_ledger_merge_files: LedgerMergeFlow,
  waiting_audit_file: AuditFlow,
  waiting_compliance_file: ComplianceFlow,
}

const CHAT_MODEL_STORAGE_KEY = 'fadu.chatModel'
const VISION_MODEL_STORAGE_KEY = 'fadu.visionModel'

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
  compliance: {
    msg: '📑 合规审查工作台账生成',
    reply: '好的！请上传 OA 流程表单及审批记录 PDF，系统会提取重大事项、程序、审查意见、签署时间和背景材料，确认后写入长期累计合规审查工作台账。',
    stage: 'waiting_compliance_file',
  },
}

export default function App() {
  // 每个会话独立维护消息列表：messagesMap[sessionId] = Message[]
  // 切换会话时不清空已缓存的消息，Session A 在后台流式输出时消息直接写入 A 的队列
  const [messagesMap, setMessagesMap] = useState<Record<string, Message[]>>({})
  const messagesMapRef = useRef<Record<string, Message[]>>({})

  const [stages, setStages] = useState<Record<string, Stage>>({})
  const [input, setInput] = useState('')
  const [useKb, setUseKb] = useState(false)
  const [useFayanKb, setUseFayanKb] = useState(false)
  const [chatModel, setChatModel] = useState<ChatModel>(() => {
    const saved = window.localStorage.getItem(CHAT_MODEL_STORAGE_KEY)
    return saved && isChatModel(saved) ? saved : (saved || DEFAULT_CHAT_MODEL)
  })
  const [visionModel, setVisionModel] = useState<VisionModel>(() => {
    const saved = window.localStorage.getItem(VISION_MODEL_STORAGE_KEY)
    return saved && isVisionModel(saved) ? saved : (saved || DEFAULT_VISION_MODEL)
  })
  const [chatModelOptions, setChatModelOptions] = useState<ModelOption[]>(CHAT_MODEL_OPTIONS)
  const [visionModelOptions, setVisionModelOptions] = useState<ModelOption[]>(VISION_MODEL_OPTIONS)
  const [kbConvId, setKbConvId] = useState('')
  const [sendingMap, setSendingMap] = useState<Record<string, boolean>>({})
  const [creatingSession, setCreatingSession] = useState(false)
  const [versionOpen, setVersionOpen] = useState(false)
  const [adminOpen, setAdminOpen] = useState(false)
  const [sessions, setSessions] = useState<SessionMeta[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string>('')
  const currentSessionIdRef = useRef<string>('')

  // 从 map 中取当前会话的派生值
  const messages = messagesMap[currentSessionId] ?? []
  const stage: Stage = stages[currentSessionId] ?? 'idle'
  const sending = sendingMap[currentSessionId] ?? false
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesMapRef.current = messagesMap
  }, [messagesMap])

  useEffect(() => {
    currentSessionIdRef.current = currentSessionId
  }, [currentSessionId])

  function setStage(next: Stage) {
    const id = currentSessionIdRef.current
    setStages(prev => ({ ...prev, [id]: next }))
  }

  useEffect(() => {
    async function init() {
      let list = await getSessions()
      if (list.length === 0) {
        const { session_id } = await createSession()
        list = await getSessions()
        setCurrentSessionId(session_id)
        setApiSessionId(session_id)
        setSessions(list)
        setMessagesMap({ [session_id]: [] })
      } else {
        setSessions(list)
        const first = list[0].id
        setCurrentSessionId(first)
        setApiSessionId(first)
        const { messages: msgs } = await getHistory(first)
        setMessagesMap({ [first]: msgs ?? [] })
      }
    }
    init()
  }, [])

  useEffect(() => {
    async function loadRoutes() {
      try {
        const routes = await getModelRoutes()
        const nextChatOptions = routes.chat_models.length ? routes.chat_models : CHAT_MODEL_OPTIONS
        const nextVisionOptions = routes.vision_models.length ? routes.vision_models : VISION_MODEL_OPTIONS
        setChatModelOptions(nextChatOptions)
        setVisionModelOptions(nextVisionOptions)
        setChatModel(current => hasModel(current, nextChatOptions) ? current : routes.default_chat_model)
        setVisionModel(current => hasModel(current, nextVisionOptions) ? current : routes.default_vision_model)
      } catch {
        // Keep bundled fallbacks when the runtime model route API is unavailable.
      }
    }
    loadRoutes()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, stage])

  useEffect(() => {
    window.localStorage.setItem(CHAT_MODEL_STORAGE_KEY, chatModel)
  }, [chatModel])

  useEffect(() => {
    window.localStorage.setItem(VISION_MODEL_STORAGE_KEY, visionModel)
  }, [visionModel])

  // 向当前会话添加消息（同步操作，安全使用 ref）
  function addMessage(role: 'user' | 'assistant', content: string) {
    const sessionId = currentSessionIdRef.current
    setMessagesMap(prev => ({
      ...prev,
      [sessionId]: [...(prev[sessionId] ?? []), { role, content }],
    }))
  }

  async function handleSend() {
    const text = input.trim()
    const sessionId = currentSessionId   // 调用时快照，防止异步期间切换会话
    if (!text || sending || stage !== 'idle') return

    function stageSet(next: Stage) {
      setStages(prev => ({ ...prev, [sessionId]: next }))
    }
    function sendingSet(v: boolean) {
      setSendingMap(prev => ({ ...prev, [sessionId]: v }))
    }
    // 消息始终写入发出请求时的 sessionId，不受后续切换影响
    function sessionAddMsg(role: 'user' | 'assistant', content: string) {
      setMessagesMap(prev => ({
        ...prev,
        [sessionId]: [...(prev[sessionId] ?? []), { role, content }],
      }))
    }

    setInput('')
    sessionAddMsg('user', text)
    sendingSet(true)
    stageSet('thinking')

    let gotFirstChunk = false
    let accumulated = ''

    try {
      const res = await sendChat(text, useKb, kbConvId, chatModel, visionModel, (chunk) => {
        accumulated += chunk
        if (!gotFirstChunk) {
          gotFirstChunk = true
          stageSet('idle')
          sessionAddMsg('assistant', accumulated)
        } else {
          setMessagesMap(prev => {
            const sessionMsgs = prev[sessionId] ?? []
            const updated = [...sessionMsgs]
            updated[updated.length - 1] = { role: 'assistant', content: accumulated }
            return { ...prev, [sessionId]: updated }
          })
        }
      }, useFayanKb)

      if (res.reply) {
        if (gotFirstChunk) {
          setMessagesMap(prev => {
            const sessionMsgs = prev[sessionId] ?? []
            const updated = [...sessionMsgs]
            updated[updated.length - 1] = { role: 'assistant', content: res.reply }
            return { ...prev, [sessionId]: updated }
          })
        } else {
          sessionAddMsg('assistant', res.reply)
        }
      }

      if (res.kb_conversation_id) setKbConvId(res.kb_conversation_id)
      stageSet(res.next_stage as Stage)
    } catch {
      if (gotFirstChunk) {
        setMessagesMap(prev => {
          const sessionMsgs = prev[sessionId] ?? []
          const updated = [...sessionMsgs]
          updated[updated.length - 1] = { role: 'assistant', content: '❌ 请求失败，请检查后端服务是否启动。' }
          return { ...prev, [sessionId]: updated }
        })
      } else {
        sessionAddMsg('assistant', '❌ 请求失败，请检查后端服务是否启动。')
      }
      stageSet('idle')
    } finally {
      sendingSet(false)
    }
  }

  function triggerSkill(skill: SkillKey) {
    const { msg, reply, stage: nextStage } = SKILL_TRIGGERS[skill]
    addMessage('user', msg)
    addMessage('assistant', reply)
    setStage(nextStage)
  }

  async function handleClearLedger() {
    const res = await clearLedger()
    addMessage('assistant', res.message)
  }

  async function handleClearChat() {
    await clearHistory(currentSessionId)
    setMessagesMap(prev => ({ ...prev, [currentSessionId]: [] }))
    setKbConvId('')
  }

  async function switchSession(sessionId: string) {
    setCurrentSessionId(sessionId)
    setApiSessionId(sessionId)
    setKbConvId('')
    // 若该会话消息已缓存在内存中，直接切换显示，无需重新请求后端
    // 这样可保留会话切换期间收到的流式消息和 Flow 完成消息
    if (!messagesMapRef.current[sessionId]) {
      const { messages: msgs } = await getHistory(sessionId)
      setMessagesMap(prev => ({ ...prev, [sessionId]: msgs ?? [] }))
    }
  }

  async function handleNewSession() {
    if (creatingSession) return
    setCreatingSession(true)
    try {
      const { session_id } = await createSession()
      const list = await getSessions()
      setSessions(list)
      // 新会话消息为空，直接写入缓存并切换，无需请求后端历史
      setMessagesMap(prev => ({ ...prev, [session_id]: [] }))
      setCurrentSessionId(session_id)
      setApiSessionId(session_id)
      setKbConvId('')
    } finally {
      setCreatingSession(false)
    }
  }

  async function handleDeleteSession(sessionId: string) {
    await deleteSession(sessionId)
    const list = await getSessions()
    setSessions(list)
    // 清理已删除会话的内存缓存
    setMessagesMap(prev => {
      const next = { ...prev }
      delete next[sessionId]
      return next
    })
    if (currentSessionId === sessionId) {
      if (list.length > 0) {
        await switchSession(list[0].id)
      } else {
        await handleNewSession()
      }
    }
  }

  function handleToggleKb(v: boolean) {
    setUseKb(v)
    if (!v) setKbConvId('')
  }

  function handleToggleFayanKb(v: boolean) {
    setUseFayanKb(v)
  }

  const isIdle = stage === 'idle'
  const isDownloadStage = stage in DOWNLOAD_ACTIONS
  const activeDownload = DOWNLOAD_ACTIONS[stage]

  return (
    <AuthGate>
      {(user: AuthUser, onLogout: () => void) => (
    <div className="flex h-screen w-full overflow-hidden bg-slate-950">
      <Sidebar
        stage={stage}
        useKb={useKb}
        useFayanKb={useFayanKb}
        user={user}
        sessions={sessions}
        currentSessionId={currentSessionId}
        creatingSession={creatingSession}
        onSkill={triggerSkill}
        onClearLedger={handleClearLedger}
        onClearChat={handleClearChat}
        onToggleKb={handleToggleKb}
        onToggleFayanKb={handleToggleFayanKb}
        onNewSession={handleNewSession}
        onSwitchSession={switchSession}
        onDeleteSession={handleDeleteSession}
      />

      {/* Main chat area */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Header */}
        <div className="flex-shrink-0 px-6 py-4 border-b border-slate-700/50 bg-slate-900/50 backdrop-blur flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold text-white m-0">{APP_TITLE}</h1>
          </div>
          <div className="flex items-center gap-2">
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
            <ModelSelect
              label="文字模型"
              title="选择本次对话使用的大模型"
              value={chatModel}
              options={chatModelOptions}
              onChange={setChatModel}
              disabled={sending}
            />
            <ModelSelect
              label="图像模型"
              title="选择图片和扫描件识别使用的视觉模型"
              value={visionModel}
              options={visionModelOptions}
              onChange={setVisionModel}
              disabled={sending}
            />
            <UserMenu user={user} onLogout={onLogout} onOpenAdmin={() => setAdminOpen(true)} />
          </div>
        </div>

        <VersionPanel open={versionOpen} onClose={() => setVersionOpen(false)} />
        {user.role === 'admin' && (
          <UserAdminPanel open={adminOpen} onClose={() => setAdminOpen(false)} currentUser={user} />
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {messages.length === 0 && stage === 'idle' && (
            <div className="h-full flex flex-col items-center justify-center select-none">
              <div className="text-4xl mb-3">📋</div>
              <div className="text-lg font-semibold text-slate-200 mb-1">法度云图</div>
              <div className="text-sm text-slate-500 mb-8">AI 驱动的法务合规智能工具</div>
              <div className="grid grid-cols-2 gap-3 w-full max-w-md">
                {[
                  { icon: '📊', label: '培训统计', desc: '培训通知 + 签到表归档', color: 'border-blue-500/30 hover:border-blue-500/60 hover:bg-blue-500/5',    key: 'training' as const },
                  { icon: '⚖️', label: '案件台账', desc: '法律文书 → 台账提取',   color: 'border-violet-500/30 hover:border-violet-500/60 hover:bg-violet-500/5', key: 'ledger'   as const },
                  { icon: '📝', label: '授权请示', desc: '呈批件 → 授权书起草',   color: 'border-emerald-500/30 hover:border-emerald-500/60 hover:bg-emerald-500/5',key: 'auth'     as const },
                  { icon: '🔀', label: '三台账合并', desc: '合同/采购/财务合并',  color: 'border-amber-500/30 hover:border-amber-500/60 hover:bg-amber-500/5',    key: 'merge'    as const },
                  { icon: '🔍', label: '审计分析', desc: 'AI分类审计问题',        color: 'border-red-500/30 hover:border-red-500/60 hover:bg-red-500/5',          key: 'audit'    as const },
                  { icon: '📑', label: '合规审查台账', desc: 'OA审批PDF → 累计台账', color: 'border-cyan-500/30 hover:border-cyan-500/60 hover:bg-cyan-500/5', key: 'compliance' as const },
                  { icon: '💬', label: '直接对话', desc: '询问、查询、或聊任意话题', color: 'border-slate-600/50 hover:border-slate-500 hover:bg-slate-700/20',    key: null },
                ].map(item => (
                  <button
                    key={item.label}
                    onClick={() => item.key && triggerSkill(item.key)}
                    className={`text-left px-4 py-3 rounded-xl border bg-slate-800/40 transition-all ${item.color}`}
                  >
                    <div className="text-xl mb-1">{item.icon}</div>
                    <div className="text-sm font-medium text-slate-200">{item.label}</div>
                    <div className="text-xs text-slate-500 mt-0.5">{item.desc}</div>
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((msg, i) => (
            <ChatMessage key={i} message={msg} />
          ))}

          {/* Flow 面板：所有会话的 Flow 同时挂载，当前会话可见，其余隐藏
               这样切换会话时组件不会卸载，内部处理状态（上传进度、识别结果）完整保留
               Flow 完成/取消消息直接写入对应会话的 messagesMap，切回后即可看到 */}
          {Object.entries(stages).map(([sid, sStage]) => {
            const FlowComp = FLOW_COMPONENTS[sStage]
            if (!FlowComp) return null
            return (
              <div key={sid} className={sid === currentSessionId ? '' : 'hidden'}>
                <FlowComp
                  onComplete={reply => {
                    setMessagesMap(prev => ({
                      ...prev,
                      [sid]: [...(prev[sid] ?? []), { role: 'assistant' as const, content: reply }],
                    }))
                    setStages(prev => ({ ...prev, [sid]: 'idle' }))
                  }}
                  onCancel={() => {
                    setMessagesMap(prev => ({
                      ...prev,
                      [sid]: [...(prev[sid] ?? []), { role: 'assistant' as const, content: '已取消，如需重新操作请告诉我。' }],
                    }))
                    setStages(prev => ({ ...prev, [sid]: 'idle' }))
                  }}
                  visionModel={visionModel}
                  canManageResponsiblePersons={user.role === 'admin'}
                />
              </div>
            )
          })}

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

        {/* 输入栏 */}
        <div className="flex-shrink-0 px-6 py-4 border-t border-slate-700/40 bg-slate-900/20">
          <div className="flex items-center bg-slate-800/80 border border-slate-700/60 rounded-2xl px-1 py-1 gap-1 focus-within:border-indigo-500/60 focus-within:ring-2 focus-within:ring-indigo-500/20 transition-all">
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
              placeholder={isIdle || isDownloadStage ? '有什么可以帮您？' : '请完成当前操作…'}
              disabled={(!isIdle && !isDownloadStage) || sending}
              className="
                flex-1 bg-transparent border-none
                px-3 py-2.5 text-sm text-white placeholder-slate-500
                outline-none
                disabled:opacity-50 disabled:cursor-not-allowed
              "
            />
            <button
              onClick={handleSend}
              disabled={(!isIdle && !isDownloadStage) || !input.trim() || sending}
              className="
                flex-shrink-0 w-9 h-9 flex items-center justify-center
                bg-indigo-600 hover:bg-indigo-500
                disabled:opacity-40 disabled:cursor-not-allowed
                text-white rounded-xl transition-colors
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
      )}
    </AuthGate>
  )
}
