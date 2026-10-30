// Owner: Dev D
// GET /institutions once per session, as a lookup by id or AICTE code.
import { useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { components } from '../lib/api-types'
import type { InstitutionLookup } from './format'

type Institution = components['schemas']['Institution']

export function useInstitutions(): { lookup: InstitutionLookup; isLoading: boolean } {
  const query = useQuery({
    queryKey: ['institutions'],
    queryFn: () => api<Institution[]>('/institutions'),
    staleTime: Infinity,
    gcTime: Infinity,
  })

  const index = useMemo(() => {
    const map = new Map<string, Institution>()
    for (const item of query.data ?? []) {
      map.set(item.id, item)
      map.set(item.aicte_code, item)
    }
    return map
  }, [query.data])

  const lookup = useCallback<InstitutionLookup>((idOrCode) => index.get(idOrCode), [index])
  return { lookup, isLoading: query.isLoading }
}
