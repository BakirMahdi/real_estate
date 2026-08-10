import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { MessageCircle, Send, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { api, isAuthenticated } from "../api/client";
import type { AgentMessage } from "../types/property";
import { getLang, useLang } from "../lib/i18n";

// PropertyPage is mounted at /property/:id but this widget lives at the App
// root (so it survives navigation and keeps one floating bubble everywhere),
// so it has no route params of its own - reading the id back out of the
// pathname is simpler than threading it through a context just for this.
function propertyIdFromPath(pathname: string): number | undefined {
  const match = pathname.match(/^\/property\/(\d+)/);
  return match ? Number(match[1]) : undefined;
}

// Renders the agent's Markdown (bold, lists, and the [title](/property/id)
// links it emits for listings). Internal links (starting with "/") navigate
// in-app via react-router so the chat widget stays open; anything else opens
// in a new tab. `onNavigate` lets the caller collapse the widget on click.
function MessageContent({ text, onNavigate }: { text: string; onNavigate: () => void }) {
  return (
    <div className="space-y-2 [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-4 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-4">
      <ReactMarkdown
        components={{
          a: ({ href, children }) => {
            if (href && href.startsWith("/")) {
              return (
                <Link
                  to={href}
                  onClick={onNavigate}
                  className="font-medium text-brand-600 underline underline-offset-2 hover:text-brand-700 dark:text-brand-200 dark:hover:text-brand-100"
                >
                  {children}
                </Link>
              );
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-brand-600 underline underline-offset-2 hover:text-brand-700 dark:text-brand-200 dark:hover:text-brand-100"
              >
                {children}
              </a>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

// Time only for messages sent today, date + time otherwise, in the viewer's
// local timezone (the stored value is UTC ISO 8601).
function formatMessageTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const locale = getLang() === "fr" ? "fr-FR" : "en-GB";
  const time = date.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
  const isToday = new Date().toDateString() === date.toDateString();
  if (isToday) return time;
  return `${date.toLocaleDateString(locale, { day: "2-digit", month: "2-digit" })} ${time}`;
}

export function AgentChatWidget() {
  const location = useLocation();
  const { t } = useLang();
  const authenticated = isAuthenticated();
  const propertyId = propertyIdFromPath(location.pathname);

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open || !authenticated || historyLoaded) return;
    api
      .getAgentHistory()
      .then((res) => setMessages(res.messages))
      .catch((err) => {
        if (err instanceof Error && err.message === "UNAUTHORIZED") setSessionExpired(true);
        else setError(t("chat.historyError"));
      })
      .finally(() => setHistoryLoaded(true));
  }, [open, authenticated, historyLoaded]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const send = () => {
    const text = input.trim();
    if (!text || sending) return;

    setMessages((prev) => [
      ...prev,
      { role: "user", content: text, created_at: new Date().toISOString() },
    ]);
    setInput("");
    setSending(true);
    setError(null);

    api
      .agentChat(text, propertyId)
      .then((res) =>
        setMessages((prev) => [
          ...prev,
          { role: "model", content: res.reply, created_at: new Date().toISOString() },
        ]),
      )
      .catch((err) => {
        if (err instanceof Error && err.message === "UNAUTHORIZED") setSessionExpired(true);
        else setError(err instanceof Error ? err.message : t("chat.replyError"));
      })
      .finally(() => setSending(false));
  };

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-3">
      {open && (
        <div className="glass flex h-[28rem] w-80 flex-col overflow-hidden sm:w-96">
          <div className="flex items-center justify-between border-b border-gray-200 dark:border-white/10 bg-white/80 dark:bg-navy-800/80 px-4 py-3">
            <div>
              <p className="font-display text-sm font-semibold text-navy-700 dark:text-white">{t("chat.title")}</p>
              {propertyId && (
                <p className="text-xs text-gray-700 dark:text-gray-600">{t("chat.aboutListing")}</p>
              )}
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label={t("chat.close")}
              className="rounded-lg p-1 text-gray-700 dark:text-gray-600 transition hover:bg-lightPrimary dark:hover:bg-navy-700 hover:text-navy-700 dark:hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {!authenticated ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
              <MessageCircle className="h-8 w-8 text-brand-500" />
              <p className="text-sm text-gray-700 dark:text-gray-600">{t("chat.loginPrompt")}</p>
              <Link to="/login" onClick={() => setOpen(false)} className="btn-primary text-sm">
                {t("chat.login")}
              </Link>
            </div>
          ) : (
            <>
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.length === 0 && !sending && (
              <p className="text-sm text-gray-700 dark:text-gray-600">{t("chat.emptyHint")}</p>
            )}
            {messages.map((m, idx) => (
              <div
                key={idx}
                className={`flex max-w-[85%] flex-col gap-1 ${
                  m.role === "user" ? "ml-auto items-end" : "items-start"
                }`}
              >
                <div
                  className={`rounded-xl px-3 py-2 text-sm ${
                    m.role === "user"
                      ? "bg-brand-500 text-white"
                      : "bg-lightPrimary dark:bg-navy-700 text-navy-700 dark:text-white"
                  }`}
                >
                  {m.role === "model" ? (
                    <MessageContent text={m.content} onNavigate={() => setOpen(false)} />
                  ) : (
                    m.content
                  )}
                </div>
                {m.created_at && (
                  <span className="px-1 text-[10px] text-gray-700 dark:text-gray-600">
                    {formatMessageTime(m.created_at)}
                  </span>
                )}
              </div>
            ))}
            {sending && (
              <div className="max-w-[85%] rounded-xl bg-lightPrimary dark:bg-navy-700 px-3 py-2 text-sm text-gray-700 dark:text-gray-600">
                ...
              </div>
            )}
            {sessionExpired && (
              <p className="text-xs text-horizonOrange-600 dark:text-horizonOrange-500">
                {t("chat.sessionExpired")}{" "}
                <Link
                  to="/login"
                  onClick={() => setOpen(false)}
                  className="font-medium underline underline-offset-2"
                >
                  {t("chat.reconnect")}
                </Link>{" "}
                {t("chat.toContinue")}
              </p>
            )}
            {error && <p className="text-xs text-horizonRed-500 dark:text-horizonRed-400">{error}</p>}
          </div>

          <div className="flex items-center gap-2 border-t border-gray-200 dark:border-white/10 p-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") send();
              }}
              placeholder={t("chat.placeholder")}
              disabled={sessionExpired}
              className="input-field flex-1 text-sm disabled:opacity-50"
            />
            <button
              type="button"
              onClick={send}
              disabled={sending || !input.trim() || sessionExpired}
              aria-label={t("chat.send")}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-500 text-white transition hover:bg-brand-600 disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
            </>
          )}
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label={t("chat.open")}
        className="flex h-14 w-14 items-center justify-center rounded-full bg-brand-500 text-white shadow-glow transition hover:bg-brand-600"
      >
        <MessageCircle className="h-6 w-6" />
      </button>
    </div>
  );
}
