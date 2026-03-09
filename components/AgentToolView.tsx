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
      return <Ionicons name="globe" size={14} color="#FF9F0A" />;
    case "file_read":
    case "file_write":
    case "file_find":
      return <Ionicons name="document-text" size={14} color="#FFD60A" />;
    case "message_notify":
      return <Ionicons name="chatbubble" size={14} color="#BF5AF2" />;
    default:
      return <Ionicons name="construct" size={14} color="#8E8E93" />;
  }
}

function ToolLabel({ name }: { name: string }) {
  const labels: Record<string, string> = {
    shell_exec: "Shell",
    web_search: "Web Search",
    web_browse: "Browse URL",
    file_read: "Read File",
    file_write: "Write File",
    file_find: "Find Files",
    message_notify: "Notification",
  };
  return (
    <Text style={styles.toolLabel}>{labels[name] || name}</Text>
  );
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

  // Get a brief summary of the args
  const argsSummary = Object.entries(functionArgs)
    .map(([key, val]) => {
      const strVal = String(val);
      return `${key}: ${strVal.length > 60 ? strVal.slice(0, 60) + "..." : strVal}`;
    })
    .join(", ");

  return (
    <View style={[styles.container, isCalling && styles.containerCalling]}>
      <TouchableOpacity
        style={styles.header}
        onPress={() => setExpanded(!expanded)}
        activeOpacity={0.7}
      >
        <View style={styles.headerLeft}>
          <ToolIcon name={functionName} />
          <ToolLabel name={functionName} />
          {isCalling && (
            <Ionicons name="sync" size={12} color="#6C5CE7" />
          )}
          {isCalled && (
            <Ionicons name="checkmark" size={12} color="#30D158" />
          )}
        </View>
        <Ionicons
          name={expanded ? "chevron-up" : "chevron-down"}
          size={14}
          color="#636366"
        />
      </TouchableOpacity>

      {/* Brief args display */}
      {!expanded && argsSummary && (
        <Text style={styles.argsSummary} numberOfLines={1}>
          {argsSummary}
        </Text>
      )}

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

          {/* Tool content */}
          {toolContent && isCalled && (
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
    borderRadius: 10,
    padding: 10,
    marginVertical: 2,
    borderWidth: 1,
    borderColor: "#2C2C30",
  },
  containerCalling: {
    borderColor: "rgba(108, 92, 231, 0.3)",
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
  },
  toolLabel: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 12,
    color: "#E8E8ED",
  },
  argsSummary: {
    fontFamily: "Inter_400Regular",
    fontSize: 11,
    color: "#636366",
    marginTop: 4,
    paddingLeft: 22,
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
