const DB = "asha-vaani";
const STORE = "kv";
function idb() {
    return new Promise((resolve, reject) => {
        const r = indexedDB.open(DB, 1);
        r.onupgradeneeded = () => r.result.createObjectStore(STORE);
        r.onsuccess = () => resolve(r.result);
        r.onerror = () => reject(r.error);
    });
}
async function get(key) {
    const db = await idb();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, "readonly").objectStore(STORE).get(key);
        tx.onsuccess = () => resolve(tx.result);
        tx.onerror = () => reject(tx.error);
    });
}
async function put(key, value) {
    const db = await idb();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).put(value, key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}
async function del(key) {
    const db = await idb();
    return new Promise((resolve) => {
        const tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).delete(key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
    });
}
async function key() {
    let k = await get("draft-key");
    if (!k) {
        k = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
        await put("draft-key", k);
    }
    return k;
}
export function available() {
    return typeof indexedDB !== "undefined" && !!(globalThis.crypto && crypto.subtle);
}
export async function savePending(d) {
    if (!available())
        return false;
    try {
        const iv = crypto.getRandomValues(new Uint8Array(12));
        const data = new TextEncoder().encode(JSON.stringify(d));
        const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await key(), data);
        await put("pending", { iv, ct });
        return true;
    }
    catch {
        return false;
    }
}
export async function loadPending() {
    if (!available())
        return null;
    try {
        const rec = await get("pending");
        if (!rec)
            return null;
        const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: rec.iv }, await key(), rec.ct);
        return JSON.parse(new TextDecoder().decode(pt));
    }
    catch {
        return null;
    }
}
export async function clearPending() {
    if (available())
        await del("pending");
}
