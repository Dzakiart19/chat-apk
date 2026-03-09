import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { AgentPlanView } from "@/components/AgentPlanView";
import { AgentToolView } from "@/components/AgentToolView";
import { AgentThinking } from "@/components/AgentThinking";
import type { AgentEvent } from "@/lib/chat";

interface AgentMessageProps {
  event: AgentEvent;
}

export function AgentMessage({ event }: AgentMessageProps) {
  switch (event.type) {
    case "thinking":
      return (
        <View style={styles.container}>
          <AgentThinking thinking={event.thinking || event.content || "Thinking..."} />
        </View>
      );

    case "plan":
      if (event.plan) {
        return (
          <View style={styles.container}>
            <AgentPlanView plan={event.plan} />
          </View>
        );
      }
      return null;

    case "step":
      if (event.step) {
        return (
          <View style={styles.container}>
            <View style={styles.stepEvent}>
              <StepStatusBadge status={event.status || ""} />
              <Text style={styles.stepText} numberOfLines={2}>
                {event.step.description}
              </Text>
            </View>
          </View>
        );
      }
      return null;

    case "tool":
      return (
        <View style={styles.container}>
          <AgentToolView
            toolName={event.tool_name || ""}
            functionName={event.function_name || ""}
            functionArgs={event.function_args || {}}
            status={event.status || ""}
            toolContent={event.tool_content}
            functionResult={event.function_result}
          />
        </View>
      );

    case "message":
      return (
        <View style={styles.container}>
          <View style={styles.messageContainer}>
            <View style={styles.avatar}>
              <Ionicons name="sparkles" size={14} color="#FFFFFF" />
            </View>
            <View style={styles.messageBubble}>
              <Text style={styles.messageText} selectable>
                {event.message || ""}
              </Text>
            </View>
          </View>
        </View>
      );

    case "title":
      return (
        <View style={styles.container}>
          <View style={styles.titleContainer}>
            <Ionicons name="rocket" size={16} color="#6C5CE7" />
            <Text style={styles.titleText}>{event.title || "Task"}</Text>
          </View>
        </View>
      );

    case "error":
      return (
        <View style={styles.container}>
          <View style={styles.errorContainer}>
            <Ionicons name="alert-circle" size={14} color="#FF453A" />
            <Text style={styles.errorText}>{event.error || "Unknown error"}</Text>
          </View>
        </View>
      );

    case "wait":
      return (
        <View style={styles.container}>
          <View style={styles.waitContainer}>
            <Ionicons name="hourglass" size={14} color="#FF9F0A" />
            <Text style={styles.waitText}>
              {event.prompt || "Waiting for input..."}
            </Text>
          </View>
        </View>
      );

    case "done":
      return null;

    default:
      return null;
  }
}

function StepStatusBadge({ status }: { status: string }) {
  switch (status) {
    case "started":
      return (
        <View style={[styles.badge, styles.badgeRunning]}>
          <Ionicons name="play" size={10} color="#6C5CE7" />
          <Text style={[styles.badgeText, styles.badgeTextRunning]}>Running</Text>
        </View>
      );
    case "completed":
      return (
        <View style={[styles.badge, styles.badgeCompleted]}>
          <Ionicons name="checkmark" size={10} color="#30D158" />
          <Text style={[styles.badgeText, styles.badgeTextCompleted]}>Done</Text>
        </View>
      );
    case "failed":
      return (
        <View style={[styles.badge, styles.badgeFailed]}>
          <Ionicons name="close" size={10} color="#FF453A" />
          <Text style={[styles.badgeText, styles.badgeTextFailed]}>Failed</Text>
        </View>
      );
    default:
      return null;
  }
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingVertical: 2,
  },
  stepEvent: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 4,
  },
  stepText: {
    flex: 1,
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: "#A0A0A8",
    lineHeight: 18,
  },
  badge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
  },
  badgeRunning: {
    backgroundColor: "rgba(108, 92, 231, 0.12)",
  },
  badgeCompleted: {
    backgroundColor: "rgba(48, 209, 88, 0.12)",
  },
  badgeFailed: {
    backgroundColor: "rgba(255, 69, 58, 0.12)",
  },
  badgeText: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 10,
  },
  badgeTextRunning: {
    color: "#6C5CE7",
  },
  badgeTextCompleted: {
    color: "#30D158",
  },
  badgeTextFailed: {
    color: "#FF453A",
  },
  messageContainer: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
  },
  avatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: "#6C5CE7",
    alignItems: "center",
    justifyContent: "center",
  },
  messageBubble: {
    flex: 1,
    backgroundColor: "#1A1A20",
    borderRadius: 18,
    borderBottomLeftRadius: 6,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  messageText: {
    fontFamily: "Inter_400Regular",
    fontSize: 15,
    color: "#E8E8ED",
    lineHeight: 22,
  },
  titleContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 8,
    paddingHorizontal: 4,
  },
  titleText: {
    fontFamily: "Inter_700Bold",
    fontSize: 18,
    color: "#FFFFFF",
  },
  errorContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(255, 69, 58, 0.08)",
    borderRadius: 10,
    padding: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 69, 58, 0.15)",
  },
  errorText: {
    flex: 1,
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: "#FF6B6B",
    lineHeight: 18,
  },
  waitContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(255, 159, 10, 0.08)",
    borderRadius: 10,
    padding: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 159, 10, 0.15)",
  },
  waitText: {
    flex: 1,
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: "#FF9F0A",
    lineHeight: 18,
  },
});
