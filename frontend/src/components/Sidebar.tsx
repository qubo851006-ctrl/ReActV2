import type { Stage, SkillKey } from '../types'
import type { AuthUser } from './AuthGate'

interface Props {
  stage: Stage
  useKb: boolean
  user: AuthUser
  onSkill: (skill: SkillKey) => void
  onClearLedger: () => void
  onClearChat: () => void
  onToggleKb: (v: boolean) => void
}

const skills = [
  { key: 'training' as const, icon: '📊', label: '培训统计及归档', desc: '上传培训通知+签到表，自动统计归档' },
  { key: 'ledger' as const,   icon: '⚖️', label: '案件台账生成',   desc: '上传法律文书，自动提取并更新台账' },
  { key: 'auth' as const,     icon: '📝', label: '授权请示起草',   desc: '上传呈批件，AI起草授权请示Word' },
  { key: 'merge' as const,    icon: '🔀', label: '三台账合并',     desc: '合并采购/合同/财务系统导出台账' },
  { key: 'audit' as const,   icon: '🔍', label: '审计问题分析',   desc: '上传审计汇总表，AI分类并生成报告' },
]

export default function Sidebar({ stage, useKb, user, onSkill, onClearLedger, onClearChat, onToggleKb }: Props) {
  const busy = stage !== 'idle'
  return (
    <aside className="w-60 flex-shrink-0 flex flex-col bg-slate-900 border-r border-slate-700/50 h-screen">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-slate-700/50">
        <div className="flex items-center gap-2">
          <span className="text-2xl">📋</span>
          <div>
            <div className="text-sm font-semibold text-white leading-tight">法务合规部智能体V2</div>
            <div className="text-xs text-slate-400 mt-0.5">AI 驱动的智能管理工具</div>
          </div>
        </div>
      </div>

      {/* Skills */}
      <div className="px-3 pt-4 flex-1 overflow-y-auto">
        <div className="text-xs font-medium text-slate-500 uppercase tracking-wider px-2 mb-2">快捷技能</div>
        {skills.map(s => (
          <button
            key={s.key}
            onClick={() => onSkill(s.key)}
            disabled={busy}
            className={`
              w-full text-left px-3 py-3 rounded-xl mb-1.5 transition-all duration-150
              ${busy
                ? 'opacity-40 cursor-not-allowed'
                : 'hover:bg-slate-700/60 active:bg-slate-700 cursor-pointer'}
              group
            `}
          >
            <div className="flex items-center gap-2.5">
              <span className="text-lg">{s.icon}</span>
              <div>
                <div className="text-sm font-medium text-slate-200 group-hover:text-white transition-colors">{s.label}</div>
                <div className="text-xs text-slate-500 mt-0.5 leading-tight">{s.desc}</div>
              </div>
            </div>
          </button>
        ))}

        {/* Divider */}
        <div className="border-t border-slate-700/50 my-3" />

        <div className="text-xs font-medium text-slate-500 uppercase tracking-wider px-2 mb-2">管理操作</div>
        {user.role === 'admin' && (
          <button
            onClick={onClearLedger}
            disabled={busy}
            className="w-full text-left px-3 py-2.5 rounded-lg mb-1 text-sm text-slate-400 hover:text-slate-200 hover:bg-slate-700/40 transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <span>🗂️</span> 清空台账
          </button>
        )}
        <button
          onClick={onClearChat}
          disabled={busy}
          className="w-full text-left px-3 py-2.5 rounded-lg mb-1 text-sm text-slate-400 hover:text-slate-200 hover:bg-slate-700/40 transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <span>🗑️</span> 清空对话
        </button>
      </div>

      {/* Knowledge base toggle */}
      <div className="px-4 py-4 border-t border-slate-700/50">
        <label className="flex items-center gap-3 cursor-pointer">
          <div className="relative">
            <input
              type="checkbox"
              className="sr-only peer"
              checked={useKb}
              onChange={e => onToggleKb(e.target.checked)}
            />
            <div className="w-9 h-5 bg-slate-600 rounded-full peer-checked:bg-indigo-500 transition-colors" />
            <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-4" />
          </div>
          <div>
            <div className="text-xs font-medium text-slate-300">📚 知识库问答</div>
            <div className="text-xs text-slate-500 mt-0.5">{useKb ? '已启用' : '使用企业知识库检索'}</div>
          </div>
        </label>
      </div>
    </aside>
  )
}
