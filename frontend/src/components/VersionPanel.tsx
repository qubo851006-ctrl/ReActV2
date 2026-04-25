import { useState } from 'react'

interface VersionEntry {
  version: string
  date: string
  changes: { type: 'feat' | 'fix' | 'refactor'; text: string }[]
}

const VERSIONS: VersionEntry[] = [
  {
    version: 'v2.0',
    date: '2026-04-25',
    changes: [
      { type: 'feat', text: '通用对话引入轻量 ReAct：助手现在了解系统全部功能，能根据上下文主动引导用户进入对应工作流，无需每次手动点击卡片' },
      { type: 'refactor', text: '意图识别由 5 次独立 LLM 调用优化为单次分类调用，聊天响应速度提升约 5 倍，新增意图只需在配置文件加一行描述' },
      { type: 'refactor', text: '新增工具注册表（tools/registry.py），统一管理 15 个 AI 工具函数及描述，为后续接入 ReAct 预留接口' },
      { type: 'refactor', text: '前端功能模块改为配置表驱动（FLOW_COMPONENTS / DOWNLOAD_ACTIONS / SKILL_TRIGGERS），新增功能仅需在表中加一行，不改主逻辑' },
    ],
  },
  {
    version: 'v1.5',
    date: '2026-04-24',
    changes: [
      { type: 'feat', text: '授权请示起草：同步生成授权书（法定代表人授权书格式）' },
      { type: 'feat', text: '授权请示起草：完成后自动追加授权委托台账（Excel），支持一键下载' },
      { type: 'feat', text: '授权台账文件自动创建，无需手动配置路径，存放于项目 data/授权台账/ 目录' },
    ],
  },
  {
    version: 'v1.4',
    date: '2026-04-24',
    changes: [
      { type: 'feat', text: '新增审计问题智能分析模块：上传汇总表，AI 双维度分类（问题类别 × 业务领域），可编辑后导出' },
      { type: 'fix', text: '修复 Excel 表头识别错误导致数据提取为空的问题' },
      { type: 'fix', text: '修复授权请示下载链接消失问题并优化 Word 生成格式' },
    ],
  },
  {
    version: 'v1.3',
    date: '2026-04-23',
    changes: [
      { type: 'feat', text: '新增三台账合并功能：以合同系统台账为主键，自动合并采购 / 财务台账，支持模糊匹配合同编号' },
    ],
  },
  {
    version: 'v1.2',
    date: '2026-04-22',
    changes: [
      { type: 'feat', text: '支持生产部署：FastAPI 托管前端静态文件，单进程启动' },
      { type: 'feat', text: '聊天中直接说"下载统计表/台账"即可自动触发文件下载' },
      { type: 'feat', text: '案件台账写入前增加确认步骤，完成后提供下载入口' },
      { type: 'fix', text: '下载改为内联按钮，避免浏览器弹窗拦截' },
      { type: 'refactor', text: '所有用户生成数据统一迁移到项目 data/ 目录' },
    ],
  },
  {
    version: 'v1.1',
    date: '2026-04-22',
    changes: [
      { type: 'feat', text: '培训签到人数识别加入自我反思二次核查，提升识别准确率' },
    ],
  },
  {
    version: 'v1.0',
    date: '2026-04-22',
    changes: [
      { type: 'feat', text: '法务合规部智能体 V1 上线：React + FastAPI 全栈重构，支持培训统计、案件台账、授权请示起草' },
    ],
  },
]

const FEATURES = [
  {
    icon: '📊',
    name: '培训统计及归档',
    steps: [
      '点击左侧"培训统计及归档"按钮，或直接在聊天中描述需求',
      '上传培训通知 PDF 和签到表图片（JPG/PNG）',
      '填写组织部门后点击"提取信息"，AI 自动识别培训主题、日期、人员名单',
      '确认信息后写入培训统计表，并自动归档文件',
      '可在聊天中说"下载培训统计表"随时导出 Excel',
    ],
  },
  {
    icon: '⚖️',
    name: '案件台账生成',
    steps: [
      '点击左侧"案件台账生成"按钮',
      '上传案件相关法律文书（PDF/DOCX/DOC，可多选）',
      'AI 自动识别文书类型（起诉状、判决书、仲裁裁决书等）并提取关键字段',
      '系统判断是否为台账已有案件，确认匹配关系后写入台账',
      '可在聊天中说"下载案件台账"随时导出 Excel',
    ],
  },
  {
    icon: '📝',
    name: '授权请示起草',
    steps: [
      '点击左侧"授权请示起草"按钮',
      '上传呈批件 PDF（支持文字版和扫描版，扫描版自动 OCR）',
      'AI 自动提取项目名称、文件编号、授权事项、授权单位、期限、份数等字段',
      '生成授权请示 Word 文档（规范散文格式）和授权书（法定代表人授权书）',
      '同时将本次授权记录追加到授权委托台账 Excel',
      '下载后，授权书中注册地址、法定代表人等空白处需人工填写',
    ],
  },
  {
    icon: '🔀',
    name: '三台账合并',
    steps: [
      '点击左侧"三台账合并"按钮',
      '上传合同系统台账 Excel（必填），采购/财务系统台账（可选）',
      '系统以合同编号为主键自动关联，支持大小写、全角括号等差异的模糊匹配',
      '合并完成后下载合并结果 Excel，包含匹配状态和来源标记',
    ],
  },
  {
    icon: '🔍',
    name: '审计问题分析',
    steps: [
      '点击左侧"审计问题分析"按钮',
      '上传审计发现问题汇总表 Excel（系统自动识别问题列）',
      'AI 对每条问题进行双维度分类：问题类别（内控/制度/资金/采购）× 业务领域（工程/酒店/物业/资产）',
      '在结果表格中可直接修改分类',
      '点击"导出 Excel"生成带分类结果的文件',
    ],
  },
]

const TYPE_BADGE: Record<string, string> = {
  feat: 'bg-indigo-500/20 text-indigo-300',
  fix: 'bg-amber-500/20 text-amber-300',
  refactor: 'bg-slate-500/20 text-slate-300',
}
const TYPE_LABEL: Record<string, string> = {
  feat: '新增',
  fix: '修复',
  refactor: '重构',
}

interface Props {
  open: boolean
  onClose: () => void
}

export default function VersionPanel({ open, onClose }: Props) {
  const [tab, setTab] = useState<'guide' | 'history'>('guide')

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      {/* Panel */}
      <div
        className={`
          fixed top-0 right-0 z-50 h-full w-[420px] max-w-full
          bg-slate-900 border-l border-slate-700/60 shadow-2xl
          flex flex-col
          transition-transform duration-300 ease-in-out
          ${open ? 'translate-x-0' : 'translate-x-full'}
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/60">
          <div>
            <div className="text-sm font-semibold text-white">功能说明 &amp; 版本记录</div>
            <div className="text-xs text-slate-500 mt-0.5">法务合规部智能体 · Created by 曲波</div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-700/60">
          {(['guide', 'history'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 py-2.5 text-sm transition-colors ${
                tab === t
                  ? 'text-indigo-400 border-b-2 border-indigo-400'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {t === 'guide' ? '📖 功能使用说明' : '🕐 版本更新记录'}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {tab === 'guide' ? (
            <div className="space-y-6">
              {FEATURES.map(f => (
                <div key={f.name}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-base">{f.icon}</span>
                    <span className="text-sm font-medium text-white">{f.name}</span>
                  </div>
                  <ol className="space-y-1.5 pl-1">
                    {f.steps.map((step, i) => (
                      <li key={i} className="flex gap-2 text-xs text-slate-400">
                        <span className="flex-shrink-0 w-4 h-4 rounded-full bg-slate-700 text-slate-400 flex items-center justify-center text-[10px] mt-0.5">
                          {i + 1}
                        </span>
                        <span>{step}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-5">
              {VERSIONS.map(v => (
                <div key={v.version}>
                  <div className="flex items-baseline gap-2 mb-2">
                    <span className="text-sm font-semibold text-white">{v.version}</span>
                    <span className="text-xs text-slate-500">{v.date}</span>
                  </div>
                  <ul className="space-y-1.5">
                    {v.changes.map((c, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-slate-400">
                        <span className={`flex-shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium ${TYPE_BADGE[c.type]}`}>
                          {TYPE_LABEL[c.type]}
                        </span>
                        <span>{c.text}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
