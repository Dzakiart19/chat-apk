import React, { useState, useEffect, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Animated,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { AgentEvent, ToolContent } from "@/lib/chat";

interface AgentToolCardProps {
  event: AgentEvent;
}

/** Tool icon mapping - matches ai-manus style */
function getToolIcon(functionName: string): {
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
} {
  const map: Record<
    string,
    { icon: keyof typeof Ionicons.glyphMap; color: string }
  > = {
    shell_exec: { icon: "terminal", color: "#30D158" },
    shell_view: { icon: "terminal", color: "#30D158" },
    shell_wait: { icon: "time", color: "#30D158" },
    shell_write_to_process: { icon: "terminal", color: "#30D158" },
    shell_kill_process: { icon: "close-circle", color: "#FF453A" },
    file_read: { icon: "document-text", color: "#FFD60A" },
    file_write: { icon: "save", color: "#FFD60A" },
    file_str_replace: { icon: "create", color: "#FFD60A" },
    file_find_by_name: { icon: "folder-open", color: "#FFD60A" },
    file_find_in_content: { icon: "search", color: "#FFD60A" },
    browser_navigate: { icon: "globe", color: "#FF9F0A" },
    browser_view: { icon: "eye", color: "#FF9F0A" },
    browser_click: { icon: "finger-print", color: "#FF9F0A" },
    browser_type: { icon: "create", color: "#FF9F0A" },
    browser_scroll: { icon: "arrow-down", color: "#FF9F0A" },
    browser_scroll_to_bottom: { icon: "arrow-down", color: "#FF9F0A" },
    browser_read_links: { icon: "link", color: "#FF9F0A" },
    browser_console_view: { icon: "code-slash", color: "#FF9F0A" },
    browser_restart: { icon: "refresh", color: "#FF9F0A" },
    browser_save_image: { icon: "image", color: "#FF9F0A" },
    web_search: { icon: "search", color: "#5AC8FA" },
    web_browse: { icon: "globe", color: "#5AC8FA" },
    message_notify_user: { icon: "chatbubble", color: "#BF5AF2" },
    message_ask_user: { icon: "help-circle", color: "#BF5AF2" },
    mcp_call_tool: { icon: "extension-puzzle", color: "#64D2FF" },
    mcp_list_tools: { icon: "list", color: "#64D2FF" },
  };
  return map[functionName] || { icon: "construct", color: "#8E8E93" };
}

/** Get action label for the function - ai-manus style */
function getActionLabel(functionName: string): string {
  const map: Record<string, string> = {
    shell_exec: "Executing command",
    shell_view: "Viewing output",
    shell_wait: "Waiting for process",
    shell_write_to_process: "Writing to process",
    shell_kill_process: "Killing process",
    file_read: "Reading file",
    file_write: "Writing file",
    file_str_replace: "Editing file",
    file_find_by_name: "Finding files",
    file_find_in_content: "Searching in files",
    browser_navigate: "Opening page",
    browser_view: "Viewing page",
    browser_click: "Clicking element",
    browser_type: "Typing text",
    browser_scroll: "Scrolling page",
    browser_scroll_to_bottom: "Scrolling to bottom",
    browser_read_links: "Reading links",
    browser_console_view: "Viewing console",
    browser_restart: "Restarting browser",
    browser_save_image: "Saving image",
    web_search: "Searching web",
    web_browse: "Browsing URL",
    message_notify_user: "Sending message",
    message_ask_user: "Asking question",
    mcp_call_tool: "Calling MCP tool",
    mcp_list_tools: "Listing MCP tools",
  };
  return map[functionName] || functionName;
}

/** Get the primary argument to display inline */
function getPrimaryArg(
  functionName: string,
  args: Record<string, unknown>,
): string {
  const keyMap: Record<string, string> = {
    shell_exec: "command",
    web_search: "query",
    web_browse: "url",
    browser_navigate: "url",
    file_read: "file",
    file_write: "file",
    file_str_replace: "file",
    file_find_by_name: "glob",
    file_find_in_content: "regex",
    browser_type: "text",
    message_notify_user: "text",
    message_ask_user: "text",
    mcp_call_tool: "tool_name",
  };
  const key = keyMap[functionName];
  if (key && args[key]) {
    let val = String(args[key]);
    // Clean common path prefixes
    val = val.replace(/^\/home\/ubuntu\//, "");
    return val.length > 55 ? val.slice(0, 55) + "..." : val;
  }
  const firstKey = Object.keys(args)[0];
  if (firstKey) {
    const val = String(args[firstKey] ?? "");
    return val.length > 55 ? val.slice(0, 55) + "..." : val;
  }
  return "";
}

function SpinnerDot() {
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          toValue: 1,
          duration: 600,
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 0.3,
          duration: 600,
          useNativeDriver: true,
        }),
      ]),
    ).start();
    return () => opacity.stopAnimation();
  }, [opacity]);

  return (
    <Animated.View style={[styles.spinnerDot, { opacity }]}>
      <View style={styles.spinnerDotInner} />
    </Animated.View>
  );
}

/** Render tool result content */
function ToolResultContent({
  toolContent,
  functionResult,
}: {
  toolContent?: ToolContent;
  functionResult?: string;
}) {
  if (toolContent) {
    if (toolContent.type === "shell" && toolContent.console != null) {
      return (
        <View style={styles.resultBox}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.resultScroll}
          >
            <Text style={styles.shellText} selectable numberOfLines={8}>
              {toolContent.console || "(no output)"}
            </Text>
          </ScrollView>
        </View>
      );
    }
    if (toolContent.type === "search" && toolContent.results) {
      return (
        <View style={styles.resultBox}>
          {toolContent.results.slice(0, 3).map((r, i) => (
            <View key={i} style={styles.searchItem}>
              <Text style={styles.searchTitle} numberOfLines={1}>
                {r.title}
              </Text>
              <Text style={styles.searchUrl} numberOfLines={1}>
                {r.url}
              </Text>
            </View>
          ))}
        </View>
      );
    }
    if (toolContent.type === "browser") {
      return (
        <View style={styles.resultBox}>
          {toolContent.title ? (
            <Text style={styles.browserTitle} numberOfLines={1}>
              {toolContent.title}
            </Text>
          ) : null}
          <Text style={styles.browserContent} numberOfLines={4}>
            {toolContent.content || "(page loaded)"}
          </Text>
        </View>
      );
    }
    if (toolContent.type === "file" && toolContent.content != null) {
      return (
        <View style={styles.resultBox}>
          <Text style={styles.fileText} selectable numberOfLines={6}>
            {toolContent.content || "(empty)"}
          </Text>
        </View>
      );
    }
  }

  // Fallback: show raw function result
  if (functionResult) {
    return (
      <View style={styles.resultBox}>
        <Text style={styles.shellText} selectable numberOfLines={4}>
          {functionResult.slice(0, 300)}
        </Text>
      </View>
    );
  }

  return null;
}

/**
 * Manus-style inline tool card.
 * Shows as a compact pill with icon + action + argument.
 * Expandable to show details and results.
 */
export function AgentToolCard({ event }: AgentToolCardProps) {
  const [expanded, setExpanded] = useState(false);
  const functionName = event.function_name || "";
  const functionArgs = event.function_args || {};
  const isCalling = event.status === "calling";
  const isCalled = event.status === "called";
  const isError = event.status === "error";

  const { icon, color } = getToolIcon(functionName);
  const actionLabel = getActionLabel(functionName);
  const primaryArg = getPrimaryArg(functionName, functionArgs);

  return (
    <View style={styles.wrapper}>
      <TouchableOpacity
        style={[
          styles.pill,
          isCalling && styles.pillCalling,
          isError && styles.pillError,
        ]}
        onPress={() => setExpanded(!expanded)}
        activeOpacity={0.7}
      >
        <View style={styles.pillContent}>
          <Ionicons name={icon} size={16} color={color} />
          <Text style={styles.actionLabel}>{actionLabel}</Text>
          {primaryArg ? (
            <Text style={styles.argText} numberOfLines={1}>
              <Text style={styles.argCode}>{primaryArg}</Text>
            </Text>
          ) : null}
        </View>
        <View style={styles.pillRight}>
          {isCalling && <SpinnerDot />}
          {isCalled && (
            <Ionicons name="checkmark-circle" size={14} color="#30D158" />
          )}
          {isError && (
            <Ionicons name="close-circle" size={14} color="#FF453A" />
          )}
          <Ionicons
            name={expanded ? "chevron-up" : "chevron-down"}
            size={12}
            color="#636366"
          />
        </View>
      </TouchableOpacity>

      {expanded && (
        <View style={styles.expandedBody}>
          {/* Arguments */}
          {Object.keys(functionArgs).length > 0 && (
            <View style={styles.argsBox}>
              {Object.entries(functionArgs).map(([key, val]) => (
                <Text key={key} style={styles.argLine} numberOfLines={2}>
                  <Text style={styles.argKey}>{key}: </Text>
                  <Text style={styles.argVal}>
                    {String(val ?? "").slice(0, 200)}
                  </Text>
                </Text>
              ))}
            </View>
          )}

          {/* Result content */}
          {(isCalled || isError) && (
            <ToolResultContent
              toolContent={event.tool_content}
              functionResult={event.function_result}
            />
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    paddingHorizontal: 16,
    paddingVertical: 2,
    paddingLeft: 44,
  },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#141418",
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: "#1E1E24",
  },
  pillCalling: {
    borderColor: "rgba(108, 92, 231, 0.3)",
    backgroundColor: "rgba(108, 92, 231, 0.04)",
  },
  pillError: {
    borderColor: "rgba(255, 69, 58, 0.3)",
    backgroundColor: "rgba(255, 69, 58, 0.04)",
  },
  pillContent: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    flex: 1,
    minWidth: 0,
  },
  pillRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    marginLeft: 8,
  },
  actionLabel: {
    fontFamily: "Inter_500Medium",
    fontSize: 13,
    color: "#E8E8ED",
  },
  argText: {
    flex: 1,
    minWidth: 0,
  },
  argCode: {
    fontFamily: "monospace",
    fontSize: 12,
    color: "#8E8E93",
  },
  spinnerDot: {
    width: 14,
    height: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  spinnerDotInner: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: "#6C5CE7",
  },
  expandedBody: {
    marginTop: 4,
    gap: 6,
    marginLeft: 4,
  },
  argsBox: {
    backgroundColor: "#1A1A20",
    borderRadius: 8,
    padding: 8,
    gap: 2,
  },
  argLine: {
    fontSize: 11,
    lineHeight: 16,
  },
  argKey: {
    fontFamily: "Inter_600SemiBold",
    color: "#8E8E93",
  },
  argVal: {
    fontFamily: "Inter_400Regular",
    color: "#A0A0A8",
  },
  resultBox: {
    backgroundColor: "#0D0D10",
    borderRadius: 8,
    padding: 8,
    maxHeight: 150,
    overflow: "hidden",
  },
  resultScroll: {
    maxHeight: 130,
  },
  shellText: {
    fontFamily: "monospace",
    fontSize: 11,
    color: "#30D158",
    lineHeight: 16,
  },
  searchItem: {
    paddingVertical: 4,
  },
  searchTitle: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 12,
    color: "#5AC8FA",
  },
  searchUrl: {
    fontFamily: "Inter_400Regular",
    fontSize: 10,
    color: "#636366",
    marginTop: 1,
  },
  browserTitle: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 12,
    color: "#FF9F0A",
    marginBottom: 4,
  },
  browserContent: {
    fontFamily: "Inter_400Regular",
    fontSize: 11,
    color: "#A0A0A8",
    lineHeight: 16,
  },
  fileText: {
    fontFamily: "monospace",
    fontSize: 11,
    color: "#FFD60A",
    lineHeight: 16,
  },
});
