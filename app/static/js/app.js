// Judol Hunter - Alpine.js Components

document.addEventListener('alpine:init', () => {
    // Main Application Component
    Alpine.data('app', () => ({
        isAuthenticated: false,
        user: null,
        currentView: 'dashboard',

        init() {
            this.checkAuth();
        },

        async checkAuth() {
            const token = localStorage.getItem('access_token');
            if (token) {
                try {
                    const response = await fetch('/api/auth/me', {
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    });
                    if (response.ok) {
                        this.user = await response.json();
                        this.isAuthenticated = true;
                    } else {
                        localStorage.removeItem('access_token');
                    }
                } catch (error) {
                    console.error('Auth check failed:', error);
                }
            }
        },

        async logout() {
            localStorage.removeItem('access_token');
            this.isAuthenticated = false;
            this.user = null;
            window.location.href = '/';
        }
    }));

    // Scan Form Component
    Alpine.data('scanForm', () => ({
        urls: '',
        isSubmitting: false,
        scans: [],
        activeScan: null,
        showResults: false,

        async submitScan() {
            if (!this.urls.trim()) {
                this.showError('Please enter at least one URL');
                return;
            }

            this.isSubmitting = true;
            const urlList = this.urls.split('\n')
                .map(u => u.trim())
                .filter(u => u);

            try {
                const token = localStorage.getItem('access_token');
                const headers = { 'Content-Type': 'application/json' };
                if (token) headers['Authorization'] = `Bearer ${token}`;

                const response = await fetch('/api/scans', {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({ urls: urlList })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Scan creation failed');
                }

                this.scans = await response.json();
                this.showResults = true;
                this.activeScan = this.scans[0];

                // Start streaming first scan
                if (this.activeScan) {
                    this.streamScan(this.activeScan.id);
                }
            } catch (error) {
                this.showError(error.message);
            } finally {
                this.isSubmitting = false;
            }
        },

        async streamScan(scanId) {
            const token = localStorage.getItem('access_token');
            const headers = {};
            if (token) headers['Authorization'] = `Bearer ${token}`;

            const eventSource = new EventSource(
                `/api/scans/${scanId}/stream`,
                { headers }
            );

            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleStreamEvent(data);
            };

            eventSource.onerror = () => {
                eventSource.close();
            };
        },

        handleStreamEvent(event) {
            const scan = this.scans.find(s => s.id === event.scan_id);
            if (scan) {
                scan.status = event.data?.status || scan.status;
                scan.risk_level = event.data?.risk_level || scan.risk_level;

                if (event.type === 'complete') {
                    scan.findings = event.data?.findings;
                }

                // Force reactivity
                this.scans = [...this.scans];
            }
        },

        showError(message) {
            // Simple alert for now, could be enhanced
            alert(message);
        }
    }));

    // Scan History Component
    Alpine.data('scanHistory', () => ({
        scans: [],
        loading: true,

        async init() {
            await this.loadScans();
        },

        async loadScans() {
            this.loading = true;
            try {
                const token = localStorage.getItem('access_token');
                if (!token) {
                    this.scans = [];
                    return;
                }

                const response = await fetch('/api/scans', {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });

                if (response.ok) {
                    this.scans = await response.json();
                }
            } catch (error) {
                console.error('Failed to load scans:', error);
            } finally {
                this.loading = false;
            }
        },

        getStatusBadgeClass(status) {
            const classes = {
                'pending': 'badge',
                'running': 'badge',
                'completed': 'badge badge-clean',
                'failed': 'badge badge-error'
            };
            return classes[status] || 'badge';
        },

        getRiskBadgeClass(risk) {
            return `badge badge-risk-${risk}`;
        }
    }));

    // Scan Detail Component
    Alpine.data('scanDetail', () => ({
        scanId: null,
        scan: null,
        loading: true,

        init() {
            this.scanId = this.$root.dataset.scanId;
            if (this.scanId) {
                this.loadScan();
            }
        },

        async loadScan() {
            this.loading = true;
            try {
                const token = localStorage.getItem('access_token');
                const headers = { 'Content-Type': 'application/json' };
                if (token) headers['Authorization'] = `Bearer ${token}`;

                const response = await fetch(`/api/scans/${this.scanId}`, {
                    headers
                });

                if (response.ok) {
                    this.scan = await response.json();
                }
            } catch (error) {
                console.error('Failed to load scan:', error);
            } finally {
                this.loading = false;
            }
        },

        formatTimestamp(ts) {
            if (!ts) return '-';
            return new Date(ts).toLocaleString();
        },

        formatDuration(seconds) {
            if (!seconds) return '-';
            if (seconds < 60) return `${seconds.toFixed(1)}s`;
            return `${(seconds / 60).toFixed(1)}m`;
        }
    }));

    // Auth Form Component
    Alpine.data('authForm', () => ({
        isLogin: true,
        email: '',
        password: '',
        fullName: '',
        confirmPassword: '',
        isSubmitting: false,
        error: '',

        async submit() {
            this.error = '';
            this.isSubmitting = true;

            const endpoint = this.isLogin ? '/api/auth/login' : '/api/auth/register';
            const body = this.isLogin ? {
                email: this.email,
                password: this.password
            } : {
                email: this.email,
                password: this.password,
                full_name: this.fullName,
                confirm_password: this.confirmPassword
            };

            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Authentication failed');
                }

                if (this.isLogin) {
                    localStorage.setItem('access_token', data.access_token);
                    window.location.href = '/dashboard';
                } else {
                    // Switch to login after successful registration
                    this.isLogin = true;
                    this.error = '';
                    this.email = this.email;
                    this.password = '';
                    alert('Registration successful! Please log in.');
                }
            } catch (error) {
                this.error = error.message;
            } finally {
                this.isSubmitting = false;
            }
        },

        toggleMode() {
            this.isLogin = !this.isLogin;
            this.error = '';
        }
    }));

    // Terminal Output Component
    Alpine.data('terminalOutput', () => ({
        lines: [],
        maxLines: 100,

        addLine(text, type = 'info') {
            this.lines.push({
                text,
                type,
                timestamp: new Date().toISOString()
            });

            // Keep only last N lines
            if (this.lines.length > this.maxLines) {
                this.lines.shift();
            }

            // Auto-scroll to bottom
            this.$nextTick(() => {
                const container = this.$refs.output;
                if (container) {
                    container.scrollTop = container.scrollHeight;
                }
            });
        },

        clear() {
            this.lines = [];
        }
    }));

    // Plan Cards Component
    Alpine.data('planCards', () => ({
        plans: [],
        currentPlan: 'free',

        async init() {
            await this.loadPlans();
            await this.checkCurrentPlan();
        },

        async loadPlans() {
            try {
                const response = await fetch('/api/auth/plans');
                if (response.ok) {
                    this.plans = await response.json();
                }
            } catch (error) {
                console.error('Failed to load plans:', error);
            }
        },

        async checkCurrentPlan() {
            const token = localStorage.getItem('access_token');
            if (token) {
                try {
                    const response = await fetch('/api/auth/me', {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    if (response.ok) {
                        const user = await response.json();
                        this.currentPlan = user.plan_type;
                    }
                } catch (error) {
                    console.error('Failed to get current plan:', error);
                }
            }
        },

        selectPlan(planSlug) {
            // This would integrate with payment provider
            alert(`Plan selection: ${planSlug}\n\nPayment integration would be handled here.`);
        }
    }));

    // URL Input with Validation
    Alpine.data('urlInput', () => ({
        urls: '',
        urlCount: 0,
        isValid: true,

        validate() {
            const lines = this.urls.split('\n').filter(u => u.trim());
            this.urlCount = lines.length;

            // Basic URL validation
            const urlPattern = /^https?:\/\/.+/i;
            this.isValid = lines.every(url => urlPattern.test(url.trim()));
        }
    }));

    // Real-time Clock
    Alpine.data('clock', () => ({
        time: '',
        date: '',

        init() {
            this.updateTime();
            setInterval(() => this.updateTime(), 1000);
        },

        updateTime() {
            const now = new Date();
            this.time = now.toLocaleTimeString();
            this.date = now.toLocaleDateString();
        }
    }));
});

// Utility functions
function getAuthToken() {
    return localStorage.getItem('access_token');
}

function getAuthHeaders() {
    const token = getAuthToken();
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return headers;
}

async function apiRequest(url, options = {}) {
    const headers = getAuthHeaders();
    const response = await fetch(url, {
        ...options,
        headers: { ...headers, ...options.headers }
    });

    if (response.status === 401) {
        localStorage.removeItem('access_token');
        window.location.href = '/login';
        throw new Error('Unauthorized');
    }

    return response;
}

// Format bytes
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// Truncate text
function truncate(text, length = 100) {
    if (!text) return '';
    return text.length > length ? text.substring(0, length) + '...' : text;
}
