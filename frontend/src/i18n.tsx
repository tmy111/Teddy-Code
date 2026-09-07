import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const english = {
  languageSwitcher: "Interface language",
  statusReady: "Ready",
  statusAgentStarted: "Agent started",
  statusThinkingPass: "Thinking · pass {attempt}",
  statusPreparingAnswer: "Preparing answer",
  statusPlanningAction: "Planning next action",
  statusRunningTool: "Running {tool}",
  statusThinkingAfterTool: "Thinking after tool",
  statusWaitingApproval: "Waiting for approval",
  statusWaitingAnswer: "Waiting for your answer",
  statusStopped: "Stopped",
  statusComplete: "Complete",
  statusError: "Error",
  statusStarting: "Starting",
  statusStopping: "Stopping",
  statusContinuing: "Continuing",
  errorCreateSession: "Could not create a session.",
  errorConnect: "Could not connect to TeddyCode.",
  errorOpenSession: "Could not open the session.",
  errorStream: "The stream ended unexpectedly.",
  errorStop: "Could not stop the turn.",
  errorTurnFailed: "The turn failed.",
  errorSubmitResponse: "Could not submit the response.",
  approvalTitle: "Allow {action}?",
  thisAction: "this action",
  questionFallback: "Teddy needs more information",
  workspaceFallback: "TeddyCode workspace",
  local: "local",
  configuredModel: "configured model",
  openingWorkspace: "Opening workspace",
  emptyTitle: "What should we work on?",
  emptyDescription: "Teddy can inspect this repository, run tools, and make changes with your approval.",
  suggestionMap: "Map the project structure",
  suggestionRisks: "Find risky code paths",
  suggestionTests: "Run the test suite",
  you: "You",
  teddy: "Teddy",
  stopped: "stopped",
  composerLabel: "Message TeddyCode",
  composerPlaceholder: "Ask Teddy to inspect, explain, or change this workspace…",
  composerPreparing: "Preparing workspace…",
  composerHint: "Enter to send · Shift+Enter for a new line",
  stop: "Stop",
  send: "Send",
  localAgent: "local agent",
  newSession: "New session",
  sessions: "Sessions",
  justNow: "Just now",
  recent: "Recent",
  sessionFallback: "Session {id}",
  eventCountOne: "{count} event",
  eventCount: "{count} events",
  localOnly: "Local only",
  toolReadFile: "Read file",
  toolListFiles: "List files",
  toolSearch: "Search workspace",
  toolRunShell: "Run command",
  toolWriteFile: "Write file",
  toolPatchFile: "Patch file",
  toolInspectImage: "Inspect image",
  toolAskUser: "Ask user",
  toolAgent: "Run sub-agent",
  toolRunning: "running",
  toolSuccess: "success",
  toolError: "error",
  approvalRequired: "Approval required",
  teddyQuestion: "Teddy has a question",
  answered: "Answered: {answer}",
  deny: "Deny",
  allow: "Allow",
  typeAnswer: "Type an answer",
  reply: "Reply",
} as const;

export type MessageKey = keyof typeof english;
export type Language = "en" | "zh";
export type TranslationValues = Record<string, string | number>;

const chinese: Record<MessageKey, string> = {
  languageSwitcher: "界面语言",
  statusReady: "就绪",
  statusAgentStarted: "智能体已启动",
  statusThinkingPass: "思考中 · 第 {attempt} 轮",
  statusPreparingAnswer: "正在整理回答",
  statusPlanningAction: "正在规划下一步",
  statusRunningTool: "正在运行 {tool}",
  statusThinkingAfterTool: "正在分析工具结果",
  statusWaitingApproval: "等待你的批准",
  statusWaitingAnswer: "等待你的回答",
  statusStopped: "已停止",
  statusComplete: "已完成",
  statusError: "出错了",
  statusStarting: "正在启动",
  statusStopping: "正在停止",
  statusContinuing: "正在继续",
  errorCreateSession: "无法创建会话。",
  errorConnect: "无法连接到 TeddyCode。",
  errorOpenSession: "无法打开会话。",
  errorStream: "流式响应意外结束。",
  errorStop: "无法停止本轮任务。",
  errorTurnFailed: "本轮任务执行失败。",
  errorSubmitResponse: "无法提交回复。",
  approvalTitle: "允许执行“{action}”吗？",
  thisAction: "此操作",
  questionFallback: "Teddy 需要更多信息",
  workspaceFallback: "TeddyCode 工作区",
  local: "本地",
  configuredModel: "已配置模型",
  openingWorkspace: "正在打开工作区",
  emptyTitle: "我们接下来做什么？",
  emptyDescription: "Teddy 可以检查这个仓库、运行工具，并在获得你的批准后修改代码。",
  suggestionMap: "梳理项目结构",
  suggestionRisks: "查找高风险代码路径",
  suggestionTests: "运行测试套件",
  you: "你",
  teddy: "Teddy",
  stopped: "已停止",
  composerLabel: "给 TeddyCode 发消息",
  composerPlaceholder: "让 Teddy 检查、解释或修改这个工作区…",
  composerPreparing: "正在准备工作区…",
  composerHint: "Enter 发送 · Shift+Enter 换行",
  stop: "停止",
  send: "发送",
  localAgent: "本地智能体",
  newSession: "新建会话",
  sessions: "会话",
  justNow: "刚刚",
  recent: "最近",
  sessionFallback: "会话 {id}",
  eventCountOne: "{count} 个事件",
  eventCount: "{count} 个事件",
  localOnly: "仅保存在本地",
  toolReadFile: "读取文件",
  toolListFiles: "列出文件",
  toolSearch: "搜索工作区",
  toolRunShell: "运行命令",
  toolWriteFile: "写入文件",
  toolPatchFile: "修改文件",
  toolInspectImage: "检查图片",
  toolAskUser: "询问用户",
  toolAgent: "运行子智能体",
  toolRunning: "运行中",
  toolSuccess: "成功",
  toolError: "失败",
  approvalRequired: "需要批准",
  teddyQuestion: "Teddy 有一个问题",
  answered: "已回答：{answer}",
  deny: "拒绝",
  allow: "允许",
  typeAnswer: "输入回答",
  reply: "回复",
};

const messages = { en: english, zh: chinese };
const storageKey = "teddycode-language";

function initialLanguage(): Language {
  const stored = window.localStorage.getItem(storageKey);
  if (stored === "en" || stored === "zh") return stored;
  return window.navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

function formatMessage(template: string, values: TranslationValues = {}) {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? `{${key}}`));
}

interface I18nContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: MessageKey, values?: TranslationValues) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(initialLanguage);

  useEffect(() => {
    window.localStorage.setItem(storageKey, language);
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  const value = useMemo<I18nContextValue>(() => ({
    language,
    setLanguage,
    t: (key, values) => formatMessage(messages[language][key], values),
  }), [language]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used inside LanguageProvider");
  return context;
}
