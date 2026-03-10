import React, {
  useState,
  useRef,
  useCallback,
  useEffect,
} from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  StatusBar,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { ChatMessageBubble } from "@/components/ChatMessage";
import { ChatInput } from "@/components/ChatInput";
import { TypingIndicator } from "@/components/TypingIndicator";
import { AgentMessage } from "@/components/AgentMessage";
import { AgentStatusBar } from "@/components/AgentStatusBar";
import { ChatHistoryModal } from "@/components/ChatHistoryModal";
import { AgentPlanView } from "@/components/AgentPlanView";
import { AgentWorking } from "@/components/AgentThinking";
import { AgentToolCard } from "@/components/AgentToolCard";
import { ComputerView } from "@/components/ComputerView";
import { streamChat, streamAgent } from "@/lib/chat";
import {
  saveChatSession,
  buildSessionTitle,
  buildSessionPreview,
  type ChatSession,
} from "@/lib/storage";
import type {
  ChatMessage,
  ChatAttachment,
  AgentEvent,
  AgentPlan,
  ChatListItem,
} from "@/lib/chat";

const SYSTEM_PROMPT = {
  role: "system",
  content:
    "You are Dzeck AI, a helpful and professional AI assistant. Respond clearly and concisely. Use markdown formatting when appropriate - use code blocks with language tags for code, bold for emphasis, and bullet points for lists.",
};

function getApiUrl(): string {
  const host = process.env.EXPO_PUBLIC_DOMAIN;
  if (host) return `https://${host}/`;
  const port = process.env.EXPO_PUBLIC_API_PORT || "5000";
  return `http://localhost:${port}/`;
}


export default function ChatScreen() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [agentEvents, setAgentEvents] = useState<ChatListItem[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isAgentMode, setIsAgentMode] = useState(false);
  const [currentPlan, setCurrentPlan] = useState<AgentPlan | null>(null);
  const [agentStatus, setAgentStatus] = useState<{
    label: string;
    toolName?: string;
    functionName?: string;
  } | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [browserState, setBrowserState] = useState<{
    url: string;
    title: string;
    content: string;
    screenshot?: string;
    isLoading: boolean;
  } | null>(null);
  const flatListRef = useRef<FlatList>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string>(Date.now().toString());
  const streamingMsgIdRef = useRef<string | null>(null);
  const currentStepIdRef = useRef<string | null>(null);
  const planViewAddedRef = useRef<boolean>(false);
  const computerViewAddedRef = useRef<boolean>(false);

  const scrollToBottom = useCallback((animated = true) => {
    setTimeout(
      () => flatListRef.current?.scrollToEnd({ animated }),
      100,
    );
  }, []);

  const autoSaveSession = useCallback(
    async (
      msgs: ChatMessage[],
      events: ChatListItem[],
      mode: "chat" | "agent",
    ) => {
      const hasContent =
        mode === "chat"
          ? msgs.some((m) => m.role === "assistant" && m.content)
          : events.some(
              (e) => e.kind === "agent" && e.data.type === "message",
            );
      if (!hasContent) return;

      const session: ChatSession = {
        id: sessionIdRef.current,
        title: buildSessionTitle(msgs, events),
        mode,
        preview: buildSessionPreview(msgs, events),
        timestamp: Date.now(),
        messages: msgs,
        agentEvents: mode === "agent" ? events : undefined,
      };
      await saveChatSession(session);
    },
    [],
  );

  // Auto-save when generation ends
  const prevGeneratingRef = useRef(false);
  useEffect(() => {
    if (prevGeneratingRef.current && !isGenerating) {
      if (isAgentMode) {
        autoSaveSession([], agentEvents, "agent");
      } else {
        autoSaveSession(messages, [], "chat");
      }
    }
    prevGeneratingRef.current = isGenerating;
  }, [isGenerating, messages, agentEvents, isAgentMode, autoSaveSession]);

  // --- Regular Chat Mode ---
  const handleChatSend = useCallback(
    async (text: string, attachments: ChatAttachment[]) => {
      if (isGenerating) return;

      const userMessage: ChatMessage = {
        id: Date.now().toString(),
        role: "user",
        content: text,
        timestamp: Date.now(),
        attachments: attachments.length > 0 ? attachments : undefined,
      };
      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "",
        timestamp: Date.now(),
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsGenerating(true);
      scrollToBottom();

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const apiUrl = getApiUrl();
        const chatHistory = [...messages, userMessage].map((m) => ({
          role: m.role,
          content: m.content,
        }));
        const allMessages = [SYSTEM_PROMPT, ...chatHistory];

        for await (const chunk of streamChat(
          allMessages,
          apiUrl,
          controller.signal,
        )) {
          setMessages((prev) => {
            const updated = [...prev];
            const lastIdx = updated.length - 1;
            if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
              updated[lastIdx] = {
                ...updated[lastIdx],
                content: updated[lastIdx].content + chunk,
              };
            }
            return updated;
          });
          scrollToBottom();
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        const errorMsg =
          error instanceof Error ? error.message : "Something went wrong";
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
            updated[lastIdx] = {
              ...updated[lastIdx],
              content:
                updated[lastIdx].content || "Sorry, I encountered an error.",
              error: errorMsg,
            };
          }
          return updated;
        });
      } finally {
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
            updated[lastIdx] = { ...updated[lastIdx], isStreaming: false };
          }
          return updated;
        });
        setIsGenerating(false);
        abortControllerRef.current = null;
      }
    },
    [messages, isGenerating, scrollToBottom],
  );

  // --- Agent Mode ---
  const handleAgentSend = useCallback(
    async (text: string, _attachments: ChatAttachment[]) => {
      if (isGenerating) return;

      sessionIdRef.current = Date.now().toString();
      streamingMsgIdRef.current = null;
      currentStepIdRef.current = null;
      planViewAddedRef.current = false;
      computerViewAddedRef.current = false;

      const userItem: ChatListItem = {
        kind: "chat",
        data: {
          id: Date.now().toString(),
          role: "user",
          content: text,
          timestamp: Date.now(),
        },
      };

      setAgentEvents((prev) => [...prev, userItem]);
      setIsGenerating(true);
      setCurrentPlan(null);
      setAgentStatus({ label: "Planning..." });
      scrollToBottom();

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const apiUrl = getApiUrl();
        let eventCounter = 0;

        for await (const event of streamAgent(text, apiUrl, controller.signal)) {
          eventCounter++;
          const eventId = `evt-${Date.now()}-${eventCounter}`;

          // ── Plan events: update plan state, inject plan_view into feed once ──
          if (event.type === "plan") {
            if (event.plan) {
              if (!planViewAddedRef.current) {
                planViewAddedRef.current = true;
                const pvId = `plan-view-${sessionIdRef.current}`;
                setAgentEvents((prev) => [
                  ...prev,
                  { kind: "plan_view", id: pvId },
                ]);
              }
              setCurrentPlan((prev) => {
                const incoming = event.plan!;
                if (!prev) return incoming;
                return {
                  ...incoming,
                  steps: incoming.steps.map((s) => {
                    const old = prev.steps.find((p) => p.id === s.id);
                    return old ? { ...s, tools: old.tools } : s;
                  }),
                };
              });
            }
            if (event.status === "running") {
              setAgentStatus({ label: "Executing..." });
            } else if (event.status === "creating") {
              setAgentStatus({ label: "Planning..." });
            }
            continue;
          }

          // ── Step events: track current step, update plan ──
          if (event.type === "step" && event.step) {
            if (event.status === "running") {
              currentStepIdRef.current = event.step.id;
              setAgentStatus({ label: event.step.description });
            }
            setCurrentPlan((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                steps: prev.steps.map((s) =>
                  s.id === event.step?.id
                    ? { ...s, ...event.step, tools: s.tools }
                    : s,
                ),
              };
            });
            continue;
          }

          // ── Tool events: show inline as Manus-style cards + track in plan ──
          if (event.type === "tool") {
            const stepId = currentStepIdRef.current;
            const toolEventId = `tool-${event.tool_call_id || eventId}`;

            if (event.status === "calling") {
              setAgentStatus({
                label: event.function_name || "Using tool",
                toolName: event.tool_name,
                functionName: event.function_name,
              });

              // Add tool card inline in feed (Manus-style)
              setAgentEvents((prev) => [
                ...prev,
                { kind: "tool_card", data: event, id: toolEventId },
              ]);

              // Also track in plan
              if (stepId) {
                setCurrentPlan((prev) => {
                  if (!prev) return prev;
                  return {
                    ...prev,
                    steps: prev.steps.map((s) =>
                      s.id === stepId
                        ? { ...s, tools: [...(s.tools || []), event] }
                        : s,
                    ),
                  };
                });
              }

              // Track browser state and add computer view on first browser tool
              if (event.function_name?.startsWith("browser_")) {
                if (!computerViewAddedRef.current) {
                  computerViewAddedRef.current = true;
                  const cvId = `computer-view-${sessionIdRef.current}`;
                  setAgentEvents((prev) => [
                    ...prev,
                    { kind: "computer_view", id: cvId },
                  ]);
                }
                setBrowserState((prev) => ({
                  url: (event.function_args?.url as string) || prev?.url || "",
                  title: prev?.title || "",
                  content: prev?.content || "",
                  isLoading: true,
                }));
              }
            } else if (event.status === "called" || event.status === "error") {
              setAgentStatus({ label: "Processing..." });

              // Update the existing tool card in the feed
              setAgentEvents((prev) =>
                prev.map((item) =>
                  item.kind === "tool_card" && item.id === toolEventId
                    ? { ...item, data: event }
                    : item,
                ),
              );

              // Update plan tool tracking
              if (stepId) {
                setCurrentPlan((prev) => {
                  if (!prev) return prev;
                  return {
                    ...prev,
                    steps: prev.steps.map((s) => {
                      if (s.id !== stepId) return s;
                      const tools = s.tools || [];
                      const idx = tools.findIndex(
                        (t) =>
                          t.tool_call_id === event.tool_call_id &&
                          t.status === "calling",
                      );
                      if (idx >= 0) {
                        const updated = [...tools];
                        updated[idx] = event;
                        return { ...s, tools: updated };
                      }
                      return { ...s, tools: [...tools, event] };
                    }),
                  };
                });
              }

              // Update browser state from tool result
              if (event.function_name?.startsWith("browser_") && event.tool_content) {
                setBrowserState((prev) => ({
                  url: (event.tool_content?.url as string) || prev?.url || "",
                  title: (event.tool_content?.title as string) || prev?.title || "",
                  content: (event.tool_content?.content as string) || prev?.content || "",
                  screenshot: (event.tool_content?.screenshot_b64 as string) || prev?.screenshot,
                  isLoading: false,
                }));
              }
            }
            scrollToBottom();
            continue;
          }

          // ── Streaming final message ──
          if (event.type === "message_start") {
            const msgId = `stream-${Date.now()}`;
            streamingMsgIdRef.current = msgId;
            setAgentEvents((prev) => [
              ...prev,
              {
                kind: "agent",
                data: { type: "message", message: "", isStreaming: true },
                id: msgId,
              },
            ]);
            scrollToBottom();
            continue;
          }

          if (event.type === "message_chunk") {
            const msgId = streamingMsgIdRef.current;
            if (msgId) {
              setAgentEvents((prev) =>
                prev.map((item) =>
                  item.id === msgId && item.kind === "agent"
                    ? {
                        ...item,
                        data: {
                          ...item.data,
                          message:
                            (item.data.message || "") + (event.chunk || ""),
                        },
                      }
                    : item,
                ),
              );
              scrollToBottom();
            }
            continue;
          }

          if (event.type === "message_end") {
            const msgId = streamingMsgIdRef.current;
            if (msgId) {
              setAgentEvents((prev) =>
                prev.map((item) =>
                  item.id === msgId && item.kind === "agent"
                    ? { ...item, data: { ...item.data, isStreaming: false } }
                    : item,
                ),
              );
              streamingMsgIdRef.current = null;
            }
            continue;
          }

          // ── Visible events: message, wait (agent asking user), errors ──
          const shouldShow =
            event.type === "message" || event.type === "error" || event.type === "wait";

          if (shouldShow) {
            setAgentEvents((prev) => [
              ...prev,
              { kind: "agent", data: event, id: eventId },
            ]);
            scrollToBottom();
          }

          if (event.type === "done") {
            setAgentStatus(null);
          }
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        const errorMsg =
          error instanceof Error ? error.message : "Something went wrong";
        setAgentEvents((prev) => [
          ...prev,
          {
            kind: "agent",
            data: { type: "error", error: errorMsg },
            id: `err-${Date.now()}`,
          },
        ]);
      } finally {
        setIsGenerating(false);
        setAgentStatus(null);
        abortControllerRef.current = null;
        scrollToBottom();
      }
    },
    [isGenerating, scrollToBottom],
  );

  const handleSend = useCallback(
    (text: string, attachments: ChatAttachment[]) => {
      if (isAgentMode) {
        handleAgentSend(text, attachments);
      } else {
        handleChatSend(text, attachments);
      }
    },
    [isAgentMode, handleAgentSend, handleChatSend],
  );

  const handleStop = useCallback(() => {
    abortControllerRef.current?.abort();
    setIsGenerating(false);
    setAgentStatus(null);
  }, []);

  const handleClearChat = useCallback(() => {
    if (isGenerating) {
      abortControllerRef.current?.abort();
      setIsGenerating(false);
    }
    setMessages([]);
    setAgentEvents([]);
    setCurrentPlan(null);
    setAgentStatus(null);
    setBrowserState(null);
    sessionIdRef.current = Date.now().toString();
    streamingMsgIdRef.current = null;
    currentStepIdRef.current = null;
    planViewAddedRef.current = false;
    computerViewAddedRef.current = false;
  }, [isGenerating]);

  const toggleMode = useCallback(() => {
    if (!isGenerating) {
      setIsAgentMode((prev) => !prev);
    }
  }, [isGenerating]);

  const handleRestoreSession = useCallback((session: ChatSession) => {
    setIsAgentMode(session.mode === "agent");
    if (session.mode === "chat") {
      setMessages(session.messages);
      setAgentEvents([]);
    } else {
      setAgentEvents(session.agentEvents || []);
      setMessages([]);
    }
    setCurrentPlan(null);
    setAgentStatus(null);
    sessionIdRef.current = session.id;
  }, []);


  // --- Render ---
  const renderChatMessage = useCallback(
    ({ item }: { item: ChatMessage }) => <ChatMessageBubble message={item} />,
    [],
  );

  const renderAgentItem = useCallback(
    ({ item }: { item: ChatListItem }) => {
      if (item.kind === "chat") {
        return <ChatMessageBubble message={item.data} />;
      }
      if (item.kind === "plan_view") {
        return currentPlan ? (
          <View style={styles.planSection}>
            <AgentPlanView plan={currentPlan} />
          </View>
        ) : null;
      }
      if (item.kind === "tool_card") {
        return <AgentToolCard event={item.data} />;
      }
      if (item.kind === "computer_view") {
        return (
          <ComputerView
            browserState={browserState}
            plan={currentPlan}
            onClose={() => setBrowserState(null)}
          />
        );
      }
      return <AgentMessage event={item.data} />;
    },
    [currentPlan, browserState],
  );

  const chatKeyExtractor = useCallback((item: ChatMessage) => item.id, []);
  const agentKeyExtractor = useCallback(
    (item: ChatListItem) => {
      if (item.kind === "chat") return item.data.id;
      if (item.kind === "plan_view") return item.id;
      if (item.kind === "tool_card") return item.id;
      if (item.kind === "computer_view") return item.id;
      return item.id;
    },
    [],
  );

  const hasContent = isAgentMode
    ? agentEvents.length > 0
    : messages.length > 0;

  const showTyping =
    !isAgentMode &&
    isGenerating &&
    messages.length > 0 &&
    messages[messages.length - 1].content === "";

  return (
    <SafeAreaView style={styles.safeArea} edges={["top"]}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0C" />
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={0}
      >
        {/* Header - only show when there is content */}
        {hasContent && (
          <View style={styles.header}>
            <View style={styles.headerLeft}>
              <TouchableOpacity
                onPress={handleClearChat}
                style={styles.backBtn}
                activeOpacity={0.6}
              >
                <Ionicons name="chevron-back" size={22} color="#E8E8ED" />
              </TouchableOpacity>
              <View style={styles.headerTitleRow}>
                <Text style={styles.headerTitle}>
                  {isAgentMode ? "Dzeck Agent" : "Dzeck AI"}
                </Text>
                <View style={[styles.headerBadge, isAgentMode && styles.headerBadgeAgent]}>
                  <Text style={[styles.headerBadgeText, isAgentMode && styles.headerBadgeTextAgent]}>
                    {isAgentMode ? "Agent" : "Lite"}
                  </Text>
                </View>
              </View>
            </View>
            <View style={styles.headerRight}>
              <TouchableOpacity
                onPress={() => setShowHistory(true)}
                style={styles.iconBtn}
                activeOpacity={0.6}
              >
                <Ionicons name="time-outline" size={20} color="#8E8E93" />
              </TouchableOpacity>
              <TouchableOpacity
                onPress={handleClearChat}
                style={styles.iconBtn}
                activeOpacity={0.6}
              >
                <Ionicons name="add-outline" size={22} color="#8E8E93" />
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.iconBtn}
                activeOpacity={0.6}
              >
                <Ionicons name="ellipsis-horizontal" size={20} color="#8E8E93" />
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Content */}
        {!hasContent ? (
          /* Clean empty state - Manus style */
          <View style={styles.emptyState}>
            <Text style={styles.emptyTitle}>
              Apa yang bisa saya bantu?
            </Text>
          </View>
        ) : isAgentMode ? (
          /* Agent feed */
          <FlatList
            ref={flatListRef}
            data={agentEvents}
            renderItem={renderAgentItem}
            keyExtractor={agentKeyExtractor}
            style={styles.messageList}
            contentContainerStyle={styles.messageListContent}
            showsVerticalScrollIndicator={false}
            ListFooterComponent={
              isGenerating ? (
                <View style={styles.agentFooter}>
                  <AgentWorking
                    label={agentStatus?.label || "Agent is working..."}
                  />
                </View>
              ) : null
            }
          />
        ) : (
          /* Chat feed */
          <FlatList
            ref={flatListRef}
            data={messages}
            renderItem={renderChatMessage}
            keyExtractor={chatKeyExtractor}
            style={styles.messageList}
            contentContainerStyle={styles.messageListContent}
            showsVerticalScrollIndicator={false}
            ListFooterComponent={showTyping ? <TypingIndicator /> : null}
          />
        )}

        {/* Agent active status bar */}
        {isAgentMode && isGenerating && agentStatus?.functionName && (
          <AgentStatusBar
            status={agentStatus.label}
            toolName={agentStatus.toolName}
            functionName={agentStatus.functionName}
            isActive={true}
          />
        )}

        {/* Input */}
        <ChatInput
          onSend={handleSend}
          disabled={false}
          isGenerating={isGenerating}
          onStop={handleStop}
          isAgentMode={isAgentMode}
          onToggleMode={toggleMode}
          onShowHistory={() => setShowHistory(true)}
          showModeToggle={!hasContent}
          placeholder={
            isAgentMode
              ? "Tetapkan tugas atau tanyakan apa saja"
              : "Kirim pesan ke Dzeck AI..."
          }
        />
      </KeyboardAvoidingView>

      {/* History modal */}
      <ChatHistoryModal
        visible={showHistory}
        onClose={() => setShowHistory(false)}
        onRestoreSession={handleRestoreSession}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#0A0A0C",
  },
  container: {
    flex: 1,
    backgroundColor: "#0A0A0C",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 8,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#1A1A1F",
  },
  headerLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  backBtn: {
    width: 32,
    height: 32,
    alignItems: "center",
    justifyContent: "center",
  },
  headerTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
  },
  headerTitle: {
    fontFamily: "Inter_700Bold",
    fontSize: 16,
    color: "#FFFFFF",
    lineHeight: 20,
  },
  headerBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    backgroundColor: "#2C2C30",
  },
  headerBadgeAgent: {
    backgroundColor: "rgba(108, 92, 231, 0.15)",
  },
  headerBadgeText: {
    fontFamily: "Inter_500Medium",
    fontSize: 10,
    color: "#8E8E93",
  },
  headerBadgeTextAgent: {
    color: "#6C5CE7",
  },
  iconBtn: {
    width: 36,
    height: 36,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 8,
  },
  messageList: {
    flex: 1,
  },
  messageListContent: {
    paddingTop: 8,
    paddingBottom: 8,
  },
  planSection: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 4,
  },
  agentFooter: {
    paddingHorizontal: 16,
    paddingBottom: 8,
  },
  emptyState: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 28,
  },
  emptyTitle: {
    fontFamily: "Inter_500Medium",
    fontSize: 22,
    color: "#E8E8ED",
    textAlign: "center",
    letterSpacing: -0.3,
  },
});
