/**
 * AURA Shared App Logic
 * Consolidates auth, toasts, PWA, and haptic feedback across all pages.
 */

const SharedApp = {
    // Detect API Base URL
    get API_BASE() {
        return (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
            ? 'http://localhost:8000/api/v1'
            : window.location.origin + '/api/v1';
    },

    // Initialize the shared features
    init() {
        this.registerServiceWorker();
        this.checkMobileMode();
        window.addEventListener('resize', () => this.checkMobileMode());
        console.log('✨ Aura Shared Logic Initialized');
    },

    // Toast Notification System
    showToast(type, title, message, duration = 4000) {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container fixed top-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none';
            document.body.appendChild(container);

            // Add basic CSS if not present
            if (!document.getElementById('toast-styles')) {
                const style = document.createElement('style');
                style.id = 'toast-styles';
                style.innerHTML = `
                    .toast { 
                        transform: translateX(120%); transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
                        background: rgba(15, 15, 15, 0.9); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1);
                        padding: 12px 16px; border-radius: 12px; min-width: 250px; max-width: 350px; pointer-events: auto;
                    }
                    .toast.show { transform: translateX(0); }
                    .toast-content { display: flex; align-items: center; gap: 12px; }
                    .toast-icon { font-size: 20px; }
                    .toast-text { color: white; }
                    .toast-title { font-weight: bold; font-size: 14px; }
                    .toast-message { font-size: 12px; opacity: 0.7; }
                `;
                document.head.appendChild(style);
            }
        }

        const icons = { info: 'ℹ️', success: '✅', warning: '⚠️', error: '❌' };

        const toast = document.createElement('div');
        toast.className = `toast toast-${type} glass shadow-2xl`;
        toast.innerHTML = `
            <div class="toast-content">
                <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
                <div class="toast-text">
                    <div class="toast-title">${title}</div>
                    <div class="toast-message">${message}</div>
                </div>
            </div>
        `;

        container.appendChild(toast);
        // Trigger reflow for animation
        setTimeout(() => toast.classList.add('show'), 10);

        // Auto-remove
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 400);
        }, duration);
    },

    // Authentication Helpers
    isLoggedIn() {
        return !!localStorage.getItem('aura_user_token');
    },

    logout() {
        localStorage.removeItem('aura_user_token');
        localStorage.removeItem('aura_user_id');
        localStorage.removeItem('aura_username');
        localStorage.removeItem('aura_user_email');
        localStorage.removeItem('aura_user_name');
        window.location.href = '/login';
    },

    async verifyToken() {
        const token = localStorage.getItem('aura_user_token');
        if (!token) return false;

        try {
            const res = await fetch(`${this.API_BASE}/auth/verify`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            return res.ok;
        } catch (e) {
            return false;
        }
    },

    // PWA Support
    registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/static/sw.js')
                    .then(reg => console.log('🚀 SW Registered:', reg.scope))
                    .catch(err => console.error('❌ SW Failed:', err));
            });
        }
    },

    // Mobile Detection
    checkMobileMode() {
        const isMobile = window.innerWidth < 768;
        if (isMobile) {
            document.body.classList.add('mobile-mode');
        } else {
            document.body.classList.remove('mobile-mode');
        }
        return isMobile;
    },

    // Haptic Feedback
    vibrate(pattern = 10) {
        if ('vibrate' in navigator) {
            navigator.vibrate(pattern);
        }
    }
};

// Global export
window.SharedApp = SharedApp;
SharedApp.init();
