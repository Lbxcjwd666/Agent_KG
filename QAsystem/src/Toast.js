import React, { useState, useEffect, useCallback } from 'react';
import './Toast.css';

let toastId = 0;

export function useToast() {
    const [toasts, setToasts] = useState([]);

    const removeToast = useCallback((id) => {
        setToasts(prev => prev.filter(t => t.id !== id));
    }, []);

    const addToast = useCallback((message, type = 'info', duration = 3000) => {
        const id = ++toastId;
        setToasts(prev => [...prev, { id, message, type }]);
        if (duration > 0) {
            setTimeout(() => removeToast(id), duration);
        }
        return id;
    }, [removeToast]);

    const toast = {
        success: (msg) => addToast(msg, 'success'),
        error: (msg) => addToast(msg, 'error', 5000),
        warning: (msg) => addToast(msg, 'warning', 4000),
        info: (msg) => addToast(msg, 'info'),
    };

    return { toasts, removeToast, toast };
}

export default function ToastContainer({ toasts, onRemove }) {
    if (!toasts || toasts.length === 0) return null;

    return (
        <div className="toast-container" aria-live="polite">
            {toasts.map(t => (
                <div key={t.id} className={`toast toast-${t.type}`} role="alert">
                    <span className="toast-icon">
                        {t.type === 'success' && '✔'}
                        {t.type === 'error' && '✘'}
                        {t.type === 'warning' && '⚠'}
                        {t.type === 'info' && 'ℹ'}
                    </span>
                    <span className="toast-message">{t.message}</span>
                    <button className="toast-close" onClick={() => onRemove(t.id)} aria-label="关闭通知">
                        &times;
                    </button>
                </div>
            ))}
        </div>
    );
}
