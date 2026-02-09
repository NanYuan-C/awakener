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
    // Keys use camelCase to match data-i18n attributes in dashboard.html
    dashboard: {
      agent_status: "Agent Status",
      controls: "Agent Controls",
      start: "Start",
      stop: "Stop",
      restart: "Restart",
      idle: "Idle",
      running: "Running",
      waiting: "Waiting",
      stopping: "Stopping",
      error: "Error",
      round: "Round",
      tools: "Tools",
      currentRound: "CURRENT ROUND",
      status: "STATUS",
      toolCalls: "TOOL CALLS",
      uptime: "UPTIME",
      ws_clients: "Connected Clients",
      liveLog: "Live Log",
      clear: "Clear",
      autoScroll: "Auto-scroll",
      no_logs: "No logs yet. Start the agent to see activity.",
      send_inspiration: "Send Inspiration to Agent",
      inspirationPlaceholder: "Type an inspiration for the agent...",
      send: "Send",
      inspiration_sent: "Inspiration sent to agent",
      inspirationHint: "Not a chat — it's a nudge for the next round",
      inspirationTitle: "What is Inspiration?",
      inspirationDesc1: "Inspiration is <strong>not</strong> a conversation with the agent. The agent cannot reply to you here.",
      inspirationDesc2: "It is a one-way message that the agent will see as a \"spark of inspiration\" at the beginning of its <strong>next activation round</strong>. Use it to gently steer the agent's direction — for example:",
      inspirationEx1: "\"Try organizing your notes today\"",
      inspirationEx2: "\"Explore something creative\"",
      inspirationEx3: "\"Review yesterday's work and reflect\"",
      inspirationDesc3: "The agent will incorporate this inspiration into its own thinking and decide how to act on it autonomously.",
      understood: "Got it",
    },

    // -- Settings --
    // Keys use camelCase to match data-i18n attributes in settings.html
    settings: {
      title: "Settings",
      model: "Model Configuration",
      provider: "Provider",
      modelName: "Model Name",
      modelHint: "The model identifier used by LiteLLM. Examples: deepseek-chat, gpt-4o, claude-sonnet-4-20250514",
      apiBase: "API Base URL (optional)",
      apiBaseHint: "Leave empty to use the provider's default endpoint",
      interval: "Activation Interval (seconds)",
      intervalHint: "Seconds between rounds. Set to 0 for continuous execution (no delay).",
      maxTools: "Max Tool Calls Per Round",
      toolTimeout: "Tool Execution Timeout (seconds)",
      agentParams: "Agent Parameters",
      apiKeys: "API Keys",
      apiKeysHint: "API keys are stored in the .env file on your server. Values are masked for security.",
      addKey: "Add Key",
      save: "Save",
      saved: "Settings saved successfully",
      security: "Security",
      changePassword: "Change Password",
      currentPassword: "Current Password",
      newPassword: "New Password",
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
      refresh: "Refresh",
      loading: "Loading memory...",
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
      controls: "Agent 控制",
      start: "启动",
      stop: "停止",
      restart: "重启",
      idle: "未启动",
      running: "运行中",
      waiting: "等待中",
      stopping: "停止中",
      error: "错误",
      round: "轮次",
      tools: "工具",
      currentRound: "当前轮次",
      status: "状态",
      toolCalls: "工具调用",
      uptime: "运行时间",
      ws_clients: "已连接客户端",
      liveLog: "实时日志",
      clear: "清空",
      autoScroll: "自动滚动",
      no_logs: "暂无日志。启动 Agent 后即可看到活动。",
      send_inspiration: "给 Agent 灵感",
      inspirationPlaceholder: "输入要给 Agent 的灵感...",
      send: "发送",
      inspiration_sent: "灵感已发送给 Agent",
      inspirationHint: "非对话 — 是给下一轮的引导",
      inspirationTitle: "什么是灵感？",
      inspirationDesc1: "灵感<strong>不是</strong>和 Agent 的对话。Agent 不会在这里回复你。",
      inspirationDesc2: "它是一条单向消息，Agent 会在<strong>下一轮激活</strong>开始时看到它，将其视为一个"灵感火花"。你可以用它来轻轻引导 Agent 的方向，例如：",
      inspirationEx1: ""今天试着整理一下你的笔记"",
      inspirationEx2: ""探索一些有创意的东西"",
      inspirationEx3: ""回顾一下昨天的工作并反思"",
      inspirationDesc3: "Agent 会将这个灵感融入自己的思考中，并自主决定如何行动。",
      understood: "明白了",
    },

    settings: {
      title: "设置",
      model: "模型配置",
      provider: "提供商",
      modelName: "模型名称",
      modelHint: "LiteLLM 使用的模型标识符。例如：deepseek-chat、gpt-4o、claude-sonnet-4-20250514",
      apiBase: "API 基础 URL（可选）",
      apiBaseHint: "留空使用提供商默认端点",
      interval: "激活间隔（秒）",
      intervalHint: "两轮之间的等待秒数。设为 0 表示连续运行。",
      maxTools: "每轮最大工具调用数",
      toolTimeout: "工具执行超时（秒）",
      agentParams: "Agent 参数",
      apiKeys: "API 密钥",
      apiKeysHint: "API 密钥存储在服务器的 .env 文件中，显示值已脱敏。",
      addKey: "添加密钥",
      save: "保存",
      saved: "设置已保存",
      security: "安全",
      changePassword: "修改密码",
      currentPassword: "当前密码",
      newPassword: "新密码",
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
      refresh: "刷新",
      loading: "加载记忆中...",
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
