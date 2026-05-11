import type { VersionEntry } from './branding'

export const VERSION_ENTRIES: VersionEntry[] = [
  {
    version: 'v2.14',
    date: '2026-05-11',
    changes: [
      { type: 'feat', text: '新增合规审查工作台账生成：上传 OA 流程表单及审批记录 PDF，系统提取重大事项、董事会/总办会程序、各单位审查意见、负责人签署时间和背景材料，预览确认后写入长期累计台账' },
      { type: 'feat', text: '合规审查台账支持多会签单位多行展开，审查单位列显示部门名称；管理员可在功能内维护部门负责人配置，默认内置财务部、审计部/法务合规部、人力资源部等负责人名单' },
      { type: 'fix', text: '补充合规审查台账单元与回归测试：覆盖意见归一化、多会签展开、Excel 合并单元格、负责人配置持久化和累计台账自然序号追加；后端全量 52 条测试通过' },
    ],
  },
  {
    version: 'v2.13',
    date: '2026-05-11',
    changes: [
      { type: 'feat', text: '审计问题分析新增双模型交叉校验：模型A完成初步分类后，模型B逐条审查并提出修正建议；分歧行以橙色高亮，展示A/B两种分类选项，用户手动确认后生成报告，提升分类可信度' },
      { type: 'feat', text: '审计报告图表新增下载/复制功能：每张饼图右上角提供「下载 PNG」和「复制图片」按钮，以2倍分辨率截图，可直接粘贴到 Word/PPT' },
    ],
  },
  {
    version: 'v2.12',
    date: '2026-05-11',
    changes: [
      { type: 'feat', text: '培训统计新增培训时长（课时）：AI 自动从培训通知 PDF 中提取开始时间和结束时间，按"总分钟数 ÷ 40 = 课时"计算；多天培训支持天数×单日时长；课时精度保留 1 位小数' },
      { type: 'feat', text: '培训确认页新增「培训开始时间」「培训结束时间」「培训时长（课时）」三个可编辑字段，识别不准时可手动修正后再写入' },
      { type: 'feat', text: '培训统计表 Excel 新增「培训时长（课时）」列（位于参与人数之后），已有台账文件自动迁移表头，无需手动处理旧数据' },
    ],
  },
  {
    version: 'v2.11',
    date: '2026-05-08',
    changes: [
      { type: 'feat', text: '引入 Noto Sans SC 字体：替换系统默认中文字体，中文显示更精致统一' },
      { type: 'feat', text: '空会话欢迎页：无对话时显示 6 宫格功能入口卡片，点击直接触发对应技能，告别空白页面' },
      { type: 'feat', text: '侧边栏技能图标升级：每个技能添加专属彩色背景圆角块（培训蓝、台账紫、授权绿、合并琥珀、审计红），一眼可辨' },
      { type: 'feat', text: '输入框视觉优化：input 与发送按钮合并为统一外壳容器，聚焦时亮起 indigo 双圈发光效果' },
      { type: 'feat', text: '整体配色调整：主背景改为更深的深蓝色（#0a0f1e），滚动条换用 indigo 色调，视觉层次更清晰' },
    ],
  },
  {
    version: 'v2.10',
    date: '2026-05-08',
    changes: [
      { type: 'fix', text: '修复所有 async def 端点中的事件循环阻塞问题（根本原因）：培训提取、案件台账提取、授权请示生成、审计分析均调用了同步 LLM/PDF/OCR 函数，直接运行于事件循环，在 Session A 处理期间（10~60 秒）完全阻塞了 Session B 的所有请求；现全部通过 asyncio.to_thread 卸载到线程池，事件循环始终保持畅通' },
      { type: 'fix', text: '模型路由配置读取改为内存缓存（_get_cached_routes）：消除每次 chat 请求中 resolve_intent_model 等函数触发的 3 次同步磁盘读取，彻底杜绝 async 端点内的文件 I/O 阻塞' },
      { type: 'fix', text: '聊天流式回复中每个 token 后增加 await asyncio.sleep(0)：主动让出事件循环，防止高频 token 流在 Starlette 缓冲未满时连续占用循环导致其他协程饿死' },
      { type: 'fix', text: 'SQLite 启用 WAL 模式（journal_mode=WAL）并设置 busy_timeout=5000ms：允许多连接并发读写 auth.db，彻底消除 get_current_user 并发 db.commit() 时的 SQLITE_BUSY 错误' },
      { type: 'fix', text: '聊天 StreamingResponse 增加 Cache-Control: no-cache、X-Accel-Buffering: no 响应头，防止代理层缓冲 SSE 数据' },
    ],
  },
  {
    version: 'v2.9',
    date: '2026-05-08',
    changes: [
      { type: 'fix', text: '聊天端点改为全异步（async def + AsyncOpenAI）：LLM 调用（意图分类、流式回答）均通过 await 非阻塞执行，事件循环在每个 token 之间都可响应其他会话的请求（新建会话、切换会话、发消息），彻底消除多会话并行时的阻塞和排队问题' },
    ],
  },
  {
    version: 'v2.8',
    date: '2026-05-08',
    changes: [
      { type: 'feat', text: '消息状态改为按会话独立存储：Session A 正在流式回答时切换到 Session B，A 的回答继续在后台写入 A 自己的消息队列，切回后内容完整呈现；Flow（培训统计/案件台账等）在后台完成时，完成消息也正确归入触发该 Flow 的会话，而非当前活跃会话，实现真正的多会话并行互不干扰' },
    ],
  },
  {
    version: 'v2.7',
    date: '2026-05-08',
    changes: [
      { type: 'feat', text: '多会话并行处理：在一个会话执行培训统计、案件台账等任务时，可自由切换到其他会话处理不同事务，切回后原任务状态完整保留（含上传文件、识别结果、待确认数据）' },
    ],
  },
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
