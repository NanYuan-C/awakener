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
      prompts: "Prompt",
      skills: "Skills",
      timeline: "Timeline",
      snapshot: "Snapshot",
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
      modelName: "Model",
      modelHint: "The model identifier used by LiteLLM. Examples: deepseek-chat, gpt-4o, claude-sonnet-4-20250514",
      apiKey: "API Key",
      apiBase: "API Base URL (optional)",
      apiBaseHint: "Leave empty to use the provider's default endpoint",
      advanced: "Advanced options",
      interval: "Activation Interval (seconds)",
      intervalHint: "Seconds between rounds. Set to 0 for continuous execution (no delay).",
      maxTools: "Max Tool Calls Per Round",
      toolTimeout: "Tool Execution Timeout (seconds)",
      agentParams: "Agent Parameters",
      save: "Save",
      saved: "Settings saved successfully",
      snapshot: "System Snapshot",
      snapshotModel: "Snapshot Auditor Model",
      snapshotModelHint: "The LLM model used to maintain the system asset inventory after each round. Leave empty to use the main agent model.",
      security: "Security",
      changePassword: "Change Password",
      currentPassword: "Current Password",
      newPassword: "New Password",
    },

    // -- Prompt --
    prompts: {
      title: "Agent Prompt",
      subtitle: "This prompt defines the agent's personality, goals, and behavior style.",
      contentLabel: "Prompt Content (Markdown)",
      placeholder: "Write the agent prompt in Markdown...",
      save: "Save",
      saved: "Prompt saved successfully",
    },

    // -- Skills --
    skills: {
      title: "Skills",
      subtitle: "Skills extend the agent's capabilities with structured instructions and scripts.",
      create: "New Skill",
      createTitle: "Create New Skill",
      name: "Skill Name",
      nameHint: "Used as the directory name. Use lowercase letters and hyphens.",
      nameRequired: "Please enter a skill name",
      nameInvalid: "Name must start with a letter/number and contain only lowercase letters, numbers, and hyphens",
      content: "SKILL.md Content",
      save: "Save",
      saved: "Skill saved",
      cancel: "Cancel",
      edit: "Edit",
      delete: "Delete",
      enable: "Enable",
      disable: "Disable",
      enabled: "Enabled",
      disabled: "Disabled",
      confirmDelete: "Delete skill \"{name}\"? This cannot be undone.",
      deleted: "Skill deleted",
      loading: "Loading skills...",
      no_data: "No skills installed. Create one to get started.",
      references: "References",
      scripts: "Scripts",
      upload: "Upload Folder",
      uploadSuccess: "Skill \"{name}\" uploaded ({count} files)",
      uploadError: "Failed to read the selected folder",
      uploadDuplicate: "Skill \"{name}\" already exists. Delete it first or rename the folder.",
      uploadNoSkillMd: "SKILL.md file not found in the selected folder",
      uploadNoFrontmatter: "SKILL.md must start with YAML frontmatter (--- delimiter)",
      uploadNoName: "SKILL.md frontmatter is missing a 'name' field",
      uploadNoDesc: "SKILL.md frontmatter is missing a 'description' field",
    },

    // -- Timeline --
    timeline: {
      title: "Timeline",
      round: "Round",
      tools_used: "tools used",
      duration: "duration",
      no_data: "No timeline data yet.",
      showMore: "Show more",
      showLess: "Collapse",
    },

    // -- Snapshot --
    snapshot: {
      title: "System Snapshot",
      lastUpdated: "Last Updated",
      round: "Round",
      services: "Services",
      serviceName: "Name",
      port: "Port",
      status: "Status",
      health: "Health",
      path: "Path",
      noServices: "No services found",
      projects: "Projects",
      noProjects: "No projects found",
      tools: "Tools",
      noTools: "No tools found",
      documents: "Documents",
      noDocuments: "No documents found",
      environment: "Environment",
      issues: "Issues",
      noIssues: "No open issues",
      empty: "No snapshot data available yet.",
      emptyHint: "The snapshot will be generated after the first agent round.",
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
      prompts: "提示词",
      skills: "技能",
      timeline: "时间线",
      snapshot: "系统快照",
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
      inspirationDesc2: "它是一条单向消息，Agent 会在<strong>下一轮激活</strong>开始时看到它，将其视为一个\u201c灵感火花\u201d。你可以用它来轻轻引导 Agent 的方向，例如：",
      inspirationEx1: "\u201c今天试着整理一下你的笔记\u201d",
      inspirationEx2: "\u201c探索一些有创意的东西\u201d",
      inspirationEx3: "\u201c回顾一下昨天的工作并反思\u201d",
      inspirationDesc3: "Agent 会将这个灵感融入自己的思考中，并自主决定如何行动。",
      understood: "明白了",
    },

    settings: {
      title: "设置",
      model: "模型配置",
      provider: "提供商",
      modelName: "模型",
      modelHint: "LiteLLM 使用的模型标识符。例如：deepseek-chat、gpt-4o、claude-sonnet-4-20250514",
      apiKey: "API 密钥",
      apiBase: "API 基础 URL（可选）",
      apiBaseHint: "留空使用提供商默认端点",
      advanced: "高级选项",
      interval: "激活间隔（秒）",
      intervalHint: "两轮之间的等待秒数。设为 0 表示连续运行。",
      maxTools: "每轮最大工具调用数",
      toolTimeout: "工具执行超时（秒）",
      agentParams: "Agent 参数",
      save: "保存",
      saved: "设置已保存",
      snapshot: "系统快照",
      snapshotModel: "快照审计模型",
      snapshotModelHint: "每轮结束后用于维护系统资产清单的 LLM 模型。留空则使用主 Agent 模型。",
      security: "安全",
      changePassword: "修改密码",
      currentPassword: "当前密码",
      newPassword: "新密码",
    },

    prompts: {
      title: "Agent 提示词",
      subtitle: "提示词定义了 Agent 的性格、目标和行为风格。",
      contentLabel: "提示词内容（Markdown）",
      placeholder: "使用 Markdown 编写 Agent 提示词...",
      save: "保存",
      saved: "提示词已保存",
    },

    skills: {
      title: "技能",
      subtitle: "技能通过结构化指令和脚本扩展 Agent 的能力。",
      create: "新建技能",
      createTitle: "创建新技能",
      name: "技能名称",
      nameHint: "用作目录名，请使用小写字母和连字符。",
      nameRequired: "请输入技能名称",
      nameInvalid: "名称必须以字母或数字开头，只能包含小写字母、数字和连字符",
      content: "SKILL.md 内容",
      save: "保存",
      saved: "技能已保存",
      cancel: "取消",
      edit: "编辑",
      delete: "删除",
      enable: "启用",
      disable: "禁用",
      enabled: "已启用",
      disabled: "已禁用",
      confirmDelete: "确定删除技能 \u201c{name}\u201d？此操作不可撤销。",
      deleted: "技能已删除",
      loading: "加载技能中...",
      no_data: "暂无技能。创建一个来开始吧。",
      references: "参考文档",
      scripts: "脚本",
      upload: "上传目录",
      uploadSuccess: "技能 \u201c{name}\u201d 上传成功（{count} 个文件）",
      uploadError: "无法读取所选文件夹",
      uploadDuplicate: "技能 \u201c{name}\u201d 已存在，请先删除或重命名文件夹。",
      uploadNoSkillMd: "所选文件夹中未找到 SKILL.md 文件",
      uploadNoFrontmatter: "SKILL.md 必须以 YAML 前置元数据开头（--- 分隔符）",
      uploadNoName: "SKILL.md 前置元数据缺少 name 字段",
      uploadNoDesc: "SKILL.md 前置元数据缺少 description 字段",
    },

    timeline: {
      title: "时间线",
      round: "轮次",
      tools_used: "工具调用",
      duration: "耗时",
      no_data: "暂无时间线数据。",
      showMore: "展开全部",
      showLess: "收起",
    },

    snapshot: {
      title: "系统快照",
      lastUpdated: "最后更新",
      round: "轮次",
      services: "服务",
      serviceName: "名称",
      port: "端口",
      status: "状态",
      health: "健康度",
      path: "路径",
      noServices: "未发现服务",
      projects: "项目",
      noProjects: "未发现项目",
      tools: "工具",
      noTools: "未发现工具",
      documents: "文档",
      noDocuments: "未发现文档",
      environment: "环境",
      issues: "问题",
      noIssues: "无待解决问题",
      empty: "暂无快照数据。",
      emptyHint: "快照将在 Agent 运行第一轮后生成。",
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
  // Use innerHTML when the translation contains HTML tags, textContent otherwise
  document.querySelectorAll("[data-i18n]").forEach(function(el) {
    var key = el.getAttribute("data-i18n");
    if (key) {
      var text = t(key);
      if (/<[a-z][\s\S]*>/i.test(text)) {
        el.innerHTML = text;
      } else {
        el.textContent = text;
      }
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
