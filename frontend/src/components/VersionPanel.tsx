import { useState } from 'react'
import { APP_NAME } from '../branding'
import { VERSION_ENTRIES } from '../versionHistory'

const FEATURES = [
  {
    icon: '🤖',
    name: '模型切换与运行时路由',
    steps: [
      '右上角提供“文字模型”和“图像模型”两个下拉框，可在发送对话或处理图片前手工选择模型',
      '文字模型用于普通聊天回答；意图识别默认走 qwen2.5-72b，以保证流程判断稳定和响应速度',
      '图像模型用于培训签到图片识别、案件台账扫描件 OCR、授权呈批件扫描 OCR 等视觉任务',
      '模型列表和默认模型来自 data/model_routes.json，管理员后续调整该文件后无需重启后端，刷新前端即可加载新配置',
      '在聊天中询问“当前模型是什么”时，系统会直接返回当前文字模型和图像模型，而不是让大模型自行猜测',
    ],
  },
  {
    icon: '💬',
    name: '多会话对话历史',
    steps: [
      '登录后左侧边栏上方自动显示历史对话列表，按"今天 / 昨天 / 较早"分组',
      '点击"新建对话"创建空白会话，原有对话保留在列表中',
      '点击任意历史会话可立即切换，聊天记录自动恢复，工作流状态同步重置',
      '将鼠标悬停在会话条目上，右侧出现删除图标，单击即可删除该会话',
      '每条会话标题取自该会话第一条用户消息的前 20 个字，便于快速识别',
    ],
  },
  {
    icon: '🔐',
    name: '用户登录与权限管理',
    steps: [
      '首次访问自动跳转登录页，选择姓名后输入短码（由管理员设置）完成登录',
      '登录状态保持 30 天，关闭浏览器后再次打开无需重新登录',
      '右上角头像菜单可查看当前身份，点击"退出登录"可手动注销',
      '管理员可点击右上角"用户管理"，对所有用户进行增删、重置短码、切换角色等操作',
      '所有台账写入、培训归档、授权请示生成操作均记录审计日志',
    ],
  },
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
  {
    icon: '🏢',
    name: '企业信息查询',
    steps: [
      '无需点击按钮，直接在聊天框输入即可，例如："查一下XX公司的工商信息"',
      '支持模糊输入公司名称，系统自动匹配精确注册名称',
      '默认返回基本信息（注册资本、法定代表人、地址等）和司法风险（立案、执行、裁判文书数量）',
      '数据来源：mcpmarket.cn 企业信息 MCP 服务，查询结果仅供参考',
    ],
  },
  {
    icon: '🛡️',
    name: '安全校验与自动部署',
    steps: [
      '后端会统一校验上传文件的安全文件名、扩展名、文件大小、MIME 类型和文件头，异常文件会直接拒绝处理',
      '案件文书归档、会话历史、案件台账、培训台账、授权台账等关键文件写入均使用原子替换或文件锁，降低并发写入和半写入风险',
      '案件台账确认写入时，JSON 与 Excel 作为一组事务处理；任一步失败会返回错误并尽量回滚旧文件',
      '服务器端可通过 Windows 任务计划程序定时检测 GitHub master 分支更新，自动拉取最新代码、构建前端并重启后端',
      '生产环境请在服务器本地保留 .env 和 data 目录，不要将业务数据或密钥提交到 GitHub',
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
            <div className="text-xs text-slate-500 mt-0.5">{APP_NAME} · Created by 曲波</div>
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
              {VERSION_ENTRIES.map(v => (
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
