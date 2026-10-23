import { fixtureSnapshot } from './fixtureSnapshot'
import type { DashboardQueryPort } from './queryPort'

export const fixtureQuery: DashboardQueryPort = {
  async getSnapshot() {
    return structuredClone(fixtureSnapshot)
  },
}
