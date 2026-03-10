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

const AGENT_SUGGESTIONS = [
  "Search latest AI news and summarize it",
  "Find the top 5 JavaScript frameworks in 2025",
  "Research and compare cloud storage options",
  "Write a Python script to rename files",
];

const CHAT_SUGGESTIONS = [
  "Explain quantum computing simply",
  "Write a cover letter for a software engineer",
  "Translate this to Spanish: Hello, how are you?",
  "Give me 5 healthy breakfast ideas",
];

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
  const flatListRef = useRef<FlatList>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string>(Date.now().toString());

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
      setAgentStatus({ label: "Thinking..." });
      scrollToBottom();

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const apiUrl = getApiUrl();
        let eventCounter = 0;

        for await (const event of streamAgent(
          text,
          apiUrl,
          controller.signal,
        )) {
          eventCounter++;
          const eventId = `evt-${Date.now()}-${eventCounter}`;

          // Update live plan state
          if (event.type === "plan" && event.plan) {
            setCurrentPlan(event.plan);
            if (event.status === "running") {
              setAgentStatus({ label: "Executing plan..." });
            }
          }

          // Update live step status within plan
          if (event.type === "step" && event.step) {
            setCurrentPlan((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                steps: prev.steps.map((s) =>
                  s.id === event.step?.id ? { ...s, ...event.step } : s,
                ),
              };
            });
            if (event.status === "running") {
              setAgentStatus({
                label: `Running: ${event.step.description}`,
              });
            }
          }

          // Track active tool for status bar
          if (event.type === "tool") {
            if (event.status === "calling") {
              setAgentStatus({
                label: event.function_name || "Using tool",
                toolName: event.tool_name,
                functionName: event.function_name,
              });
            } else if (event.status === "called") {
              setAgentStatus({ label: "Processing result..." });
            }

            const toolCallId = event.tool_call_id;
            if (event.status === "calling") {
              setAgentEvents((prev) => [
                ...prev,
                { kind: "agent", data: event, id: eventId },
              ]);
            } else if (
              event.status === "called" ||
              event.status === "error"
            ) {
              setAgentEvents((prev) => {
                const existingIdx = prev.findIndex(
                  (item) =>
                    item.kind === "agent" &&
                    item.data.type === "tool" &&
                    item.data.tool_call_id === toolCallId &&
                    item.data.status === "calling",
                );
                if (existingIdx >= 0) {
                  const updated = [...prev];
                  updated[existingIdx] = { ...updated[existingIdx], data: event };
                  return updated;
                }
                return [...prev, { kind: "agent", data: event, id: eventId }];
              });
            }
            scrollToBottom();
            continue;
          }

          // Filter and display relevant events
          const shouldShow =
            event.type === "message" ||
            event.type === "title" ||
            event.type === "thinking" ||
            event.type === "error" ||
            event.type === "wait";

          if (shouldShow) {
            if (event.type === "thinking") {
              setAgentStatus({ label: event.content || "Thinking..." });
            }
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
    sessionIdRef.current = Date.now().toString();
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

  const handleSuggestion = useCallback(
    (text: string) => {
      handleSend(text, []);
    },
    [handleSend],
  );

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
      return <AgentMessage event={item.data} />;
    },
    [],
  );

  const chatKeyExtractor = useCallback((item: ChatMessage) => item.id, []);
  const agentKeyExtractor = useCallback(
    (item: ChatListItem) =>
      item.kind === "chat" ? item.data.id : item.id,
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

  const suggestions = isAgentMode ? AGENT_SUGGESTIONS : CHAT_SUGGESTIONS;

  const AgentListHeader = useCallback(() => {
    if (!currentPlan) return null;
    return (
      <View style={styles.planSection}>
        <AgentPlanView plan={currentPlan} />
      </View>
    );
  }, [currentPlan]);

  return (
    <SafeAreaView style={styles.safeArea} edges={["top"]}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0C" />
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={0}
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <View
              style={[styles.headerIcon, isAgentMode && styles.headerIconAgent]}
            >
              <Ionicons
                name={isAgentMode ? "rocket" : "sparkles"}
                size={16}
                color="#FFFFFF"
              />
            </View>
            <View>
              <Text style={styles.headerTitle}>
                {isAgentMode ? "Dzeck Agent" : "Dzeck AI"}
              </Text>
              {isAgentMode && (
                <Text style={styles.headerSubtitle}>Autonomous Mode</Text>
              )}
            </View>
          </View>
          <View style={styles.headerRight}>
            {/* Mode Toggle */}
            <TouchableOpacity
              onPress={toggleMode}
              style={[
                styles.modeToggle,
                isAgentMode && styles.modeToggleActive,
              ]}
              activeOpacity={0.6}
              disabled={isGenerating}
            >
              <Ionicons
                name={isAgentMode ? "flash" : "chatbubble"}
                size={14}
                color={isAgentMode ? "#6C5CE7" : "#8E8E93"}
              />
              <Text
                style={[
                  styles.modeToggleText,
                  isAgentMode && styles.modeToggleTextActive,
                ]}
              >
                {isAgentMode ? "Agent" : "Chat"}
              </Text>
            </TouchableOpacity>

            {/* History button */}
            <TouchableOpacity
              onPress={() => setShowHistory(true)}
              style={styles.iconBtn}
              activeOpacity={0.6}
            >
              <Ionicons name="time-outline" size={20} color="#8E8E93" />
            </TouchableOpacity>

            {/* New chat button */}
            {hasContent && (
              <TouchableOpacity
                onPress={handleClearChat}
                style={styles.iconBtn}
                activeOpacity={0.6}
              >
                <Ionicons name="create-outline" size={22} color="#8E8E93" />
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* Content */}
        {!hasContent ? (
          /* Empty state */
          <View style={styles.emptyState}>
            <View
              style={[
                styles.emptyIcon,
                isAgentMode && styles.emptyIconAgent,
              ]}
            >
              <Ionicons
                name={isAgentMode ? "rocket" : "sparkles"}
                size={32}
                color="#6C5CE7"
              />
            </View>
            <Text style={styles.emptyTitle}>
              {isAgentMode ? "Dzeck Agent" : "Dzeck AI"}
            </Text>
            <Text style={styles.emptySubtitle}>
              {isAgentMode
                ? "Give me a complex task and I'll execute it step by step"
                : "How can I help you today?"}
            </Text>
            {isAgentMode && (
              <View style={styles.agentCapabilities}>
                {[
                  { icon: "search", label: "Web Search" },
                  { icon: "globe", label: "Browse Web" },
                  { icon: "terminal", label: "Run Code" },
                  { icon: "document-text", label: "Read Files" },
                ].map((cap) => (
                  <View key={cap.label} style={styles.capabilityBadge}>
                    <Ionicons
                      name={cap.icon as keyof typeof Ionicons.glyphMap}
                      size={12}
                      color="#6C5CE7"
                    />
                    <Text style={styles.capabilityText}>{cap.label}</Text>
                  </View>
                ))}
              </View>
            )}
            {/* Suggestions */}
            <View style={styles.suggestions}>
              <Text style={styles.suggestionsLabel}>Try asking:</Text>
              {suggestions.map((s) => (
                <TouchableOpacity
                  key={s}
                  style={styles.suggestionPill}
                  onPress={() => handleSuggestion(s)}
                  activeOpacity={0.7}
                >
                  <Text style={styles.suggestionText}>{s}</Text>
                </TouchableOpacity>
              ))}
            </View>
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
            ListHeaderComponent={AgentListHeader}
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
          placeholder={
            isAgentMode
              ? "Give me a task to execute autonomously..."
              : "Message Dzeck AI..."
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
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "#1E1E24",
  },
  headerLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  headerIcon: {
    width: 32,
    height: 32,
    borderRadius: 10,
    backgroundColor: "#6C5CE7",
    alignItems: "center",
    justifyContent: "center",
  },
  headerIconAgent: {
    backgroundColor: "#5A4FCF",
    borderWidth: 1,
    borderColor: "rgba(108, 92, 231, 0.5)",
  },
  headerTitle: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 17,
    color: "#FFFFFF",
    lineHeight: 22,
  },
  headerSubtitle: {
    fontFamily: "Inter_400Regular",
    fontSize: 10,
    color: "#6C5CE7",
    lineHeight: 14,
    letterSpacing: 0.3,
  },
  modeToggle: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 14,
    backgroundColor: "#1A1A20",
    borderWidth: 1,
    borderColor: "#2C2C30",
  },
  modeToggleActive: {
    backgroundColor: "rgba(108, 92, 231, 0.12)",
    borderColor: "rgba(108, 92, 231, 0.3)",
  },
  modeToggleText: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 12,
    color: "#8E8E93",
  },
  modeToggleTextActive: {
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
    gap: 10,
  },
  emptyIcon: {
    width: 68,
    height: 68,
    borderRadius: 22,
    backgroundColor: "rgba(108, 92, 231, 0.12)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 4,
  },
  emptyIconAgent: {
    borderWidth: 1,
    borderColor: "rgba(108, 92, 231, 0.3)",
  },
  emptyTitle: {
    fontFamily: "Inter_700Bold",
    fontSize: 24,
    color: "#FFFFFF",
  },
  emptySubtitle: {
    fontFamily: "Inter_400Regular",
    fontSize: 15,
    color: "#8E8E93",
    textAlign: "center",
    lineHeight: 22,
  },
  agentCapabilities: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "center",
    gap: 8,
    marginTop: 4,
  },
  capabilityBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 12,
    backgroundColor: "rgba(108, 92, 231, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(108, 92, 231, 0.18)",
  },
  capabilityText: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 11,
    color: "#8E8E93",
  },
  suggestions: {
    width: "100%",
    gap: 8,
    marginTop: 8,
  },
  suggestionsLabel: {
    fontFamily: "Inter_400Regular",
    fontSize: 12,
    color: "#636366",
    textAlign: "center",
    marginBottom: 2,
  },
  suggestionPill: {
    backgroundColor: "#141418",
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: "#2C2C30",
    width: "100%",
  },
  suggestionText: {
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: "#C8C8D4",
    lineHeight: 18,
  },
});
