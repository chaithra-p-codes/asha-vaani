const TABLE = [
    [/^\/$/, "landing"],
    [/^\/onboarding\/?$/, "onboarding"],
    [/^\/app\/?$/, "overview"],
    [/^\/app\/new-visit\/?$/, "new-visit"],
    [/^\/app\/beneficiaries\/?$/, "beneficiaries"],
    [/^\/app\/beneficiaries\/([\w-]+)\/?$/, "beneficiary"],
    [/^\/app\/visits\/?$/, "visits"],
    [/^\/app\/visits\/([\w-]+)\/?$/, "visit"],
    [/^\/app\/follow-ups\/?$/, "followups"],
    [/^\/app\/referrals\/?$/, "referrals"],
    [/^\/app\/reports\/?$/, "reports"],
    [/^\/app\/settings\/?$/, "settings"],
];
export function match(pathname, search = "") {
    const query = new URLSearchParams(search);
    for (const [rx, name] of TABLE) {
        const m = rx.exec(pathname);
        if (m)
            return { name, id: m[1] ? decodeURIComponent(m[1]) : undefined, path: pathname, query };
    }
    return { name: "not-found", path: pathname, query };
}
const LEGACY = {
    home: "/app", consent: "/app/new-visit", visit: "/app/new-visit", visits: "/app/visits",
    followups: "/app/follow-ups", settings: "/app/settings",
};
/** Map a v1 hash URL ("#/visits/abc") to its new path, or null when the hash is not a legacy route. */
export function legacyPath(hash) {
    if (!hash.startsWith("#/"))
        return null;
    const [, page, id] = hash.split("/");
    const base = LEGACY[page || "home"];
    if (!base)
        return "/app";
    return page === "visits" && id ? `/app/visits/${encodeURIComponent(id)}` : base;
}
let listener = () => { };
export function current() {
    return match(location.pathname, location.search);
}
export function navigate(to, opts = {}) {
    const url = new URL(to, location.origin);
    const same = url.pathname === location.pathname && url.search === location.search;
    if (opts.replace)
        history.replaceState(null, "", url.pathname + url.search + url.hash);
    else if (!same)
        history.pushState(null, "", url.pathname + url.search + url.hash);
    listener(match(url.pathname, url.search));
}
/** Update the query string without re-rendering (used by filters so a reload keeps them). */
export function setQuery(params) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params))
        if (v)
            q.set(k, v);
    const s = q.toString();
    history.replaceState(null, "", location.pathname + (s ? `?${s}` : ""));
}
export function startRouter(onRoute) {
    listener = onRoute;
    window.addEventListener("popstate", () => listener(current()));
    document.addEventListener("click", (ev) => {
        if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey)
            return;
        const a = ev.target?.closest("a");
        if (!a || a.target || a.hasAttribute("download") || a.dataset.external !== undefined)
            return;
        const href = a.getAttribute("href") || "";
        if (!href.startsWith("/") || href.startsWith("//") || href.startsWith("/api/"))
            return;
        ev.preventDefault();
        navigate(href);
    });
    const legacy = legacyPath(location.hash);
    if (legacy)
        navigate(legacy, { replace: true });
    else
        listener(current());
}
