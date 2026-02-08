/**
 * Awakener - Shared API Client
 * ===============================
 * Wraps the Fetch API with JWT authentication and error handling.
 * All page-specific JS files use this module to communicate with the backend.
 *
 * Features:
 *   - Automatic JWT token injection from localStorage
 *   - Automatic redirect to /login on 401 responses
 *   - JSON request/response handling
 *   - Centralized error handling
 *
 * Usage:
 *   const data = await api.get('/api/config');
 *   await api.post('/api/agent/start');
 *   await api.put('/api/config', { agent: { interval: 30 } });
 */

const api = {
  /**
   * Get the stored JWT token.
   * @returns {string|null} The JWT token or null if not logged in.
   */
  getToken() {
    return localStorage.getItem("awakener_token");
  },

  /**
   * Store a JWT token after successful login.
   * @param {string} token - The JWT token to store.
   */
  setToken(token) {
    localStorage.setItem("awakener_token", token);
  },

  /**
   * Remove the stored token (logout).
   */
  clearToken() {
    localStorage.removeItem("awakener_token");
  },

  /**
   * Build request headers with JWT authorization.
   * @returns {Object} Headers object with Content-Type and Authorization.
   */
  _headers() {
    const headers = { "Content-Type": "application/json" };
    const token = this.getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  },

  /**
   * Handle API response: parse JSON, handle errors, redirect on 401.
   * @param {Response} response - The fetch Response object.
   * @returns {Object} Parsed JSON response body.
   * @throws {Error} If the response indicates an error.
   */
  async _handleResponse(response) {
    if (response.status === 401) {
      this.clearToken();
      window.location.href = "/login";
      throw new Error("Authentication required");
    }

    const data = await response.json();

    if (!response.ok) {
      const message = data.detail || data.message || `HTTP ${response.status}`;
      throw new Error(message);
    }

    return data;
  },

  /**
   * Send a GET request.
   * @param {string} url - The API endpoint URL.
   * @returns {Promise<Object>} Response data.
   */
  async get(url) {
    const response = await fetch(url, {
      method: "GET",
      headers: this._headers(),
    });
    return this._handleResponse(response);
  },

  /**
   * Send a POST request with JSON body.
   * @param {string} url - The API endpoint URL.
   * @param {Object} [body] - Request body (will be JSON-serialized).
   * @returns {Promise<Object>} Response data.
   */
  async post(url, body = null) {
    const options = {
      method: "POST",
      headers: this._headers(),
    };
    if (body !== null) {
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    return this._handleResponse(response);
  },

  /**
   * Send a PUT request with JSON body.
   * @param {string} url - The API endpoint URL.
   * @param {Object} body - Request body (will be JSON-serialized).
   * @returns {Promise<Object>} Response data.
   */
  async put(url, body) {
    const response = await fetch(url, {
      method: "PUT",
      headers: this._headers(),
      body: JSON.stringify(body),
    });
    return this._handleResponse(response);
  },

  /**
   * Send a DELETE request.
   * @param {string} url - The API endpoint URL.
   * @returns {Promise<Object>} Response data.
   */
  async delete(url) {
    const response = await fetch(url, {
      method: "DELETE",
      headers: this._headers(),
    });
    return this._handleResponse(response);
  },

  /**
   * Check if the user is currently authenticated.
   * Verifies the token exists (does NOT validate it server-side).
   * @returns {boolean} True if a token is stored.
   */
  isAuthenticated() {
    return !!this.getToken();
  },

  /**
   * Check authentication status and redirect to appropriate page.
   * Call this at the top of every protected page.
   * Redirects to /login if not authenticated, to /setup if not configured.
   */
  async checkAuth() {
    try {
      const status = await this.get("/api/auth/status");

      if (!status.is_configured) {
        window.location.href = "/setup";
        return false;
      }

      if (!this.isAuthenticated()) {
        window.location.href = "/login";
        return false;
      }

      return true;
    } catch (e) {
      // If we can't reach the API, redirect to login
      if (!this.isAuthenticated()) {
        window.location.href = "/login";
      }
      return false;
    }
  },

  /**
   * Logout: clear token and redirect to login page.
   */
  logout() {
    this.clearToken();
    window.location.href = "/login";
  },
};

// Make available globally
window.api = api;
