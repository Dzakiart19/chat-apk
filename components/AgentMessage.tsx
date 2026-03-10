import React, { useEffect, useRef } from "react";
import { View, Text, StyleSheet, Animated } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { AgentEvent } from "@/lib/chat";

interface AgentMessageProps {
  event: AgentEvent;
}

function StreamingCursor() {
  const opacity = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0, duration: 500, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1, duration: 500, useNativeDriver: true }),
      ]),
    ).start();
    return () => opacity.stopAnimation();
  }, [opacity]);

  return (
    <Animated.Text style={[styles.cursor, { opacity }]}>▋</Animated.Text>
  );
}

export function AgentMessage({ event }: AgentMessageProps) {
  switch (event.type) {
    case "message":
      if (!event.message && !event.isStreaming) return null;
      return (
        <View style={styles.container}>
          <View style={styles.messageRow}>
            <View style={styles.avatar}>
              <Ionicons name="sparkles" size={13} color="#FFFFFF" />
            </View>
            <View style={styles.bubble}>
              <Text style={styles.messageText} selectable>
                {event.message || ""}
                {event.isStreaming ? <StreamingCursor /> : null}
              </Text>
            </View>
          </View>
        </View>
      );

    case "title":
      return (
        <View style={styles.container}>
          <View style={styles.titleRow}>
            <Ionicons name="rocket" size={15} color="#6C5CE7" />
            <Text style={styles.titleText} numberOfLines={2}>
              {event.title || ""}
            </Text>
          </View>
        </View>
      );

    case "error":
      return (
        <View style={styles.container}>
          <View style={styles.errorRow}>
            <Ionicons name="alert-circle" size={14} color="#FF453A" />
            <Text style={styles.errorText}>{event.error || "An error occurred"}</Text>
          </View>
        </View>
      );

    default:
      return null;
  }
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingVertical: 3,
  },
  messageRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
  },
  avatar: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: "#6C5CE7",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    marginTop: 1,
  },
  bubble: {
    flex: 1,
    backgroundColor: "#141418",
    borderRadius: 16,
    borderBottomLeftRadius: 5,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: "#222228",
  },
  messageText: {
    fontFamily: "Inter_400Regular",
    fontSize: 15,
    color: "#E8E8ED",
    lineHeight: 23,
    letterSpacing: -0.1,
  },
  cursor: {
    color: "#6C5CE7",
    fontSize: 14,
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 4,
    paddingLeft: 4,
  },
  titleText: {
    fontFamily: "Inter_700Bold",
    fontSize: 17,
    color: "#FFFFFF",
    letterSpacing: -0.3,
    flex: 1,
  },
  errorRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "rgba(255,69,58,0.07)",
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: "rgba(255,69,58,0.12)",
  },
  errorText: {
    flex: 1,
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: "#FF6B6B",
    lineHeight: 18,
  },
});
