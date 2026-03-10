import React, { useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Animated,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { AgentEvent } from "@/lib/chat";
import { ToolDetailModal } from "./ToolDetailModal";

interface AgentToolCardProps {
  event: AgentEvent;
}

/** Tool group → icon name + color (ai-manus style) */
function getToolDisplay(functionName: string): {
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  label: string;
  argKey: string;
} {
  const map: Record<string, { icon: keyof typeof Ionicons.glyphMap; color: string; label: string; argKey: string }> = {
    shell_exec:           { icon: "terminal-outline",       color: "#34C759", label: "Executing command",    argKey: "command" },
    shell_view:           { icon: "terminal-outline",       color: "#34C759", label: "Viewing output",       argKey: "id" },
    shell_wait:           { icon: "time-outline",           color: "#34C759", label: "Waiting for process",  argKey: "id" },
    shell_write_to_process:{ icon: "terminal-outline",      color: "#34C759", label: "Writing to process",   argKey: "input" },
    shell_kill_process:   { icon: "close-circle-outline",   color: "#FF453A", label: "Killing process",      argKey: "id" },
    file_read:            { icon: "document-text-outline",  color: "#FFD60A", label: "Reading file",         argKey: "file" },
    file_write:           { icon: "save-outline",           color: "#FFD60A", label: "Writing file",         argKey: "file" },
    file_str_replace:     { icon: "create-outline",         color: "#FFD60A", label: "Editing file",         argKey: "file" },
    file_find_by_name:    { icon: "folder-open-outline",    color: "#FFD60A", label: "Finding file",         argKey: "path" },
    file_find_in_content: { icon: "search-outline",         color: "#FFD60A", label: "Searching content",    argKey: "file" },
    browser_navigate:     { icon: "globe-outline",          color: "#FF9F0A", label: "Navigating to page",   argKey: "url" },
    browser_view:         { icon: "eye-outline",            color: "#FF9F0A", label: "Viewing page",         argKey: "page" },
    browser_click:        { icon: "hand-left-outline",      color: "#FF9F0A", label: "Clicking element",     argKey: "element" },
    browser_input:        { icon: "create-outline",         color: "#FF9F0A", label: "Entering text",        argKey: "text" },
    browser_scroll_up:    { icon: "arrow-up-outline",       color: "#FF9F0A", label: "Scrolling up",         argKey: "page" },
    browser_scroll_down:  { icon: "arrow-down-outline",     color: "#FF9F0A", label: "Scrolling down",       argKey: "page" },
    browser_console_exec: { icon: "code-slash-outline",     color: "#FF9F0A", label: "Executing JS",         argKey: "code" },
    browser_console_view: { icon: "code-slash-outline",     color: "#FF9F0A", label: "Viewing console",      argKey: "console" },
    browser_restart:      { icon: "refresh-outline",        color: "#FF9F0A", label: "Restarting browser",   argKey: "url" },
    browser_save_image:   { icon: "image-outline",          color: "#FF9F0A", label: "Saving image",         argKey: "save_dir" },
    browser_move_mouse:   { icon: "locate-outline",         color: "#FF9F0A", label: "Moving mouse",         argKey: "position" },
    browser_press_key:    { icon: "keypad-outline",         color: "#FF9F0A", label: "Pressing key",         argKey: "key" },
    browser_select_option:{ icon: "list-outline",           color: "#FF9F0A", label: "Selecting option",     argKey: "option" },
    web_search:           { icon: "search-outline",         color: "#5AC8FA", label: "Searching web",        argKey: "query" },
    info_search_web:      { icon: "search-outline",         color: "#5AC8FA", label: "Searching web",        argKey: "query" },
    web_browse:           { icon: "globe-outline",          color: "#5AC8FA", label: "Browsing URL",         argKey: "url" },
    mcp_call_tool:        { icon: "extension-puzzle-outline",color: "#64D2FF",label: "Calling MCP tool",     argKey: "tool_name" },
    mcp_list_tools:       { icon: "list-outline",           color: "#64D2FF", label: "Listing MCP tools",    argKey: "" },
  };
  return map[functionName] || { icon: "construct-outline", color: "#8E8E93", label: functionName, argKey: "" };
}

function getPrimaryArg(functionName: string, args: Record<string, unknown>): string {
  const { argKey } = getToolDisplay(functionName);
  let val = argKey && args[argKey] ? String(args[argKey]) : "";
  if (!val) {
    const firstKey = Object.keys(args)[0];
    val = firstKey ? String(args[firstKey] ?? "") : "";
  }
  val = val.replace(/^\/home\/ubuntu\//, "");
  return val.length > 60 ? val.slice(0, 60) + "…" : val;
}

/** Pulsing dot spinner (ai-manus style) */
function PulsingDot({ color }: { color: string }) {
  const scale = useRef(new Animated.Value(1)).current;
  const opacity = useRef(new Animated.Value(0.6)).current;

  useEffect(() => {
    const anim = Animated.loop(
      Animated.parallel([
        Animated.sequence([
          Animated.timing(scale, { toValue: 1.4, duration: 700, useNativeDriver: true }),
          Animated.timing(scale, { toValue: 1, duration: 700, useNativeDriver: true }),
        ]),
        Animated.sequence([
          Animated.timing(opacity, { toValue: 1, duration: 700, useNativeDriver: true }),
          Animated.timing(opacity, { toValue: 0.4, duration: 700, useNativeDriver: true }),
        ]),
      ]),
    );
    anim.start();
    return () => anim.stop();
  }, [scale, opacity]);

  return (
    <Animated.View style={{ transform: [{ scale }], opacity }}>
      <View style={[styles.dot, { backgroundColor: color }]} />
    </Animated.View>
  );
}

/**
 * ai-manus style tool card.
 * - message_notify_user / message_ask_user → plain text (no pill)
 * - all other tools → compact transparent pill
 * - tap pill → ToolDetailModal bottom sheet
 */
export function AgentToolCard({ event }: AgentToolCardProps) {
  const [modalVisible, setModalVisible] = useState(false);

  const functionName = event.function_name || "";
  const functionArgs = event.function_args || {};
  const isCalling = event.status === "calling";
  const isCalled = event.status === "called";
  const isError = event.status === "error";

  // Special case: message tool → render as plain text paragraph
  if (functionName === "message_notify_user" || functionName === "message_ask_user") {
    const msgText = String(functionArgs.text || functionArgs.message || "");
    if (msgText) {
      return (
        <View style={styles.messageTextWrapper}>
          <Text style={styles.messageText}>{msgText}</Text>
        </View>
      );
    }
    return null;
  }

  const { icon, color, label } = getToolDisplay(functionName);
  const primaryArg = getPrimaryArg(functionName, functionArgs);

  return (
    <>
      <View style={styles.wrapper}>
        <TouchableOpacity
          style={styles.pill}
          onPress={() => setModalVisible(true)}
          activeOpacity={0.65}
        >
          {/* Icon */}
          <Ionicons name={icon} size={15} color={color} />

          {/* Action label */}
          <Text style={styles.label}>{label}</Text>

          {/* Primary arg in code style */}
          {primaryArg ? (
            <View style={styles.argBadge}>
              <Text style={styles.argText} numberOfLines={1}>{primaryArg}</Text>
            </View>
          ) : null}

          {/* Status indicator */}
          <View style={styles.statusArea}>
            {isCalling && <PulsingDot color={color} />}
            {isCalled && <Ionicons name="checkmark-circle" size={13} color="#34C759" />}
            {isError && <Ionicons name="close-circle" size={13} color="#FF453A" />}
          </View>
        </TouchableOpacity>
      </View>

      <ToolDetailModal
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        functionName={functionName}
        functionArgs={functionArgs}
        label={label}
        icon={icon}
        iconColor={color}
        status={event.status || "called"}
        toolContent={event.tool_content}
        functionResult={event.function_result}
      />
    </>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    paddingHorizontal: 16,
    paddingVertical: 2,
    paddingLeft: 16,
    alignItems: "flex-start",
  },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(255,255,255,0.04)",
    maxWidth: "100%",
  },
  label: {
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: "rgba(255,255,255,0.75)",
  },
  argBadge: {
    backgroundColor: "rgba(255,255,255,0.08)",
    borderRadius: 5,
    paddingHorizontal: 5,
    paddingVertical: 1,
    maxWidth: 180,
    overflow: "hidden",
  },
  argText: {
    fontFamily: "monospace",
    fontSize: 11,
    color: "rgba(255,255,255,0.45)",
  },
  statusArea: {
    width: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  messageTextWrapper: {
    paddingHorizontal: 16,
    paddingVertical: 4,
  },
  messageText: {
    fontFamily: "Inter_400Regular",
    fontSize: 14,
    color: "rgba(255,255,255,0.65)",
    lineHeight: 21,
  },
});
