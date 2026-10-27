import type { Resource } from '../../types/models'

export type ResourceFilters = {
  search: string; area: string; source: string; status: string
  revision: 'all' | 'due' | 'upcoming' | 'unscheduled'
  sort: 'updated' | 'title' | 'revision'
}
export const emptyFilters: ResourceFilters = {
  search: '', area: '', source: '', status: '', revision: 'all', sort: 'updated',
}

export function filterResources(resources: Resource[], filters: ResourceFilters, today: string): Resource[] {
  const query = filters.search.trim().toLocaleLowerCase()
  return resources.filter((resource) => {
    const searchable = [resource.title, ...resource.tags, resource.notes].join(' ').toLocaleLowerCase()
    return (!query || searchable.includes(query))
      && (!filters.area || resource.area === filters.area)
      && (!filters.source || resource.source === filters.source)
      && (!filters.status || resource.status === filters.status)
      && (filters.revision === 'all'
        || (filters.revision === 'due' && !!resource.nextRevisionDate && resource.nextRevisionDate <= today)
        || (filters.revision === 'upcoming' && !!resource.nextRevisionDate && resource.nextRevisionDate > today)
        || (filters.revision === 'unscheduled' && !resource.nextRevisionDate))
  }).sort((a, b) => {
    if (filters.sort === 'title') return a.title.localeCompare(b.title) || a.id.localeCompare(b.id)
    if (filters.sort === 'revision') return (a.nextRevisionDate ?? '9999-99-99').localeCompare(b.nextRevisionDate ?? '9999-99-99') || a.title.localeCompare(b.title)
    return b.updatedAt.localeCompare(a.updatedAt) || a.title.localeCompare(b.title)
  })
}
