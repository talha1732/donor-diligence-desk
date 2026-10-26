import { useEffect, useLayoutEffect, useRef, useState } from "react";

/** "Connecticut Foodshare Inc" reads better as "Connecticut Foodshare" in a letter. */
function letterName(name: string): string {
  return name.replace(/,?\s+(inc\.?|incorporated)$/i, "").trim() || name;
}

export function emailTemplate(name: string, questions: string[]) {
  const org = letterName(name);
  const subject = `Questions before a gift to ${org}`;
  const list = questions.map((q, i) => `${i + 1}. ${q.trim()}`).join("\n");
  const body = [
    "Hello,",
    "",
    `I am considering a gift to ${org}. I have reviewed the public financial data in your IRS Form 990 filings, and before I decide I would be grateful for your answers to a few questions:`,
    "",
    list,
    "",
    "If any of this is already covered in a report or on your website, a link would be just as helpful.",
    "",
    "Thank you for your time and for the work you do.",
    "",
    "Kind regards,",
    "[Your name]",
  ].join("\n");
  return { subject, body };
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  }
}

/** Deterministic email draft (no AI) with the charity's questions, ready to copy or open in a mail app. */
export function EmailDraft({ name, questions }: { name: string; questions: string[] }) {
  const [openPanel, setOpenPanel] = useState(false);
  const initial = emailTemplate(name, questions);
  const [subject, setSubject] = useState(initial.subject);
  const [body, setBody] = useState(initial.body);
  const [copied, setCopied] = useState<"idle" | "done" | "failed">("idle");
  const subjectRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (copied === "idle") return;
    const t = window.setTimeout(() => setCopied("idle"), 2400);
    return () => window.clearTimeout(t);
  }, [copied]);

  const bodyRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (openPanel) subjectRef.current?.focus();
  }, [openPanel]);

  // Grow the message box to fit the text so the whole email is visible without scrolling.
  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight + 2}px`;
  }, [body, openPanel]);

  if (!questions.length) return null;

  const mailto = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body.replace(/\r?\n/g, "\r\n"))}`;
  const edited = subject !== initial.subject || body !== initial.body;

  if (!openPanel) {
    return (
      <div className="email-cta no-print">
        <button className="btn btn-secondary btn-small" type="button" onClick={() => setOpenPanel(true)}>
          <MailIcon />
          Draft an email to the charity
        </button>
      </div>
    );
  }

  return (
    <div className="email-panel no-print" role="region" aria-label="Email draft">
      <div className="email-head">
        <div>
          <div className="email-title">Email draft</div>
          <div className="muted small">A fixed template with the questions above. Edit anything before you send it.</div>
        </div>
        <button className="btn-icon" type="button" onClick={() => setOpenPanel(false)} aria-label="Close the email draft">
          ×
        </button>
      </div>
      <label className="email-field">
        <span className="field-label">Subject</span>
        <input ref={subjectRef} type="text" value={subject} onChange={(e) => setSubject(e.target.value)} />
      </label>
      <label className="email-field">
        <span className="field-label">Message</span>
        <textarea ref={bodyRef} value={body} onChange={(e) => setBody(e.target.value)} rows={12} spellCheck />
      </label>
      <div className="email-actions">
        <button
          className="btn btn-primary btn-small"
          type="button"
          onClick={async () => setCopied((await copyText(`Subject: ${subject}\n\n${body}`)) ? "done" : "failed")}
        >
          {copied === "done" ? "Copied" : "Copy email"}
        </button>
        <a className="btn btn-secondary btn-small" href={mailto}>
          Open in my email app
        </a>
        {edited && (
          <button
            className="btn-link small"
            type="button"
            onClick={() => {
              setSubject(initial.subject);
              setBody(initial.body);
            }}
          >
            Undo my edits
          </button>
        )}
        <span className="email-status small" role="status" aria-live="polite">
          {copied === "done" ? "Subject and message copied to your clipboard." : copied === "failed" ? "Copy did not work in this browser. Select the text and copy it." : ""}
        </span>
      </div>
      <p className="muted small email-note">Nothing is sent from this page. Add the charity's address in your email app.</p>
    </div>
  );
}

function MailIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
      <rect x="1.5" y="3" width="13" height="10" rx="1.6" stroke="currentColor" strokeWidth="1.4" />
      <path d="M2 4l6 4.6L14 4" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}
