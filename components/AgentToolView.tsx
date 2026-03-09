import React, { useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { ToolContent } from "@/lib/chat";

interface AgentToolViewProps {
  toolName: string;
  functionName: string;
  functionArgs: Record<string, unknown>;
  status: string;
  toolContent?: ToolContent;
  functionResult?: string;
}

function ToolIcon({ name }: { name: string }) {
  switch (name) {
    case "shell_exec":
      return <Ionicons name="terminal" size={14} color="#30D158" />;
    case "web_search":
      return <Ionicons name="search" size={14} color="#5AC8FA" />;
    case "web_browse":
    case "browser_navigate":
    case "browser_view":
    case "browser_restart":
      return <Ionicons name="globe" size={14} color="#FF9F0A" />;
    case "file_read":
    case "file_write":
    case "file_str_replace":
    case "file_find_by_name":
    case "file_find_in_content":
      return <Ionicons name="document-text" size={14} color="#FFD60A" />;
    case "message_notify_user":
    case "message_ask_user":
      return <Ionicons name="chatbubble" size={14} color="#BF5AF2" />;
    case "mcp_call_tool":
    case "mcp_list_tools":
      return <Ionicons name="extension-puzzle" size={14} color="#64D2FF" />;
    default:
      return <Ionicons name="construct" size={14} color="#8E8E93" />;
  }
}


function ShellContent({ content }: { content: string }) {
  return (
    <View style={styles.shellContainer}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <Text style={styles.shellText} selectable>
          {content || "(no output)"}
        </Text>
      </ScrollView>
    </View>
  );
}

function SearchContent({
  results,
}: {
  results: { title: string; url: string; snippet: string }[];
}) {
  return (
    <View style={styles.searchContainer}>
      {results.slice(0, 5).map((result, i) => (
        <View key={i} style={styles.searchResult}>
          <Text style={styles.searchTitle} numberOfLines={1}>
            {result.title}
          </Text>
          <Text style={styles.searchUrl} numberOfLines={1}>
            {result.url}
          </Text>
          {result.snippet ? (
            <Text style={styles.searchSnippet} numberOfLines={2}>
              {result.snippet}
            </Text>
          ) : null}
        </View>
      ))}
    </View>
  );
}

function BrowserContent({
  title,
  content,
}: {
  title?: string;
  content?: string;
}) {
  return (
    <View style={styles.browserContainer}>
      {title ? (
        <Text style={styles.browserTitle} numberOfLines={1}>
          {title}
        </Text>
      ) : null}
      <Text style={styles.browserContent} numberOfLines={8}>
        {content || "(empty page)"}
      </Text>
    </View>
  );
}

function FileContent({ content }: { content: string }) {
  return (
    <View style={styles.fileContainer}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <Text style={styles.fileText} selectable numberOfLines={10}>
          {content || "(empty)"}
        </Text>
      </ScrollView>
    </View>
  );
}

/**
 * Get the primary argument to show inline on the tool card (ai-manus style).
 * Maps function names to their most relevant argument key.
 */
function getToolFunctionArg(functionName: string, args: Record<string, unknown>): string {
  const argKeyMap: Record<string, string> = {
    shell_exec: "command",
    shell_view: "id",
    shell_wait: "id",
    shell_write_to_process: "input",
    shell_kill_process: "id",
    file_read: "file",
    file_write: "file",
    file_str_replace: "file",
    file_find_by_name: "path",
    file_find_in_content: "file",
    browser_navigate: "url",
    browser_view: "page",
    browser_restart: "url",
    browser_click: "element",
    browser_type: "text",
    browser_scroll: "direction",
    browser_scroll_to_bottom: "page",
    browser_read_links: "page",
    browser_console_view: "console",
    browser_save_image: "save_dir",
    web_search: "query",
    web_browse: "url",
    message_notify_user: "text",
    message_ask_user: "text",
    mcp_call_tool: "tool_name",
    mcp_list_tools: "",
  };
  const key = argKeyMap[functionName] || "";
  if (!key) {
    // Fall back to first arg value
    const firstKey = Object.keys(args)[0];
    if (firstKey) {
      const val = String(args[firstKey] ?? "");
      return val.length > 60 ? val.slice(0, 60) + "..." : val;
    }
    return "";
  }
  const val = String(args[key] ?? "");
  // Strip common path prefix for cleaner display
  const cleaned = val.replace(/^\/home\/ubuntu\//, "");
  return cleaned.length > 60 ? cleaned.slice(0, 60) + "..." : cleaned;
}

/**
 * Get the display label for the function (ai-manus style action description).
 */
function getToolFunctionLabel(functionName: string): string {
  const labelMap: Record<string, string> = {
    shell_exec: "Executing command",
    shell_view: "Viewing output",
    shell_wait: "Waiting for command",
    shell_write_to_process: "Writing to process",
    shell_kill_process: "Terminating process",
    file_read: "Reading file",
    file_write: "Writing file",
    file_str_replace: "Replacing content",
    file_find_by_name: "Finding file",
    file_find_in_content: "Searching content",
    browser_navigate: "Navigating to page",
    browser_view: "Viewing page",
    browser_click: "Clicking element",
    browser_type: "Entering text",
    browser_scroll: "Scrolling page",
    browser_scroll_to_bottom: "Scrolling to bottom",
    browser_read_links: "Reading links",
    browser_console_view: "Viewing console",
    browser_restart: "Restarting browser",
    browser_save_image: "Saving image",
    web_search: "Searching web",
    web_browse: "Browsing URL",
    message_notify_user: "Sending notification",
    message_ask_user: "Asking question",
    mcp_call_tool: "Calling MCP tool",
    mcp_list_tools: "Listing MCP tools",
  };
  return labelMap[functionName] || functionName;
}

export function AgentToolView({
  toolName,
  functionName,
  functionArgs,
  status,
  toolContent,
  functionResult,
}: AgentToolViewProps) {
  const [expanded, setExpanded] = useState(false);
  const isCalling = status === "calling";
  const isCalled = status === "called";
  const isError = status === "error";

  // ai-manus style: show function action label + primary arg inline
  const functionLabel = getToolFunctionLabel(functionName);
  const primaryArg = getToolFunctionArg(functionName, functionArgs);

  return (
    <View style={[styles.container, isCalling && styles.containerCalling, isError && styles.containerError]}>
      <TouchableOpacity
        style={styles.header}
        onPress={() => setExpanded(!expanded)}
        activeOpacity={0.7}
      >
        <View style={styles.headerLeft}>
          <ToolIcon name={functionName} />
          <Text style={styles.toolLabel}>{functionLabel}</Text>
          {primaryArg ? (
            <Text style={styles.primaryArg} numberOfLines={1}>
              <Text style={styles.primaryArgCode}>{primaryArg}</Text>
            </Text>
          ) : null}
        </View>
        <View style={styles.headerRight}>
          {isCalling && (
            <Ionicons name="sync" size={12} color="#6C5CE7" />
          )}
          {isCalled && (
            <Ionicons name="checkmark-circle" size={14} color="#30D158" />
          )}
          {isError && (
            <Ionicons name="close-circle" size={14} color="#FF453A" />
          )}
          <Ionicons
            name={expanded ? "chevron-up" : "chevron-down"}
            size={14}
            color="#636366"
          />
        </View>
      </TouchableOpacity>

      {/* Expanded content */}
      {expanded && (
        <View style={styles.expandedContent}>
          {/* Args */}
          <View style={styles.argsContainer}>
            <Text style={styles.argsLabel}>Arguments:</Text>
            {Object.entries(functionArgs).map(([key, val]) => (
              <Text key={key} style={styles.argItem}>
                {key}: {String(val).slice(0, 200)}
              </Text>
            ))}
          </View>

          {/* Tool content - show for both called and error states */}
          {toolContent && (isCalled || isError) && (
            <View style={styles.resultContainer}>
              {toolContent.type === "shell" && toolContent.console != null && (
                <ShellContent content={toolContent.console} />
              )}
              {toolContent.type === "search" && toolContent.results && (
                <SearchContent results={toolContent.results} />
              )}
              {toolContent.type === "browser" && (
                <BrowserContent
                  title={toolContent.title}
                  content={toolContent.content}
                />
              )}
              {toolContent.type === "file" && toolContent.content != null && (
                <FileContent content={toolContent.content} />
              )}
              {toolContent.type === "mcp" && toolContent.result != null && (
                <View style={styles.shellContainer}>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                    <Text style={styles.shellText} selectable>
                      {toolContent.result || "(no result)"}
                    </Text>
                  </ScrollView>
                </View>
              )}
            </View>
          )}

          {/* Function result text fallback */}
          {!toolContent && functionResult && (isCalled || isError) && (
            <View style={styles.resultContainer}>
              <View style={styles.shellContainer}>
                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                  <Text style={[styles.shellText, isError && styles.errorResultText]} selectable numberOfLines={10}>
                    {functionResult.slice(0, 500)}
                  </Text>
                </ScrollView>
              </View>
            </View>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#141418",
    borderRadius: 15,
    paddingHorizontal: 10,
    paddingVertical: 6,
    marginVertical: 2,
    borderWidth: 1,
    borderColor: "#2C2C30",
  },
  containerCalling: {
    borderColor: "rgba(108, 92, 231, 0.3)",
    backgroundColor: "rgba(108, 92, 231, 0.04)",
  },
  containerError: {
    borderColor: "rgba(255, 69, 58, 0.3)",
    backgroundColor: "rgba(255, 69, 58, 0.04)",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  headerLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    flex: 1,
    minWidth: 0,
  },
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  toolLabel: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 13,
    color: "#E8E8ED",
  },
  primaryArg: {
    flex: 1,
    minWidth: 0,
  },
  primaryArgCode: {
    fontFamily: "monospace",
    fontSize: 12,
    color: "#8E8E93",
  },
  errorResultText: {
    color: "#FF6B6B",
  },
  expandedContent: {
    marginTop: 8,
    gap: 8,
  },
  argsContainer: {
    backgroundColor: "#1A1A20",
    borderRadius: 6,
    padding: 8,
  },
  argsLabel: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 11,
    color: "#8E8E93",
    marginBottom: 4,
  },
  argItem: {
    fontFamily: "Inter_400Regular",
    fontSize: 11,
    color: "#A0A0A8",
    lineHeight: 16,
  },
  resultContainer: {
    marginTop: 4,
  },
  shellContainer: {
    backgroundColor: "#0D0D10",
    borderRadius: 6,
    padding: 8,
    maxHeight: 150,
  },
  shellText: {
    fontFamily: "monospace",
    fontSize: 11,
    color: "#30D158",
    lineHeight: 16,
  },
  searchContainer: {
    gap: 6,
  },
  searchResult: {
    backgroundColor: "#1A1A20",
    borderRadius: 6,
    padding: 8,
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
    marginTop: 2,
  },
  searchSnippet: {
    fontFamily: "Inter_400Regular",
    fontSize: 11,
    color: "#A0A0A8",
    marginTop: 4,
    lineHeight: 16,
  },
  browserContainer: {
    backgroundColor: "#1A1A20",
    borderRadius: 6,
    padding: 8,
    maxHeight: 150,
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
  fileContainer: {
    backgroundColor: "#0D0D10",
    borderRadius: 6,
    padding: 8,
    maxHeight: 150,
  },
  fileText: {
    fontFamily: "monospace",
    fontSize: 11,
    color: "#FFD60A",
    lineHeight: 16,
  },
});
