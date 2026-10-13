'use client'
import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from './api'

export function useApi<T>(path: string) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const load = useCallback(() => {
    setLoading(true)
    api<T>(path).then(d => { setData(d); setError(null) }).catch(e => setError(e)).finally(() => setLoading(false))
  }, [path])
  useEffect(load, [load])
  return { data, error, loading, reload: load }
}
