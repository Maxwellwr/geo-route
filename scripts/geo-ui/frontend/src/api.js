async function getJson(url) {
  const resp = await fetch(url);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || resp.statusText || String(resp.status));
  }
  return data;
}

function mutate(url, options) {
  return fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
}

export function getGroups() {
  return getJson("/api/groups");
}

export function getEntries(slug) {
  return getJson("/api/groups/" + encodeURIComponent(slug) + "/entries");
}

export function createGroup(body) {
  return mutate("/api/groups", { method: "POST", body: JSON.stringify(body) });
}

export function patchGroup(slug, body) {
  return mutate("/api/groups/" + encodeURIComponent(slug), {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteGroup(slug) {
  return mutate("/api/groups/" + encodeURIComponent(slug), { method: "DELETE" });
}

export function addEntry(slug, body) {
  return mutate("/api/groups/" + encodeURIComponent(slug) + "/entries", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function patchEntry(slug, id, body) {
  return mutate(
    "/api/groups/" + encodeURIComponent(slug) + "/entries/" + id,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

export function deleteEntry(slug, id) {
  return mutate(
    "/api/groups/" + encodeURIComponent(slug) + "/entries/" + id,
    { method: "DELETE" },
  );
}

export async function getTags(type, query, limit = 30) {
  const params = new URLSearchParams({
    type,
    q: query || "",
    limit: String(limit),
  });
  const data = await getJson("/api/tags?" + params.toString());
  return data.tags || [];
}

export async function consumeSse(response, onLog) {
  const ct = response.headers.get("content-type") || "";
  if (!response.ok || !ct.includes("event-stream")) {
    let msg = "request failed";
    try {
      const data = await response.json();
      if (data && data.error) msg = data.error;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  if (!response.body) {
    throw new Error("empty SSE body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let eventName = "message";
  let dataLines = [];
  let exitCode = 0;

  const dispatch = () => {
    const raw = dataLines.join("\n");
    dataLines = [];
    const name = eventName;
    eventName = "message";
    if (!raw) return;
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = raw;
    }
    if (name === "log") {
      onLog(typeof parsed === "string" ? parsed : JSON.stringify(parsed));
    } else if (name === "done") {
      if (parsed && typeof parsed.exit === "number") {
        exitCode = parsed.exit;
      }
    }
  };

  const handleLine = (line) => {
    if (line.endsWith("\r")) line = line.slice(0, -1);
    if (line === "") {
      dispatch();
      return;
    }
    if (line.startsWith(":")) return;
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") eventName = value;
    else if (field === "data") dataLines.push(value);
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      handleLine(buf.slice(0, nl));
      buf = buf.slice(nl + 1);
    }
  }
  buf += decoder.decode();
  if (buf) handleLine(buf);
  if (dataLines.length) dispatch();
  return exitCode;
}
