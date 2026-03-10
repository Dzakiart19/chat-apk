import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { ChatMessage } from "./ChatMessage";
import { ChatBox } from "./ChatBox";
import { PlanPanel } from "./PlanPanel";
import { ToolPanel } from "./ToolPanel";
import { apiService } from "@/lib/api-service";

interface Message {
  id: string;
  type: "user" | "assistant" | "tool" | "step" | "attachments";
  content: any;
  timestamp: Date;
}

interface Plan {
  steps: Array<{
    id: string;
    description: string;
    status: "pending" | "running" | "completed" | "failed";
  }>;
}

interface ChatPageProps {
  sessionId?: string;
  isLeftPanelShow: boolean;
  onToggleLeftPanel: () => void;
}

export function ChatPage({
  sessionId,
  isLeftPanelShow,
  onToggleLeftPanel,
}: ChatPageProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [inputMessage, setInputMessage] = useState("");
  const [title, setTitle] = useState("New Chat");
  const [plan, setPlan] = useState<Plan | undefined>();
  const [attachments, setAttachments] = useState<any[]>([]);
  const [follow, setFollow] = useState(true);
  const [shareMode, setShareMode] = useState<"private" | "public">("private");
  const [linkCopied, setLinkCopied] = useState(false);
  const [sharingLoading, setSharingLoading] = useState(false);
  const [isAgentMode, setIsAgentMode] = useState(true);

  const flatListRef = useRef<FlatList>(null);
  const cancelChatRef = useRef<(() => void) | null>(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    if (follow && messages.length > 0) {
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 100);
    }
  }, [messages, follow]);

  // Handle submit message
  const handleSubmit = useCallback(async () => {
    if (!inputMessage.trim()) return;

    const userMessage: Message = {
      id: `msg_${Date.now()}`,
      type: "user",
      content: {
        content: inputMessage,
        timestamp: new Date().toISOString(),
      },
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputMessage("");
    setIsLoading(true);

    try {
      if (isAgentMode) {
        // Use agent mode with SSE
        await apiService.agent(
          {
            message: inputMessage,
            messages: messages.map((m) => ({
              role: m.type === "user" ? "user" : "assistant",
              content:
                typeof m.content === "string"
                  ? m.content
                  : m.content.content,
            })),
            model: "@cf/meta/llama-3.1-70b-instruct",
            attachments: attachments,
          },
          {
            onMessage: (data) => {
              if (data.type === "message") {
                const assistantMessage: Message = {
                  id: `msg_${Date.now()}`,
                  type: "assistant",
                  content: {
                    content: data.content,
                    timestamp: new Date().toISOString(),
                  },
                  timestamp: new Date(),
                };
                setMessages((prev) => [...prev, assistantMessage]);
              } else if (data.type === "tool") {
                const toolMessage: Message = {
                  id: `msg_${Date.now()}`,
                  type: "tool",
                  content: data,
                  timestamp: new Date(),
                };
                setMessages((prev) => [...prev, toolMessage]);
              } else if (data.type === "step") {
                const stepMessage: Message = {
                  id: `msg_${Date.now()}`,
                  type: "step",
                  content: data,
                  timestamp: new Date(),
                };
                setMessages((prev) => [...prev, stepMessage]);
              } else if (data.type === "title") {
                setTitle(data.title);
              } else if (data.type === "plan") {
                setPlan(data);
              }
            },
            onError: (error) => {
              console.error("Agent error:", error);
              const errorMessage: Message = {
                id: `msg_${Date.now()}`,
                type: "assistant",
                content: {
                  content: `Error: ${error}`,
                  timestamp: new Date().toISOString(),
                },
                timestamp: new Date(),
              };
              setMessages((prev) => [...prev, errorMessage]);
            },
            onDone: () => {
              setIsLoading(false);
            },
          }
        );
      } else {
        // Use regular chat mode
        const response = await apiService.chat({
          messages: messages.map((m) => ({
            role: m.type === "user" ? "user" : "assistant",
            content:
              typeof m.content === "string" ? m.content : m.content.content,
          })),
        });

        const assistantMessage: Message = {
          id: `msg_${Date.now()}`,
          type: "assistant",
          content: {
            content: response.content,
            timestamp: response.timestamp,
          },
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMessage]);
        setIsLoading(false);
      }
    } catch (error) {
      console.error("Chat error:", error);
      const errorMessage: Message = {
        id: `msg_${Date.now()}`,
        type: "assistant",
        content: {
          content: `Error: ${error}`,
          timestamp: new Date().toISOString(),
        },
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      setIsLoading(false);
    }
  }, [inputMessage, messages, isAgentMode, attachments]);

  const handleStop = useCallback(() => {
    if (cancelChatRef.current) {
      cancelChatRef.current();
      cancelChatRef.current = null;
    }
    setIsLoading(false);
  }, []);

  const handleShareModeChange = useCallback(
    async (mode: "private" | "public") => {
      setSharingLoading(true);
      try {
        setShareMode(mode);
        // API call to update share mode
      } catch (error) {
        console.error("Failed to change share mode:", error);
      } finally {
        setSharingLoading(false);
      }
    },
    []
  );

  const handleCopyLink = useCallback(async () => {
    try {
      // Copy link to clipboard
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy link:", error);
    }
  }, []);

  const renderMessage = useCallback(
    ({ item }: { item: Message }) => (
      <ChatMessage
        message={item}
        onToolClick={(toolName) => {
          console.log("Tool clicked:", toolName);
        }}
      />
    ),
    []
  );

  const renderEmpty = () => (
    <View style={styles.emptyContainer}>
      <Ionicons name="sparkles" size={48} color="#6C5CE7" />
      <Text style={styles.emptyTitle}>Welcome to Dzeck AI</Text>
      <Text style={styles.emptySubtitle}>
        {isAgentMode
          ? "Tell me what you want to accomplish"
          : "Ask me anything"}
      </Text>
    </View>
  );

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={styles.container}
      keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 20}
    >
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          {!isLeftPanelShow && (
            <TouchableOpacity
              style={styles.toggleButton}
              onPress={onToggleLeftPanel}
            >
              <Ionicons name="menu" size={20} color="#8E8E93" />
            </TouchableOpacity>
          )}
          <Text style={styles.title} numberOfLines={1}>
            {title}
          </Text>
        </View>

        <View style={styles.headerRight}>
          <TouchableOpacity
            style={styles.modeButton}
            onPress={() => setIsAgentMode(!isAgentMode)}
          >
            <Ionicons
              name={isAgentMode ? "flash" : "git-branch-outline"}
              size={18}
              color={isAgentMode ? "#6C5CE7" : "#8E8E93"}
            />
          </TouchableOpacity>
          <TouchableOpacity style={styles.shareButton}>
            <Ionicons name="share-social-outline" size={18} color="#8E8E93" />
          </TouchableOpacity>
        </View>
      </View>

      {/* Messages */}
      <FlatList
        ref={flatListRef}
        data={messages}
        renderItem={renderMessage}
        keyExtractor={(item) => item.id}
        ListEmptyComponent={renderEmpty}
        contentContainerStyle={styles.messageList}
        scrollEnabled={true}
        showsVerticalScrollIndicator={false}
        onScroll={(event) => {
          const offsetY = event.nativeEvent.contentOffset.y;
          const contentHeight = event.nativeEvent.contentSize.height;
          const layoutHeight = event.nativeEvent.layoutMeasurement.height;
          const isAtBottom =
            contentHeight - layoutHeight - offsetY < 100;
          setFollow(isAtBottom);
        }}
      />

      {/* Plan Panel */}
      {plan && plan.steps.length > 0 && <PlanPanel plan={plan} />}

      {/* Loading Indicator */}
      {isLoading && (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="small" color="#6C5CE7" />
          <Text style={styles.loadingText}>
            {isAgentMode ? "Agent is working..." : "Thinking..."}
          </Text>
        </View>
      )}

      {/* Input */}
      <ChatBox
        value={inputMessage}
        onChangeText={setInputMessage}
        onSubmit={handleSubmit}
        onStop={handleStop}
        isLoading={isLoading}
        isAgentMode={isAgentMode}
        attachments={attachments}
      />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
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
    borderBottomColor: "#2C2C30",
  },
  headerLeft: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  toggleButton: {
    width: 36,
    height: 36,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#1A1A20",
  },
  title: {
    fontSize: 16,
    fontWeight: "600",
    color: "#FFFFFF",
    flex: 1,
  },
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  modeButton: {
    width: 36,
    height: 36,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#1A1A20",
    borderWidth: 1,
    borderColor: "#2C2C30",
  },
  shareButton: {
    width: 36,
    height: 36,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#1A1A20",
    borderWidth: 1,
    borderColor: "#2C2C30",
  },
  messageList: {
    flexGrow: 1,
    paddingVertical: 16,
  },
  emptyContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: "600",
    color: "#FFFFFF",
  },
  emptySubtitle: {
    fontSize: 14,
    color: "#8E8E93",
  },
  loadingContainer: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 8,
  },
  loadingText: {
    color: "#8E8E93",
    fontSize: 14,
  },
});
