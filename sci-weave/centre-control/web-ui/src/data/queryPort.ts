import type { DashboardSnapshot } from '@/domain/dashboard'

export interface DashboardQueryPort {
  getSnapshot(signal?: AbortSignal): Promise<DashboardSnapshot>
}
