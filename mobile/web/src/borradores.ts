import type { Borrador } from './api'

export function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 15) | 64
  bytes[8] = (bytes[8] & 63) | 128
  const hex = [...bytes].map((x) => x.toString(16).padStart(2, '0')).join('')
  return hex.replace(/^(.{8})(.{4})(.{4})(.{4})(.{12})$/, '$1-$2-$3-$4-$5')
}

function usarDB<T>(modo: IDBTransactionMode, hacer: (store: IDBObjectStore) => IDBRequest<T>) {
  return new Promise<T>((resolve, reject) => {
    const open = indexedDB.open('validat3b-campo', 1)
    open.onupgradeneeded = () => open.result.createObjectStore('pendientes', { keyPath: 'id' })
    open.onerror = () => reject(open.error)
    open.onsuccess = () => {
      const db = open.result
      const tx = db.transaction('pendientes', modo)
      const request = hacer(tx.objectStore('pendientes'))
      tx.oncomplete = () => { db.close(); resolve(request.result) }
      tx.onabort = tx.onerror = () => { db.close(); reject(tx.error || request.error) }
    }
  })
}

export const borradores = () => usarDB('readonly', (store) => store.getAll()) as Promise<Borrador[]>
export const guardarBorrador = (draft: Borrador) => usarDB('readwrite', (store) => store.put(draft))
export const borrarBorrador = (id: string) => usarDB('readwrite', (store) => store.delete(id))
