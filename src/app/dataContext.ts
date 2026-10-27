import { createContext, useContext } from 'react'
import type { AppData } from '../types/models'
import type { DataAction } from './dataActions'

export type DataContextValue = {
  data: AppData
  error: string | null
  rawRecovery: string | null
  blocked: boolean
  dispatch: (action: DataAction) => boolean
  reload: () => void
  replaceData: (data: AppData, confirmed: boolean) => boolean
}
export const DataContext = createContext<DataContextValue | null>(null)


export function useAppData(): DataContextValue {
  const context = useContext(DataContext)
  if (!context) throw new Error('useAppData must be used within DataProvider')
  return context
}
