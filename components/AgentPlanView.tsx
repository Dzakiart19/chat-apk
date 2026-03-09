import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { AgentPlan, AgentPlanStep } from "@/lib/chat";

interface AgentPlanViewProps {
  plan: AgentPlan;
}

function StepStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return <Ionicons name="checkmark-circle" size={16} color="#30D158" />;
    case "running":
      return <Ionicons name="sync" size={16} color="#6C5CE7" />;
    case "failed":
      return <Ionicons name="close-circle" size={16} color="#FF453A" />;
    default:
      return <Ionicons name="ellipse-outline" size={16} color="#636366" />;
  }
}

function StepItem({ step, index }: { step: AgentPlanStep; index: number }) {
  const isActive = step.status === "running";
  const isDone = step.status === "completed";
  const isFailed = step.status === "failed";

  return (
    <View
      style={[
        styles.stepItem,
        isActive && styles.stepItemActive,
        isDone && styles.stepItemDone,
        isFailed && styles.stepItemFailed,
      ]}
    >
      <StepStatusIcon status={step.status} />
      <View style={styles.stepContent}>
        <Text
          style={[
            styles.stepDescription,
            isDone && styles.stepDescriptionDone,
            isFailed && styles.stepDescriptionFailed,
          ]}
          numberOfLines={2}
        >
          {step.description}
        </Text>
        {step.result && isDone && (
          <Text style={styles.stepResult} numberOfLines={2}>
            {step.result}
          </Text>
        )}
        {step.error && isFailed && (
          <Text style={styles.stepError} numberOfLines={2}>
            {step.error}
          </Text>
        )}
      </View>
    </View>
  );
}

export function AgentPlanView({ plan }: AgentPlanViewProps) {
  const completedCount = plan.steps.filter(
    (s) => s.status === "completed",
  ).length;
  const totalCount = plan.steps.length;
  const progress = totalCount > 0 ? completedCount / totalCount : 0;

  return (
    <View style={styles.container}>
      {/* Plan header */}
      <View style={styles.header}>
        <View style={styles.headerIcon}>
          <Ionicons name="list" size={14} color="#6C5CE7" />
        </View>
        <Text style={styles.headerTitle}>Execution Plan</Text>
        <Text style={styles.progressText}>
          {completedCount}/{totalCount}
        </Text>
      </View>

      {/* Progress bar */}
      <View style={styles.progressBar}>
        <View
          style={[styles.progressFill, { width: `${progress * 100}%` }]}
        />
      </View>

      {/* Steps */}
      <View style={styles.stepsList}>
        {plan.steps.map((step, index) => (
          <StepItem key={step.id || index} step={step} index={index} />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#141418",
    borderRadius: 14,
    padding: 14,
    marginVertical: 4,
    borderWidth: 1,
    borderColor: "#2C2C30",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 10,
  },
  headerIcon: {
    width: 24,
    height: 24,
    borderRadius: 6,
    backgroundColor: "rgba(108, 92, 231, 0.15)",
    alignItems: "center",
    justifyContent: "center",
  },
  headerTitle: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 14,
    color: "#E8E8ED",
    flex: 1,
  },
  progressText: {
    fontFamily: "Inter_400Regular",
    fontSize: 12,
    color: "#8E8E93",
  },
  progressBar: {
    height: 3,
    backgroundColor: "#2C2C30",
    borderRadius: 2,
    marginBottom: 10,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    backgroundColor: "#6C5CE7",
    borderRadius: 2,
  },
  stepsList: {
    gap: 6,
  },
  stepItem: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
    paddingVertical: 6,
    paddingHorizontal: 8,
    borderRadius: 8,
  },
  stepItemActive: {
    backgroundColor: "rgba(108, 92, 231, 0.08)",
  },
  stepItemDone: {
    opacity: 0.7,
  },
  stepItemFailed: {
    backgroundColor: "rgba(255, 69, 58, 0.08)",
  },
  stepContent: {
    flex: 1,
  },
  stepDescription: {
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: "#E8E8ED",
    lineHeight: 18,
  },
  stepDescriptionDone: {
    color: "#8E8E93",
  },
  stepDescriptionFailed: {
    color: "#FF6B6B",
  },
  stepResult: {
    fontFamily: "Inter_400Regular",
    fontSize: 11,
    color: "#30D158",
    marginTop: 2,
    lineHeight: 16,
  },
  stepError: {
    fontFamily: "Inter_400Regular",
    fontSize: 11,
    color: "#FF453A",
    marginTop: 2,
    lineHeight: 16,
  },
});
