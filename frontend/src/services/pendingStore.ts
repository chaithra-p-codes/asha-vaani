/** Offline-safe pending drafts (recovery layer 3).
 * Drafts are AES-GCM encrypted with a NON-EXTRACTABLE WebCrypto key kept in IndexedDB.
 * A pending draft is never shown as saved; resuming it reconnects to the server session,
 * which reads the record back and requires a fresh confirmation. */
export interface PendingDraft {
  session_id: string;
  token: string;
  language: string;
  mode: string;
  record: Record<string, unknown>;
  updated_at: string;
  reason: string;
  /** "sync": the save could not reach the server (offline / save failed). "draft": left before confirming. */
  kind?: "draft" | "sync";
}

const DB = "asha-vaani";
const STORE = "kv";

function idb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => r.result.createObjectStore(STORE);
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

async function get<T>(key: string): Promise<T | undefined> {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly").objectStore(STORE).get(key);
    tx.onsuccess = () => resolve(tx.result as T | undefined);
    tx.onerror = () => reject(tx.error);
  });
}

async function put(key: string, value: unknown): Promise<void> {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(value, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function del(key: string): Promise<void> {
  const db = await idb();
  return new Promise((resolve) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => resolve();
  });
}

async function key(): Promise<CryptoKey> {
  let k = await get<CryptoKey>("draft-key");
  if (!k) {
    k = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
    await put("draft-key", k);
  }
  return k;
}

export function available(): boolean {
  return typeof indexedDB !== "undefined" && !!(globalThis.crypto && crypto.subtle);
}

export async function savePending(d: PendingDraft): Promise<boolean> {
  if (!available()) return false;
  try {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const data = new TextEncoder().encode(JSON.stringify(d));
    const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await key(), data);
    await put("pending", { iv, ct });
    return true;
  } catch {
    return false;
  }
}

export async function loadPending(): Promise<PendingDraft | null> {
  if (!available()) return null;
  try {
    const rec = await get<{ iv: Uint8Array; ct: ArrayBuffer }>("pending");
    if (!rec) return null;
    const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: rec.iv as unknown as BufferSource }, await key(), rec.ct);
    return JSON.parse(new TextDecoder().decode(pt)) as PendingDraft;
  } catch {
    return null;
  }
}

export async function clearPending(): Promise<void> {
  if (available()) await del("pending");
}
