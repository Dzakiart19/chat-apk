import React, { useState, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Tool {
  tool_call_id: string;
  name: string;
  status: "pending" | "running" | "completed" | "failed";
  input?: any;
  output?: any;
  error?: string;
}

interface ToolPanelProps {
  sessionId?: string;
  onResize?: (width: number) => void;
}

export function ToolPanel({ sessionId, onResize }: ToolPanelProps) {
  const [tools, setTools] = useState<Tool[]>([]);
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const getToolIcon = (toolName: string) => {
    const iconMap: { [key: string]: string } = {
      file_read: "document-text",
      file_write: "create",
      file_delete: "trash",
      browser: "globe",
      shell: "terminal",
      search: "search",
      mcp: "settings",
    };
    return iconMap[toolName] || "settings";
  };

  const getToolColor = (status: string) => {
    switch (status) {
      case "running":
        return "#6C5CE7";
      case "completed":
        return "#34C759";
      case "failed":
        return "#FF453A";
      default:
        return "#8E8E93";
    }
  };

  const renderToolContent = (tool: Tool) => {
    return (
      <View style={styles.toolContent}>
        {/* Input */}
        {tool.input && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Input</Text>
            <View style={styles.codeBlock}>
              <Text style={styles.codeText}>
                {JSON.stringify(tool.input, null, 2)}
              </Text>
            </View>
          </View>
        )}

        {/* Output */}
        {tool.output && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Output</Text>
            <View style={styles.codeBlock}>
              <Text style={styles.codeText}>
                {typeof tool.output === "string"
                  ? tool.output
                  : JSON.stringify(tool.output, null, 2)}
              </Text>
            </View>
          </View>
        )}

        {/* Error */}
        {tool.error && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Error</Text>
            <View style={[styles.codeBlock, styles.errorBlock]}>
              <Text style={styles.errorText}>{tool.error}</Text>
            </View>
          </View>
        )}

        {/* Status */}
        {tool.status === "running" && (
          <View style={styles.statusContainer}>
            <ActivityIndicator color="#6C5CE7" size="small" />
            <Text style={styles.statusText}>Running...</Text>
          </View>
        )}
      </View>
    );
  };

  if (!isExpanded) {
    return (
      <TouchableOpacity
        style={styles.collapsedContainer}
        onPress={() => setIsExpanded(true)}
      >
        <Ionicons name="chevron-back" size={20} color="#8E8E93" />
      </TouchableOpacity>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Tools</Text>
        <TouchableOpacity
          style={styles.collapseButton}
          onPress={() => setIsExpanded(false)}
        >
          <Ionicons name="chevron-forward" size={20} color="#8E8E93" />
        </TouchableOpacity>
      </View>

      {/* Tools List */}
      <ScrollView style={styles.toolsList} showsVerticalScrollIndicator={false}>
        {tools.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="settings-outline" size={32} color="#636366" />
            <Text style={styles.emptyStateText}>No tools executed yet</Text>
          </View>
        ) : (
          tools.map((tool) => (
            <TouchableOpacity
              key={tool.tool_call_id}
              style={[
                styles.toolItem,
                selectedTool?.tool_call_id === tool.tool_call_id &&
                  styles.toolItemSelected,
              ]}
              onPress={() => setSelectedTool(tool)}
            >
              <View style={styles.toolItemIcon}>
                <Ionicons
                  name={getToolIcon(tool.name)}
                  size={16}
                  color={getToolColor(tool.status)}
                />
              </View>
              <View style={styles.toolItemContent}>
                <Text style={styles.toolItemName}>{tool.name}</Text>
                <Text style={styles.toolItemStatus}>{tool.status}</Text>
              </View>
              {tool.status === "running" && (
                <ActivityIndicator color="#6C5CE7" size="small" />
              )}
            </TouchableOpacity>
          ))
        )}
      </ScrollView>

      {/* Tool Details */}
      {selectedTool && (
        <ScrollView style={styles.detailsContainer}>
          {renderToolContent(selectedTool)}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#1A1A20",
    borderLeftWidth: 1,
    borderLeftColor: "#2C2C30",
  },
  collapsedContainer: {
    flex: 1,
    backgroundColor: "#1A1A20",
    justifyContent: "flex-start",
    alignItems: "center",
    paddingVertical: 12,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 12,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#2C2C30",
  },
  headerTitle: {
    fontSize: 14,
    fontWeight: "600",
    color: "#FFFFFF",
  },
  collapseButton: {
    width: 32,
    height: 32,
    borderRadius: 6,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#2C2C30",
  },
  toolsList: {
    flex: 1,
    paddingHorizontal: 8,
    paddingVertical: 8,
    maxHeight: "40%",
  },
  toolItem: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#2C2C30",
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 10,
    marginBottom: 8,
    gap: 8,
  },
  toolItemSelected: {
    backgroundColor: "#6C5CE7",
  },
  toolItemIcon: {
    width: 28,
    height: 28,
    borderRadius: 6,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#1A1A20",
  },
  toolItemContent: {
    flex: 1,
  },
  toolItemName: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "500",
  },
  toolItemStatus: {
    color: "#8E8E93",
    fontSize: 11,
    marginTop: 2,
  },
  emptyState: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 32,
    gap: 8,
  },
  emptyStateText: {
    color: "#636366",
    fontSize: 12,
    fontWeight: "500",
  },
  detailsContainer: {
    flex: 1,
    borderTopWidth: 1,
    borderTopColor: "#2C2C30",
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  toolContent: {
    gap: 12,
  },
  section: {
    gap: 6,
  },
  sectionTitle: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "600",
  },
  codeBlock: {
    backgroundColor: "#0A0A0C",
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: "#2C2C30",
  },
  codeText: {
    color: "#8E8E93",
    fontSize: 11,
    fontFamily: "Courier New",
  },
  errorBlock: {
    borderColor: "#FF453A",
    backgroundColor: "#FF453A10",
  },
  errorText: {
    color: "#FF453A",
    fontSize: 11,
    fontFamily: "Courier New",
  },
  statusContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 8,
  },
  statusText: {
    color: "#6C5CE7",
    fontSize: 12,
    fontWeight: "500",
  },
});
