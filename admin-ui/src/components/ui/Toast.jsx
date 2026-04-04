import { useState, useEffect, createContext, useContext, useCallback, useRef } from 'react';
import './Toast.css';

const ToastContext = createContext(null);
const DEDUPE_WINDOW_MS = 1800;
const MAX_VISIBLE_TOASTS = 5;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const recentToastsRef = useRef(new Map());

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((message, type = 'info', duration = 5000) => {
    const safeMessage = String(message || "").trim();
    if (!safeMessage) return null;

    const dedupeKey = `${type}:${safeMessage}`;
    const now = Date.now();
    const lastShownAt = recentToastsRef.current.get(dedupeKey);
    if (lastShownAt && now - lastShownAt < DEDUPE_WINDOW_MS) {
      return null;
    }
    recentToastsRef.current.set(dedupeKey, now);

    const id = now + Math.random();
    setToasts((prev) => [...prev, { id, message: safeMessage, type }].slice(-MAX_VISIBLE_TOASTS));

    if (duration > 0) {
      setTimeout(() => {
        removeToast(id);
      }, duration);
    }

    return id;
  }, [removeToast]);

  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      for (const [key, timestamp] of recentToastsRef.current.entries()) {
        if (now - timestamp > DEDUPE_WINDOW_MS * 3) {
          recentToastsRef.current.delete(key);
        }
      }
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const toast = {
    success: (msg, duration) => addToast(msg, 'success', duration),
    error: (msg, duration) => addToast(msg, 'error', duration),
    warning: (msg, duration) => addToast(msg, 'warning', duration),
    info: (msg, duration) => addToast(msg, 'info', duration),
  };

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="toast-container">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`toast toast-${t.type}`}
            role="alert"
          >
            <span className="toast-icon">
              {t.type === 'success' && '✓'}
              {t.type === 'error' && '✕'}
              {t.type === 'warning' && '⚠'}
              {t.type === 'info' && 'ℹ'}
            </span>
            <span className="toast-message">{t.message}</span>
            <button
              className="toast-close"
              onClick={() => removeToast(t.id)}
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
