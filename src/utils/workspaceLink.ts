export function workspaceFromSearch(search: string): string | undefined {
  const value = new URLSearchParams(search).get('workspace_id')
  return value && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value) ? value : undefined
}
