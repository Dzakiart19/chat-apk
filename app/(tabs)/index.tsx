import React, { useState, useRef, useCallback } from "react";
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
import { streamChat, streamAgent } from "@/lib/chat";
import type {
  ChatMessage,
  ChatAttachment,
  AgentEvent,
  AgentPlan,
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

// Union type for items in our chat list (supports both chat messages and agent events)
type ChatListItem =
  | { kind: "chat"; data: ChatMessage }
  | { kind: "agent"; data: AgentEvent; id: string };

export default function ChatScreen() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [agentEvents, setAgentEvents] = useState<ChatListItem[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isAgentMode, setIsAgentMode] = useState(true);
  const [currentPlan, setCurrentPlan] = useState<AgentPlan | null>(null);
  const flatListRef = useRef<FlatList>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

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

      const assistantId = (Date.now() + 1).toString();
      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: Date.now(),
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsGenerating(true);

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
            updated[lastIdx] = {
              ...updated[lastIdx],
              isStreaming: false,
            };
          }
          return updated;
        });
        setIsGenerating(false);
        abortControllerRef.current = null;
      }
    },
    [messages, isGenerating],
  );

  // --- Agent Mode ---
  const handleAgentSend = useCallback(
    async (text: string, _attachments: ChatAttachment[]) => {
      if (isGenerating) return;

      // Add user message to agent events
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

          // Track plan updates
          if (event.type === "plan" && event.plan) {
            setCurrentPlan(event.plan);
          }

          // Update plan steps from step events
          if (event.type === "step" && event.step) {
            setCurrentPlan((prev) => {
              if (!prev) return prev;
              const updatedSteps = prev.steps.map((s) =>
                s.id === event.step?.id ? { ...s, ...event.step } : s,
              );
              return { ...prev, steps: updatedSteps };
            });
          }

          // Filter out redundant events for cleaner UI
          const shouldShow =
            event.type === "message" ||
            event.type === "title" ||
            event.type === "thinking" ||
            event.type === "error" ||
            (event.type === "plan" && event.status === "created") ||
            (event.type === "step" &&
              (event.status === "started" || event.status === "completed")) ||
            (event.type === "tool" && event.status === "called");

          if (shouldShow) {
            setAgentEvents((prev) => [
              ...prev,
              { kind: "agent", data: event, id: eventId },
            ]);
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
        abortControllerRef.current = null;
      }
    },
    [isGenerating],
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
  }, []);

  const handleClearChat = useCallback(() => {
    if (isGenerating) {
      abortControllerRef.current?.abort();
      setIsGenerating(false);
    }
    setMessages([]);
    setAgentEvents([]);
    setCurrentPlan(null);
  }, [isGenerating]);

  const toggleMode = useCallback(() => {
    if (!isGenerating) {
      setIsAgentMode((prev) => !prev);
    }
  }, [isGenerating]);

  // --- Render helpers ---
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

  // Suppress unused variable warning - currentPlan is tracked for future use
  void currentPlan;

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
              style={[
                styles.headerIcon,
                isAgentMode && styles.headerIconAgent,
              ]}
            >
              <Ionicons
                name={isAgentMode ? "rocket" : "sparkles"}
                size={16}
                color="#FFFFFF"
              />
            </View>
            <Text style={styles.headerTitle}>
              {isAgentMode ? "Dzeck Agent" : "Dzeck AI"}
            </Text>
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

            {/* Clear button */}
            {hasContent && (
              <TouchableOpacity
                onPress={handleClearChat}
                style={styles.clearButton}
                activeOpacity={0.6}
              >
                <Ionicons name="create-outline" size={22} color="#8E8E93" />
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* Messages / Agent Events */}
        {!hasContent ? (
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
                ? "Give me a task and I'll execute it autonomously"
                : "How can I help you today?"}
            </Text>
            {isAgentMode && (
              <View style={styles.agentBadge}>
                <Ionicons name="flash" size={12} color="#6C5CE7" />
                <Text style={styles.agentBadgeText}>
                  Autonomous AI Agent Mode
                </Text>
              </View>
            )}
          </View>
        ) : isAgentMode ? (
          <FlatList
            ref={flatListRef}
            data={agentEvents}
            renderItem={renderAgentItem}
            keyExtractor={agentKeyExtractor}
            style={styles.messageList}
            contentContainerStyle={styles.messageListContent}
            onContentSizeChange={() =>
              flatListRef.current?.scrollToEnd({ animated: true })
            }
            onLayout={() =>
              flatListRef.current?.scrollToEnd({ animated: false })
            }
            showsVerticalScrollIndicator={false}
            ListFooterComponent={
              isGenerating ? (
                <View style={styles.agentWorking}>
                  <Ionicons name="sync" size={14} color="#6C5CE7" />
                  <Text style={styles.agentWorkingText}>
                    Agent is working...
                  </Text>
                </View>
              ) : null
            }
          />
        ) : (
          <FlatList
            ref={flatListRef}
            data={messages}
            renderItem={renderChatMessage}
            keyExtractor={chatKeyExtractor}
            style={styles.messageList}
            contentContainerStyle={styles.messageListContent}
            onContentSizeChange={() =>
              flatListRef.current?.scrollToEnd({ animated: true })
            }
            onLayout={() =>
              flatListRef.current?.scrollToEnd({ animated: false })
            }
            showsVerticalScrollIndicator={false}
            ListFooterComponent={showTyping ? <TypingIndicator /> : null}
          />
        )}

        {/* Input */}
        <ChatInput
          onSend={handleSend}
          disabled={false}
          isGenerating={isGenerating}
          onStop={handleStop}
        />
      </KeyboardAvoidingView>
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
    paddingVertical: 12,
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
    gap: 8,
  },
  headerIcon: {
    width: 30,
    height: 30,
    borderRadius: 8,
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
    fontSize: 18,
    color: "#FFFFFF",
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
  clearButton: {
    padding: 6,
  },
  messageList: {
    flex: 1,
  },
  messageListContent: {
    paddingVertical: 12,
  },
  emptyState: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 40,
    gap: 12,
  },
  emptyIcon: {
    width: 64,
    height: 64,
    borderRadius: 20,
    backgroundColor: "rgba(108, 92, 231, 0.12)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 8,
  },
  emptyIconAgent: {
    borderWidth: 1,
    borderColor: "rgba(108, 92, 231, 0.3)",
  },
  emptyTitle: {
    fontFamily: "Inter_700Bold",
    fontSize: 26,
    color: "#FFFFFF",
  },
  emptySubtitle: {
    fontFamily: "Inter_400Regular",
    fontSize: 16,
    color: "#8E8E93",
    textAlign: "center",
  },
  agentBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(108, 92, 231, 0.1)",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    marginTop: 8,
    borderWidth: 1,
    borderColor: "rgba(108, 92, 231, 0.2)",
  },
  agentBadgeText: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 12,
    color: "#6C5CE7",
  },
  agentWorking: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingVertical: 12,
  },
  agentWorkingText: {
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: "#6C5CE7",
  },
});
