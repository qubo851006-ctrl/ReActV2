import type { VersionEntry } from './branding'

export const VERSION_ENTRIES: VersionEntry[] = [
  {
    version: 'v2.6',
    date: '2026-05-08',
    changes: [
      { type: 'feat', text: '图像模型新增 Qwen3 VL 8B（本地）选项，支持通过本地 Ollama 服务进行图像分析，在 .env 中配置 OLLAMA_BASE_URL 后即可启用' },
      { type: 'feat', text: '新增后端单元测试：Ollama 客户端路由逻辑、模型标签、签到表解析，共 25 个测试用例全部覆盖' },
    ],
  },
  {
    version: 'v2.5',
    date: '2026-04-30',
    changes: [
      { type: 'feat', text: '新增右上角文字模型与图像模型手工切换：普通对话可选择 Qwen2.5 72B、DeepSeek V3、GLM-5，图像与扫描件识别默认使用 Qwen2.5 VL 72B' },
      { type: 'feat', text: '新增运行时模型路由：模型列表、默认文字模型、默认意图识别模型、默认图像模型统一读取 data/model_routes.json，后续调整模型配置无需重启后端，刷新前端即可生效' },
      { type: 'feat', text: '培训签到图片识别、案件台账扫描版 PDF OCR、授权呈批件扫描版 PDF OCR 已接入图像模型选择' },
      { type: 'fix', text: '当用户询问“当前模型/你是什么模型”时，后端直接返回当前文字模型和图像模型，避免大模型自报身份不准确' },
      { type: 'fix', text: '默认文字模型与意图识别模型固定为 qwen2.5-72b，避免服务器旧 .env 中的 MODEL_CHAT 残留配置影响首次运行默认值' },
    ],
  },
  {
    version: 'v2.4',
    date: '2026-04-29',
    changes: [
      { type: 'fix', text: '补强所有上传入口安全校验：培训、授权请示、审计分析、台账合并、案件台账均增加文件名净化、扩展名白名单、大小限制、MIME 与文件头校验' },
      { type: 'fix', text: '修复案件文书归档路径风险：上传文件名和案件归档目录均限制在 data 目录内，防止路径穿越和非法文件名写入' },
      { type: 'fix', text: '案件台账写入改为事务式流程：cases.json 与 Excel 写入使用文件锁和原子替换，失败时回滚旧文件，避免 JSON、Excel 状态不一致' },
      { type: 'fix', text: 'LLM 与外部知识库 HTTP 客户端默认开启 TLS 证书校验，可通过 AI_HTTP_VERIFY_SSL 环境变量显式控制' },
      { type: 'fix', text: '会话 session_id 增加白名单格式和路径边界校验，会话历史与元数据改为文件锁 + 原子写入' },
      { type: 'refactor', text: '前端移除显式 any 类型，统一错误消息提取逻辑，提升 TypeScript 质量门禁稳定性' },
      { type: 'feat', text: '补充 Windows 服务器自动部署方案：GitHub master 有新提交后，服务器任务计划程序可自动更新、构建前端并重启后端服务' },
    ],
  },
  {
    version: 'v2.3',
    date: '2026-04-28',
    changes: [
      { type: 'feat', text: '新增用户登录与身份认证：基于 SQLite + HttpOnly Cookie 的会话管理，30 天免登录，支持密码短码登录' },
      { type: 'feat', text: '新增角色权限控制：管理员可管理用户、重置密码；普通用户仅访问自己的数据' },
      { type: 'feat', text: '新增操作审计日志：所有写入操作（台账、培训、授权请示）均记录操作人、时间和内容' },
      { type: 'feat', text: '新增多会话历史侧边栏：对话历史按会话隔离，可新建对话、切换历史会话、删除会话，体验与 ChatGPT 一致' },
      { type: 'feat', text: '每位用户拥有独立的对话历史，用户之间互不可见' },
    ],
  },
  {
    version: 'v2.2',
    date: '2026-04-28',
    changes: [
      { type: 'feat', text: '前端 SSE 流式输出：普通对话首字秒出、逐字显示，彻底告别等待全文生成后才渲染的体验' },
      { type: 'refactor', text: '意图分类与通用回复合并为单次 LLM 调用：原需 2 次串行调用，现 1 次分类（max_tokens=80）即可同时识别意图、提取公司名、判断 next_stage' },
      { type: 'refactor', text: '企业查询公司名提取内嵌到分类步骤：省去原本的第 2 次独立 LLM 调用，查询响应时间进一步缩短' },
    ],
  },
  {
    version: 'v2.1',
    date: '2026-04-28',
    changes: [
      { type: 'feat', text: '新增企业信息查询：在聊天框直接输入公司名称即可查询工商基本信息和司法风险，数据来源于 mcpmarket.cn 企业信息 MCP 服务' },
      { type: 'fix', text: '修复 Markdown 表格渲染：安装 remark-gfm 插件，消息中的表格语法正确显示为带边框的深色主题表格；同时修复 prose 类样式缺失问题' },
    ],
  },
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
      { type: 'feat', text: '法度云图 V1 上线：React + FastAPI 全栈重构，支持培训统计、案件台账、授权请示起草' },
    ],
  },
]
