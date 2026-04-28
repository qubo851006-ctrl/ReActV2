import type { TrainingResult, LedgerPreview, LedgerCaseData, SessionMeta } from './types'

const BASE = '/api'

/** 当前 session ID，由 App.tsx 在切换/新建时更新 */
let _sid = ''
export function setCurrentSessionId(id: string) { _sid = id }
export function getCurrentSessionId() { return _sid }

/** 统一 fetch 封装：自动带 Cookie，401/403 派发全局登出事件 */
async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const r = await fetch(url, { ...init, credentials: 'include' })
  if (r.status === 401 || r.status === 403) {
    window.dispatchEvent(new Event('auth:unauthorized'))
    throw new Error('unauthorized')
  }
  return r
}

// ── Session 管理 ──────────────────────────────────────────────

export async function getSessions(): Promise<SessionMeta[]> {
  const r = await apiFetch(`${BASE}/chat/sessions`)
  const d = await r.json()
  return d.sessions ?? []
}

export async function createSession(): Promise<{ session_id: string; title: string }> {
  const r = await apiFetch(`${BASE}/chat/sessions`, { method: 'POST' })
  return r.json()
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiFetch(`${BASE}/chat/sessions/${sessionId}`, { method: 'DELETE' })
}

export async function renameSession(sessionId: string, title: string): Promise<void> {
  await apiFetch(`${BASE}/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
}

export async function getHistory(sessionId: string) {
  const r = await apiFetch(`${BASE}/chat/history?session_id=${encodeURIComponent(sessionId)}`)
  return r.json()
}

export async function clearHistory(sessionId: string) {
  await apiFetch(`${BASE}/chat/history?session_id=${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
}

export async function sendChat(
  message: string,
  useKb: boolean,
  kbConvId: string,
  onChunk: (text: string) => void,
): Promise<{ reply: string; next_stage: string; kb_conversation_id: string }> {
  const resp = await apiFetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, use_kb: useKb, kb_conversation_id: kbConvId, session_id: _sid }),
  })
  if (!resp.ok) throw new Error(await resp.text())

  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result = { reply: '', next_stage: 'idle', kb_conversation_id: '' }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()!
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.type === 'chunk') onChunk(data.text)
        else if (data.type === 'done') result = {
          reply: data.reply ?? '',
          next_stage: data.next_stage ?? 'idle',
          kb_conversation_id: data.kb_conversation_id ?? '',
        }
      } catch { /* ignore malformed */ }
    }
  }
  return result
}

// ── 培训统计 ──────────────────────────────────────────────────

export async function extractTraining(
  noticePdf: File,
  signinImg: File,
  department: string,
): Promise<TrainingResult> {
  const form = new FormData()
  form.append('notice_pdf', noticePdf)
  form.append('signin_img', signinImg)
  form.append('department', department)
  const r = await apiFetch(`${BASE}/training/extract`, { method: 'POST', body: form })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function writeTraining(data: Omit<TrainingResult, 'excel_path' | 'confidence' | 'reflection_note'>) {
  const r = await apiFetch(`${BASE}/training/write`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...data, session_id: _sid }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export function downloadTrainingExcel() {
  window.open(`${BASE}/training/download-excel`, '_blank')
}

// ── 案件台账 ──────────────────────────────────────────────────

export async function extractLedger(
  files: File[],
  onLog: (log: string) => void,
): Promise<LedgerPreview> {
  const form = new FormData()
  for (const f of files) form.append('files', f)

  const resp = await apiFetch(`${BASE}/ledger/extract`, { method: 'POST', body: form })
  if (!resp.ok) throw new Error(await resp.text())

  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let previewData: any = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()!
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.log) onLog(data.log)
        if (data.preview) previewData = data
      } catch { /* ignore */ }
    }
  }
  return previewData
}

export async function writeLedger(
  caseData: LedgerCaseData,
  matchIdx: number | null,
  archiveDir: string,
): Promise<{ ok: boolean; case_count: number; reply: string }> {
  const r = await apiFetch(`${BASE}/ledger/write`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_data: caseData, match_idx: matchIdx, archive_dir: archiveDir, session_id: _sid }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function clearLedger() {
  const r = await apiFetch(`${BASE}/ledger/clear`, { method: 'POST' })
  return r.json()
}

export function downloadLedgerExcel() {
  window.open(`${BASE}/ledger/download-excel`, '_blank')
}

// ── 三台账合并 ────────────────────────────────────────────────

export interface MergeStats {
  total_contract: number
  matched_purchase: number
  matched_finance: number
  fully_matched: number
  partial_matched: number
  unmatched: number
}

export async function mergeLedgers(
  contractFile: File,
  purchaseFile: File | null,
  financeFile: File | null,
): Promise<MergeStats> {
  const form = new FormData()
  form.append('contract_file', contractFile)
  if (purchaseFile) form.append('purchase_file', purchaseFile)
  if (financeFile) form.append('finance_file', financeFile)
  const r = await apiFetch(`${BASE}/ledger-merge/merge`, { method: 'POST', body: form })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export function downloadMergedExcel() {
  window.open(`${BASE}/ledger-merge/download`, '_blank')
}

// ── 审计分析 ──────────────────────────────────────────────────

export interface AuditRow {
  seq: number
  issue: string
  description: string
  category_l1: string
  category_l2: string
  domain: string
}

export interface AuditAnalysisResult {
  rows: AuditRow[]
  total: number
}

export async function analyzeAudit(
  file: File,
  domains: string[],
): Promise<AuditAnalysisResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('domains', JSON.stringify(domains))
  const r = await apiFetch(`${BASE}/audit/analyze`, { method: 'POST', body: form })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function downloadAuditExcel(rows: AuditRow[], originalFilename: string) {
  const r = await apiFetch(`${BASE}/audit/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows, original_filename: originalFilename }),
  })
  if (!r.ok) throw new Error(await r.text())
  const blob = await r.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${originalFilename}_分类结果.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}

// ── 授权请示 ──────────────────────────────────────────────────

export async function processAuthRequest(pdfFile: File) {
  const form = new FormData()
  form.append('pdf_file', pdfFile)
  form.append('session_id', _sid)
  const r = await apiFetch(`${BASE}/auth-request/process`, { method: 'POST', body: form })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export function downloadDocx(base64: string, filename: string) {
  const bytes = atob(base64)
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  const blob = new Blob([arr], {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
