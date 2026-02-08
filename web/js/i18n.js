/**
 * Awakener - Internationalization (i18n) Module
 * ================================================
 * Lightweight translation system using reactive Vue state.
 *
 * Supported languages: English (en), Chinese Simplified (zh)
 * Default language: auto-detected from browser, fallback to English.
 *
 * Usage in Vue templates:
 *   {{ t('nav.dashboard') }}
 *   {{ t('agent.status.running') }}
 *
 * Usage in JavaScript:
 *   import { t, setLocale } from './i18n.js'
 *   t('nav.dashboard')  // "Dashboard" or "仪表盘"
 *   setLocale('zh')     // Switch to Chinese
 */

const messages = {
  en: {
    // -- App Shell --
    app: {
      title: "Awakener",
      subtitle: "Autonomous Agent Console",
      version: "v2.0",
    },

    // -- Navigation --
    nav: {
      dashboard: "Dashboard",
      settings: "Settings",
      prompts: "Prompts",
      timeline: "Timeline",
      memory: "Memory",
      logout: "Logout",
    },

    // -- Auth Pages --
    auth: {
      login_title: "Welcome Back",
      login_subtitle: "Enter your password to continue",
      setup_title: "Welcome to Awakener",
      setup_subtitle: "Let's set up your autonomous agent platform",
      password: "Password",
      password_confirm: "Confirm Password",
      password_placeholder: "Enter admin password",
      password_mismatch: "Passwords do not match",
      login_button: "Login",
      setup_button: "Complete Setup",
      step_password: "Set Password",
      step_api_key: "API Key",
      step_persona: "Persona",
      invalid_password: "Invalid password",
      api_key_label: "API Key",
      api_key_placeholder: "Paste your API key here",
      select_provider: "Select LLM Provider",
      skip: "Skip for now",
      next: "Next",
      back: "Back",
    },

    // -- Dashboard --
    dashboard: {
      agent_status: "Agent Status",
      start: "Start Agent",
      stop: "Stop Agent",
      restart: "Restart",
      idle: "Idle",
      running: "Running",
      waiting: "Waiting",
      stopping: "Stopping",
      error: "Error",
      current_round: "Current Round",
      uptime: "Uptime",
      ws_clients: "Connected Clients",
      live_log: "Live Log",
      no_logs: "No logs yet. Start the agent to see activity.",
      send_inspiration: "Send Inspiration to Agent",
      inspirationPlaceholder: "Type an inspiration for the agent...",
      send: "Send",
      inspiration_sent: "Inspiration sent to agent",
    },

    // -- Settings --
    settings: {
      title: "Settings",
      model: "LLM Model",
      model_help: "Format: provider/model-name (e.g., deepseek/deepseek-chat)",
      interval: "Activation Interval",
      interval_help: "Seconds between rounds. Set to 0 for continuous.",
      interval_unit: "seconds",
      max_tools: "Max Tool Calls",
      max_tools_help: "Maximum tool calls per activation round.",
      shell_timeout: "Shell Timeout",
      shell_timeout_help: "Seconds before a shell command is killed.",
      agent_home: "Agent Home Directory",
      agent_home_help: "Working directory on the server for agent files.",
      api_keys: "API Keys",
      api_keys_help: "Configure keys for your LLM providers.",
      test_key: "Test",
      test_success: "Key is valid!",
      test_failed: "Key test failed",
      save: "Save Settings",
      saved: "Settings saved successfully",
      change_password: "Change Password",
      current_password: "Current Password",
      new_password: "New Password",
    },

    // -- Prompts --
    prompts: {
      title: "Persona Prompts",
      active: "Active",
      edit: "Edit",
      delete: "Delete",
      create: "New Persona",
      name: "Name",
      name_placeholder: "my-persona",
      content: "Content",
      save: "Save",
      cancel: "Cancel",
      confirm_delete: "Are you sure you want to delete this persona?",
      set_active: "Set as Active",
      preview: "Preview",
      editor: "Editor",
      cannot_delete_default: "Cannot delete the default persona",
    },

    // -- Timeline --
    timeline: {
      title: "Timeline",
      round: "Round",
      tools_used: "tools used",
      duration: "duration",
      no_data: "No timeline data yet.",
    },

    // -- Memory --
    memory: {
      title: "Agent Memory",
      notebook: "Notebook",
      no_data: "No memory data yet. The agent hasn't written anything.",
      lines: "lines",
      size: "size",
    },

    // -- Common --
    common: {
      loading: "Loading...",
      error: "An error occurred",
      confirm: "Confirm",
      cancel: "Cancel",
      close: "Close",
      refresh: "Refresh",
    },
  },

  zh: {
    app: {
      title: "Awakener",
      subtitle: "自主代理控制台",
      version: "v2.0",
    },

    nav: {
      dashboard: "仪表盘",
      settings: "设置",
      prompts: "人设",
      timeline: "时间线",
      memory: "记忆",
      logout: "退出",
    },

    auth: {
      login_title: "欢迎回来",
      login_subtitle: "输入密码以继续",
      setup_title: "欢迎使用 Awakener",
      setup_subtitle: "让我们来设置你的自主代理平台",
      password: "密码",
      password_confirm: "确认密码",
      password_placeholder: "输入管理密码",
      password_mismatch: "两次输入的密码不一致",
      login_button: "登录",
      setup_button: "完成设置",
      step_password: "设置密码",
      step_api_key: "API 密钥",
      step_persona: "选择人设",
      invalid_password: "密码错误",
      api_key_label: "API 密钥",
      api_key_placeholder: "粘贴你的 API 密钥",
      select_provider: "选择 LLM 提供商",
      skip: "暂时跳过",
      next: "下一步",
      back: "上一步",
    },

    dashboard: {
      agent_status: "Agent 状态",
      start: "启动 Agent",
      stop: "停止 Agent",
      restart: "重启",
      idle: "未启动",
      running: "运行中",
      waiting: "等待中",
      stopping: "停止中",
      error: "错误",
      current_round: "当前轮次",
      uptime: "运行时间",
      ws_clients: "已连接客户端",
      live_log: "实时日志",
      no_logs: "暂无日志。启动 Agent 后即可看到活动。",
      send_inspiration: "给 Agent 灵感",
      inspirationPlaceholder: "输入要给 Agent 的灵感...",
      send: "发送",
      inspiration_sent: "灵感已发送给 Agent",
    },

    settings: {
      title: "设置",
      model: "LLM 模型",
      model_help: "格式：provider/model-name（如 deepseek/deepseek-chat）",
      interval: "激活间隔",
      interval_help: "两轮之间的等待秒数。设为 0 表示连续运行。",
      interval_unit: "秒",
      max_tools: "最大工具调用数",
      max_tools_help: "每轮激活允许的最大工具调用次数。",
      shell_timeout: "Shell 超时",
      shell_timeout_help: "Shell 命令超时时间（秒）。",
      agent_home: "Agent 主目录",
      agent_home_help: "服务器上 Agent 文件的工作目录。",
      api_keys: "API 密钥",
      api_keys_help: "配置你的 LLM 提供商密钥。",
      test_key: "测试",
      test_success: "密钥有效！",
      test_failed: "密钥测试失败",
      save: "保存设置",
      saved: "设置已保存",
      change_password: "修改密码",
      current_password: "当前密码",
      new_password: "新密码",
    },

    prompts: {
      title: "人设管理",
      active: "使用中",
      edit: "编辑",
      delete: "删除",
      create: "新建人设",
      name: "名称",
      name_placeholder: "my-persona",
      content: "内容",
      save: "保存",
      cancel: "取消",
      confirm_delete: "确定要删除这个人设吗？",
      set_active: "设为当前",
      preview: "预览",
      editor: "编辑器",
      cannot_delete_default: "不能删除默认人设",
    },

    timeline: {
      title: "时间线",
      round: "轮次",
      tools_used: "工具调用",
      duration: "耗时",
      no_data: "暂无时间线数据。",
    },

    memory: {
      title: "Agent 记忆",
      notebook: "笔记本",
      no_data: "暂无记忆数据。Agent 还没有写入任何内容。",
      lines: "行",
      size: "大小",
    },

    common: {
      loading: "加载中...",
      error: "发生错误",
      confirm: "确认",
      cancel: "取消",
      close: "关闭",
      refresh: "刷新",
    },
  },
};

/**
 * Detect the preferred language from browser settings.
 * Falls back to 'en' if no supported language is detected.
 */
function detectLocale() {
  const saved = localStorage.getItem("awakener_locale");
  if (saved && messages[saved]) return saved;

  const browserLang = navigator.language || navigator.userLanguage || "en";
  if (browserLang.startsWith("zh")) return "zh";
  return "en";
}

/** Current active locale */
let currentLocale = detectLocale();

/**
 * Get a translated string by dot-notation key path.
 *
 * @param {string} key - Dot-separated key path (e.g., "nav.dashboard")
 * @returns {string} Translated string, or the key itself if not found.
 */
function t(key) {
  const keys = key.split(".");
  let result = messages[currentLocale];

  for (const k of keys) {
    if (result && typeof result === "object" && k in result) {
      result = result[k];
    } else {
      // Fallback to English if key not found in current locale
      result = messages["en"];
      for (const fk of keys) {
        if (result && typeof result === "object" && fk in result) {
          result = result[fk];
        } else {
          return key; // Key not found in any locale
        }
      }
      return result;
    }
  }
  return result;
}

/**
 * Switch the active locale and persist the choice.
 *
 * @param {string} locale - Locale code ('en' or 'zh')
 */
function setLocale(locale) {
  if (messages[locale]) {
    currentLocale = locale;
    localStorage.setItem("awakener_locale", locale);
  }
}

/**
 * Get the current active locale code.
 *
 * @returns {string} Current locale ('en' or 'zh')
 */
function getLocale() {
  return currentLocale;
}

/**
 * Get list of available locales.
 *
 * @returns {Array<{code: string, name: string}>}
 */
function getAvailableLocales() {
  return [
    { code: "en", name: "English" },
    { code: "zh", name: "中文" },
  ];
}

/**
 * Apply translations to the current DOM.
 * Scans for elements with [data-i18n] and [data-i18n-placeholder] attributes
 * and replaces their text content or placeholder with the translated value.
 *
 * Usage:
 *   <span data-i18n="nav.dashboard">Dashboard</span>
 *   <input data-i18n-placeholder="dashboard.inspirationPlaceholder" placeholder="...">
 */
function apply() {
  // Translate text content
  document.querySelectorAll("[data-i18n]").forEach(function(el) {
    var key = el.getAttribute("data-i18n");
    if (key) {
      el.textContent = t(key);
    }
  });

  // Translate placeholder attributes
  document.querySelectorAll("[data-i18n-placeholder]").forEach(function(el) {
    var key = el.getAttribute("data-i18n-placeholder");
    if (key) {
      el.placeholder = t(key);
    }
  });

  // Translate title attributes
  document.querySelectorAll("[data-i18n-title]").forEach(function(el) {
    var key = el.getAttribute("data-i18n-title");
    if (key) {
      el.title = t(key);
    }
  });
}

// Export for global use
window.i18n = { t, setLocale, getLocale, getAvailableLocales, apply };
