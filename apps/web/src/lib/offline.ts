/* Local-first save journal (FR05, NFR02, NFR03, AT03).
   Every keystroke burst is written to IndexedDB within ~0.7 s; server sync is separate and idempotent
   (client_save_id). If the tab crashes or the network drops, the journal is replayed on next load. */
import { createStore, del, get, keys, set } from "idb-keyval";

export interface JournalEntry {
  documentId: string;
  content: any;
  baseVersion: number;
  saveId: string;
  savedAt: number;
}

let store: ReturnType<typeof createStore> | null = null;
function db() {
  if (!store) store = createStore("nis-journal", "pending");
  return store;
}

const memory = new Map<string, JournalEntry>();

export async function journalPut(e: JournalEntry) {
  memory.set(e.documentId, e);
  try {
    await set(e.documentId, e, db());
  } catch {
    /* private mode: memory fallback only */
  }
}

export async function journalGet(documentId: string): Promise<JournalEntry | undefined> {
  try {
    return (await get(documentId, db())) || memory.get(documentId);
  } catch {
    return memory.get(documentId);
  }
}

export async function journalClear(documentId: string, saveId?: string) {
  const cur = await journalGet(documentId);
  if (saveId && cur && cur.saveId !== saveId) return; // a newer edit arrived meanwhile
  memory.delete(documentId);
  try {
    await del(documentId, db());
  } catch {
    /* ignore */
  }
}

export async function journalCount() {
  try {
    return (await keys(db())).length;
  } catch {
    return memory.size;
  }
}
