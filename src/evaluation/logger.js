/**
 * The interaction logger of the evaluation deployment.
 *
 * Loaded by App.svelte once a participant has identified themselves, and only
 * in evaluation mode. It records what the reader does as a stream of small
 * events and posts them in batches to `/api/evaluation/log`, where the
 * Netlify Function stores each batch as one object (netlify/lib/evaluationApi.mjs).
 *
 * Three kinds of event reach the stream:
 *
 * - what the application says through `logEvent()` — a slide change and how
 *   it was made, a network opened, an image enlarged, a search typed;
 * - what the router says: every route, so the analysis can reconstruct which
 *   view was open when, without any component reporting it;
 * - what the document says: every click with a description of the control
 *   under it, the navigation keys, scroll depth on a meta story, visibility,
 *   resizes, and script errors.
 *
 * Every event carries the moment it happened and the route it happened on.
 * Batches are numbered per session and kept until the server has confirmed
 * them; a batch that cannot be sent is held in local storage and retried on
 * the next flush or the next visit, so a dropped connection loses nothing.
 */

import { derived, get } from "svelte/store";
import { location, querystring } from "../stores/router.js";
import { currentLanguage } from "../stores/language.js";
import { highContrast } from "../stores/contrast.js";
import { assetUrl } from "../utils/assetUrl.js";
import { localStore, sessionStore } from "../utils/safeStorage.js";
import { describeTarget } from "../utils/evaluation/describeTarget.js";
import { setEventSink } from "./log.js";

const ENDPOINT = "/api/evaluation/log";
const SESSION_KEY = "evaluationSession";
const SESSION_PARTICIPANT_KEY = "evaluationSessionParticipant";
const SEQ_KEY = "evaluationSeq";
const PENDING_KEY = "evaluationPending";

const FLUSH_INTERVAL_MS = 5000;
const FLUSH_AT_EVENTS = 40;
const MAX_PENDING_BATCHES = 400;
const SCROLL_SAMPLE_MS = 1000;
const SCROLL_SAMPLE_STEP = 0.02;
const RESIZE_DEBOUNCE_MS = 500;

const NAVIGATION_KEYS = new Set([
  "ArrowUp",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "Escape",
  "Enter",
  " ",
  "Tab",
  "Home",
  "End",
  "PageUp",
  "PageDown",
]);

function randomId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function readPending() {
  try {
    const stored = JSON.parse(localStore.get(PENDING_KEY) || "[]");
    return Array.isArray(stored) ? stored : [];
  } catch {
    return [];
  }
}

function isEditable(target) {
  if (!target || target.nodeType !== 1) return false;
  const tag = target.tagName.toLowerCase();
  return (
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    target.isContentEditable === true
  );
}

function environment() {
  const media = (query) =>
    typeof window.matchMedia === "function"
      ? window.matchMedia(query).matches
      : null;
  return {
    ua: navigator.userAgent,
    w: window.innerWidth,
    h: window.innerHeight,
    dpr: window.devicePixelRatio ?? 1,
    touch: (navigator.maxTouchPoints ?? 0) > 0,
    coarse: media("(pointer: coarse)"),
    reducedMotion: media("(prefers-reduced-motion: reduce)"),
    lang: get(currentLanguage),
    browserLang: navigator.language,
    contrast: get(highContrast),
    tz: new Date().getTimezoneOffset(),
    hash: window.location.hash,
    referrer: document.referrer || null,
  };
}

/**
 * Start recording for a participant. Returns a function that stops it and
 * closes the session.
 * @param {string} participant
 * @returns {() => void}
 */
export function startLogging(participant) {
  // A session is one tab: session storage survives a reload and ends with the
  // tab, and a participant change on the same tab starts a fresh one.
  let session = sessionStore.get(SESSION_KEY);
  const resumed =
    !!session && sessionStore.get(SESSION_PARTICIPANT_KEY) === participant;
  if (!resumed) {
    session = randomId();
    sessionStore.set(SESSION_KEY, session);
    sessionStore.set(SESSION_PARTICIPANT_KEY, participant);
    sessionStore.set(SEQ_KEY, "0");
  }

  const url = assetUrl(ENDPOINT);
  let buffer = [];
  let pending = readPending();
  let sending = false;
  let stopped = false;
  let currentPath = "";
  let lastRoute = null;
  let lastPointerType = null;
  let flushTimer = null;
  let resizeTimer = null;
  let lastScrollSample = { at: 0, progress: -1, section: null };

  function nextSeq() {
    const seq = parseInt(sessionStore.get(SEQ_KEY) || "0", 10) || 0;
    sessionStore.set(SEQ_KEY, String(seq + 1));
    return seq;
  }

  function persistPending() {
    if (pending.length > MAX_PENDING_BATCHES) {
      pending = pending.slice(pending.length - MAX_PENDING_BATCHES);
    }
    if (pending.length === 0) localStore.remove(PENDING_KEY);
    else localStore.set(PENDING_KEY, JSON.stringify(pending));
  }

  function record(type, data = {}) {
    if (stopped) return;
    // The event's own fields last, so a detail named like one of them — a
    // slide's `type` — cannot overwrite it.
    buffer.push({ ...data, t: Date.now(), type, route: currentPath });
    if (buffer.length >= FLUSH_AT_EVENTS) flush();
  }

  function packBuffer() {
    if (buffer.length === 0) return;
    pending.push({
      participant,
      session,
      seq: nextSeq(),
      sentAt: new Date().toISOString(),
      events: buffer,
    });
    buffer = [];
    persistPending();
  }

  async function flush() {
    packBuffer();
    if (sending || pending.length === 0) return;
    sending = true;
    try {
      while (pending.length > 0) {
        const batch = pending[0];
        let response;
        try {
          // eslint-disable-next-line no-await-in-loop -- batches go in order
          response = await fetch(url, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(batch),
            keepalive: true,
          });
        } catch {
          break;
        }
        // A batch the server refuses as malformed or too large would be
        // refused forever; only a transport or server failure is worth a retry.
        if (response.ok || response.status === 400 || response.status === 413) {
          pending.shift();
          persistPending();
        } else {
          break;
        }
      }
    } finally {
      sending = false;
    }
  }

  // On the way out of the page a fetch may not be given time to leave; a
  // beacon is queued by the browser and sent after the page is gone.
  function flushOnExit() {
    packBuffer();
    if (typeof navigator.sendBeacon !== "function") return;
    const remaining = [];
    for (const batch of pending) {
      const body = new Blob([JSON.stringify(batch)], {
        type: "application/json",
      });
      if (!navigator.sendBeacon(url, body)) remaining.push(batch);
    }
    pending = remaining;
    persistPending();
  }

  // --- the router --------------------------------------------------------

  const routeStore = derived(
    [location, querystring],
    ([$location, $querystring]) => ({
      path: ($location || "/").split("?")[0],
      query: $querystring || "",
    })
  );
  const unsubscribeRoute = routeStore.subscribe(({ path, query }) => {
    currentPath = path;
    const key = `${path}?${query}`;
    if (key === lastRoute) return;
    lastRoute = key;
    record("route", { path, query });
  });

  // --- the stores --------------------------------------------------------

  let knownLanguage = get(currentLanguage);
  const unsubscribeLanguage = currentLanguage.subscribe((lang) => {
    if (lang === knownLanguage) return;
    record("app.language", { from: knownLanguage, to: lang });
    knownLanguage = lang;
  });
  let knownContrast = get(highContrast);
  const unsubscribeContrast = highContrast.subscribe((enabled) => {
    if (enabled === knownContrast) return;
    knownContrast = enabled;
    record("app.contrast", { enabled });
  });

  // --- the document ------------------------------------------------------

  function onPointerDown(event) {
    lastPointerType = event.pointerType || null;
  }

  function onClick(event) {
    const target = describeTarget(event.target);
    record("click", {
      ...(target ?? {}),
      x: Math.round(event.clientX),
      y: Math.round(event.clientY),
      pointer: lastPointerType,
    });
  }

  function onKeyDown(event) {
    if (!NAVIGATION_KEYS.has(event.key) || isEditable(event.target)) return;
    record("key", { key: event.key === " " ? "Space" : event.key });
  }

  function onVisibility() {
    record("session.visibility", { hidden: document.hidden });
    if (document.hidden) flushOnExit();
  }

  function onPageHide() {
    record("session.end", {});
    flushOnExit();
  }

  function onResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      record("session.resize", { w: window.innerWidth, h: window.innerHeight });
    }, RESIZE_DEBOUNCE_MS);
  }

  function onError(event) {
    record("error", {
      message: String(
        event.message ?? event.reason?.message ?? event.reason ?? ""
      ),
      source: event.filename ? `${event.filename}:${event.lineno}` : null,
    });
  }

  // A meta story is one long document, so where the reader is in it is a
  // scroll depth and the section under the viewport's middle. The sections
  // announce themselves with `data-section`; nothing else is read.
  function currentSection() {
    const middle = window.innerHeight / 2;
    let found = null;
    for (const element of document.querySelectorAll("[data-section]")) {
      const rect = element.getBoundingClientRect();
      if (rect.top <= middle && rect.bottom > middle) {
        found = element.getAttribute("data-section");
      }
    }
    return found;
  }

  function onScroll() {
    if (!/\/meta\//.test(currentPath)) return;
    const now = Date.now();
    if (now - lastScrollSample.at < SCROLL_SAMPLE_MS) return;
    const travel = document.documentElement.scrollHeight - window.innerHeight;
    const progress =
      travel > 0 ? Math.min(Math.max(window.scrollY / travel, 0), 1) : 0;
    const section = currentSection();
    const moved =
      Math.abs(progress - lastScrollSample.progress) >= SCROLL_SAMPLE_STEP;
    const changed = section !== lastScrollSample.section;
    if (!moved && !changed) return;
    lastScrollSample = { at: now, progress, section };
    record("meta.scroll", {
      progress: Math.round(progress * 1000) / 1000,
      section,
    });
  }

  document.addEventListener("pointerdown", onPointerDown, true);
  document.addEventListener("click", onClick, true);
  document.addEventListener("keydown", onKeyDown, true);
  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("pagehide", onPageHide);
  window.addEventListener("resize", onResize);
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onError);

  setEventSink(record);
  record("session.start", { participant, session, resumed, ...environment() });
  flushTimer = setInterval(flush, FLUSH_INTERVAL_MS);
  flush();

  return function stopLogging() {
    if (stopped) return;
    record("session.end", {});
    stopped = true;
    setEventSink(null);
    clearInterval(flushTimer);
    clearTimeout(resizeTimer);
    unsubscribeRoute();
    unsubscribeLanguage();
    unsubscribeContrast();
    document.removeEventListener("pointerdown", onPointerDown, true);
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("keydown", onKeyDown, true);
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("pagehide", onPageHide);
    window.removeEventListener("resize", onResize);
    window.removeEventListener("scroll", onScroll);
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onError);
    sessionStore.remove(SESSION_KEY);
    sessionStore.remove(SESSION_PARTICIPANT_KEY);
    flush();
  };
}
