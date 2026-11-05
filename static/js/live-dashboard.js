/*
 * Live updates for the VoltHub staff dashboard.
 *
 * Uses Server-Sent Events. When the server says too many live streams are
 * open (or the browser has no EventSource), it falls back to checking a JSON
 * endpoint every few seconds. Text is always inserted with textContent, never
 * innerHTML, because agent output and customer messages are not trusted HTML.
 */

function renderEvent(event, options = {}) {
  const item = document.createElement("div");
  item.className = "vh-event new agent-" + event.agent.toLowerCase();

  const head = document.createElement("div");
  head.className = "vh-event-head";

  const agent = document.createElement("span");
  agent.className = "vh-agent";
  agent.textContent = event.agent;

  const title = document.createElement("span");
  title.className = "vh-event-title";
  title.textContent = event.title;

  const time = document.createElement("span");
  time.className = "vh-event-time";
  time.title = event.when;
  time.textContent = event.clock;

  head.append(agent, title, time);
  item.append(head);

  if (options.showContext) {
    const link = document.createElement("a");
    link.className = "vh-event-context";
    link.href = options.link;
    link.textContent = `${event.customer} · Order #${event.order_id}`;
    item.append(link);
  }

  if (event.detail) {
    const detail = document.createElement("div");
    detail.className = "vh-event-detail";
    detail.textContent = event.detail;
    item.append(detail);
  }
  return item;
}

function startLiveUpdates({ streamUrl, eventsUrl, cursor, conversationId, pollMs, status, onEvent }) {
  const filter = conversationId ? `conversation=${conversationId}&` : "";
  const seen = new Set();  // ignore events we already showed (after reconnects)
  let source = null;
  let pollTimer = null;

  function setStatus(state, text) {
    status.className = "vh-live " + state;
    status.querySelector(".label").textContent = text;
  }

  function handle(event) {
    const key = event.kind + ":" + event.id;
    if (seen.has(key)) return;
    seen.add(key);
    onEvent(event);
  }

  async function poll() {
    try {
      const response = await fetch(`${eventsUrl}?${filter}cursor=${encodeURIComponent(cursor)}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      data.events.forEach(handle);
      cursor = data.cursor;
      setStatus("polling", "Live (checking every few seconds)");
    } catch (error) {
      setStatus("offline", "Offline, retrying…");
    }
  }

  function startPolling() {
    if (source) source.close();
    if (pollTimer) return;
    poll();
    pollTimer = setInterval(poll, pollMs);
  }

  function connect() {
    source = new EventSource(`${streamUrl}?${filter}cursor=${encodeURIComponent(cursor)}`);
    source.onopen = () => setStatus("live", "Live");
    source.onmessage = (message) => {
      const event = JSON.parse(message.data);
      if (event.type === "busy") {
        startPolling();  // too many live streams open: check periodically instead
        return;
      }
      if (message.lastEventId) cursor = message.lastEventId;
      handle(event);
    };
    source.onerror = () => {
      // The server closes each stream after a while; the browser reconnects
      // by itself and resumes from the last event it received.
      if (source.readyState === EventSource.CLOSED) startPolling();
      else setStatus("reconnecting", "Reconnecting…");
    };
  }

  if ("EventSource" in window) connect();
  else startPolling();
}
