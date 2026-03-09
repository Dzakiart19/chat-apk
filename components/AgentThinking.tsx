import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface AgentThinkingProps {
  thinking: string;
}

export function AgentThinking({ thinking }: AgentThinkingProps) {
  return (
    <View style={styles.container}>
      <View style={styles.iconContainer}>
        <Ionicons name="bulb" size={12} color="#BF5AF2" />
      </View>
      <Text style={styles.text} numberOfLines={3}>
        {thinking}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
    backgroundColor: "rgba(191, 90, 242, 0.08)",
    borderRadius: 10,
    padding: 10,
    marginVertical: 2,
    borderWidth: 1,
    borderColor: "rgba(191, 90, 242, 0.15)",
  },
  iconContainer: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: "rgba(191, 90, 242, 0.15)",
    alignItems: "center",
    justifyContent: "center",
    marginTop: 1,
  },
  text: {
    flex: 1,
    fontFamily: "Inter_400Regular",
    fontSize: 12,
    color: "#BF5AF2",
    lineHeight: 18,
    fontStyle: "italic",
  },
});
