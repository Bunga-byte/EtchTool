import { Check, X } from "lucide-react";
import { useState } from "react";
import { Notice } from "./components";
import { useDialog } from "./useDialog";

export function AccessDialog({
  onClose,
  onToken,
}: {
  onClose: () => void;
  onToken: (token: string) => void;
}) {
  const [input, setInput] = useState("");
  const ref = useDialog(onClose);
  function submit(token: string) {
    onToken(token);
    setInput("");
    onClose();
  }
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        ref={ref}
        className="access-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="access-title"
      >
        <div className="panel-header">
          <h2 id="access-title">Access settings</h2>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="Close access settings"
          >
            <X size={20} />
          </button>
        </div>
        <form
          className="access-body"
          onSubmit={(e) => {
            e.preventDefault();
            if (input.trim()) submit(input.trim());
          }}
        >
          <Notice>
            Local synthetic access only. Tokens are held in memory and checked
            against server configuration. Corporate SSO is not connected.
          </Notice>
          <label htmlFor="access-token">Authorized local bearer token</label>
          <input
            id="access-token"
            type="password"
            autoComplete="off"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Configured by your local administrator"
          />
          <p className="muted">
            The server assigns roles. A token does not automatically grant
            maintenance or administrative privileges.
          </p>
          <div className="access-actions">
            <button type="button" className="button" onClick={() => submit("")}>
              Use viewer mode
            </button>
            <button
              type="submit"
              className="button primary"
              disabled={!input.trim()}
            >
              <Check size={16} /> Use for this session
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
