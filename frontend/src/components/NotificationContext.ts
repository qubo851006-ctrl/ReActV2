import { createContext, useContext } from 'react'

export type NoticeType = 'success' | 'error' | 'info'

export interface NoticeInput {
  type: NoticeType
  title: string
  message?: string
  titleBadge?: string
}

export interface NotificationContextValue {
  notify: (notice: NoticeInput) => void
  notifySuccess: (title: string, message?: string) => void
  notifyError: (title: string, message?: string) => void
}

export const NotificationContext = createContext<NotificationContextValue | null>(null)

export function useNotifier() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotifier must be used inside NotificationProvider')
  }
  return context
}
