/* Two-tier save engine: local journal (≤0.7 s) + idempotent server sync with If-Match (FR05, FR06, AT03, AT04). */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, uid } from "../api/client";
import type { Doc } from "../api/types";
import { journalClear, journalGet, journalPut } from "./offline";

export type SaveState = "idle" | "local" | "syncing" | "synced" | "offline" | "conflict" | "error";

export function useAutosave(doc: Doc | null, onSynced: (d: Doc) => void) {
  const [state, setState] = useState<SaveState>("idle");
  const [lastSynced, setLastSynced] = useState<string | null>(null);
  const [conflict, setConflict] = useState<{ server: Doc; local: any } | null>(null);
  const version = useRef<number>(0);
  const docId = useRef<string | null>(null);
  const localTimer = useRef<number | undefined>(undefined);
  const syncTimer = useRef<number | undefined>(undefined);
  const latest = useRef<any>(null);
  const syncing = useRef<Promise<void> | null>(null);

  useEffect(() => {
    docId.current = doc?.id || null;
    version.current = doc?.version || 0;
    setState("idle");
    setConflict(null);
    setLastSynced(doc?.updated_at || null);
  }, [doc?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const sync = useCallback(async (): Promise<void> => {
    if (syncing.current) return syncing.current;
    const id = docId.current;
    if (!id) return;
    const run = (async () => {
      const entry = await journalGet(id);
      if (!entry) return;
      setState("syncing");
      try {
        const res = await api<Doc & { created: boolean }>(`/v1/documents/${id}`, {
          method: "PUT",
          headers: { "If-Match": `W/"${version.current}"` },
          body: { content_json: entry.content, kind: "autosave", client_save_id: entry.saveId },
        });
        version.current = res.version;
        await journalClear(id, entry.saveId);
        const newer = await journalGet(id);
        if (newer) await journalPut({ ...newer, baseVersion: res.version });
        setLastSynced(new Date().toISOString());
        setState(newer ? "local" : "synced");
        onSynced(res);
      } catch (e) {
        if (e instanceof ApiError && e.status === 412) {
          const server = await api<Doc>(`/v1/documents/${id}`);
          setConflict({ server, local: entry.content });
          setState("conflict");
        } else if (e instanceof ApiError) {
          setState("error");
        } else {
          setState("offline"); // network failure: the journal keeps the text safe
        }
      }
    })();
    syncing.current = run;
    try {
      await run;
    } finally {
      syncing.current = null;
    }
  }, [onSynced]);

  const change = useCallback((content: any) => {
    latest.current = content;
    window.clearTimeout(localTimer.current);
    window.clearTimeout(syncTimer.current);
    localTimer.current = window.setTimeout(async () => {
      if (!docId.current) return;
      await journalPut({ documentId: docId.current, content, baseVersion: version.current, saveId: uid(), savedAt: Date.now() });
      setState((s) => (s === "conflict" ? s : "local"));
      syncTimer.current = window.setTimeout(() => void sync(), 1500);
    }, 600);
  }, [sync]);

  // retry when the network comes back and periodically while offline
  useEffect(() => {
    const on = () => void sync();
    window.addEventListener("online", on);
    const t = window.setInterval(() => { if (state === "offline" || state === "local") void sync(); }, 10_000);
    return () => { window.removeEventListener("online", on); window.clearInterval(t); };
  }, [sync, state]);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (state === "local" || state === "syncing" || state === "offline") { e.preventDefault(); }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [state]);

  const flush = useCallback(async () => {
    window.clearTimeout(syncTimer.current);
    if (localTimer.current && latest.current && docId.current) {
      window.clearTimeout(localTimer.current);
      await journalPut({ documentId: docId.current, content: latest.current, baseVersion: version.current, saveId: uid(), savedAt: Date.now() });
    }
    latest.current = null;
    await sync();
  }, [sync]);

  /** Conflict resolution that never destroys history: either keep mine as a new revision on top, or take theirs. */
  const resolve = useCallback(async (choice: "mine" | "theirs") => {
    const id = docId.current;
    if (!id || !conflict) return null;
    if (choice === "mine") {
      version.current = conflict.server.version;
      setConflict(null);
      await sync();
      return null;
    }
    await journalClear(id);
    version.current = conflict.server.version;
    setConflict(null);
    setState("synced");
    return conflict.server;
  }, [conflict, sync]);

  const checkpoint = useCallback(async (content: any, label: string) => {
    await flush();
    const id = docId.current;
    if (!id) return null;
    const res = await api<Doc>(`/v1/documents/${id}`, {
      method: "PUT", headers: { "If-Match": `W/"${version.current}"` },
      body: { content_json: content, kind: "checkpoint", label, client_save_id: uid() },
    });
    version.current = res.version;
    await journalClear(id);
    setState("synced");
    setLastSynced(new Date().toISOString());
    onSynced(res);
    return res;
  }, [flush, onSynced]);

  return { state, lastSynced, conflict, change, flush, resolve, checkpoint, setVersion: (v: number) => { version.current = v; } };
}

export const SAVE_LABEL: Record<SaveState, [string, string]> = {
  idle: ["", "جاهز"],
  local: ["warn", "محفوظ محلياً"],
  syncing: ["info", "جارٍ المزامنة…"],
  synced: ["ok", "محفوظ على الخادم"],
  offline: ["bad", "غير متصل — محفوظ محلياً"],
  conflict: ["bad", "تعارض نسخة"],
  error: ["bad", "تعذر الحفظ"],
};
