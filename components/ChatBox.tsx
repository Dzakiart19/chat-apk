import React, { useRef } from "react";
import {
  View,
  TextInput,
  StyleSheet,
  TouchableOpacity,
  Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { ChatAttachment } from "@/lib/chat";

interface ChatBoxProps {
  value: string;
  onChangeText: (text: string) => void;
  onSubmit: () => void;
  onStop?: () => void;
  isLoading?: boolean;
  isAgentMode?: boolean;
  attachments?: ChatAttachment[];
}

export function ChatBox({
  value,
  onChangeText,
  onSubmit,
  onStop,
  isLoading = false,
  isAgentMode = false,
  attachments = [],
}: ChatBoxProps) {
  const inputRef = useRef<TextInput>(null);

  const canSend = value.trim().length > 0 && !isLoading;

  return (
    <View style={styles.container}>
      <View style={styles.inputWrapper}>
        <TextInput
          ref={inputRef}
          style={styles.input}
          placeholder={
            isAgentMode
              ? "Pesan untuk Agent AI..."
              : "Kirim pesan ke Dzeck AI..."
          }
          placeholderTextColor="#636366"
          value={value}
          onChangeText={onChangeText}
          multiline
          maxLength={4000}
          editable={!isLoading}
          onSubmitEditing={Platform.OS === "web" ? onSubmit : undefined}
          blurOnSubmit={false}
        />
      </View>

      <View style={styles.toolbar}>
        <View style={styles.toolbarLeft}>
          {isAgentMode && (
            <Ionicons name="flash" size={18} color="#6C5CE7" style={styles.modeIcon} />
          )}
        </View>

        <View style={styles.toolbarRight}>
          {isLoading ? (
            <TouchableOpacity onPress={onStop} style={styles.toolbarBtn} activeOpacity={0.6}>
              <View style={styles.stopIcon}>
                <Ionicons name="stop" size={14} color="#FFFFFF" />
              </View>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity
              onPress={onSubmit}
              style={[styles.toolbarBtn, !canSend && styles.sendButtonDisabled]}
              activeOpacity={0.6}
              disabled={!canSend}
            >
              <View style={[styles.sendIconContainer, !canSend && styles.sendIconDisabled]}>
                <Ionicons name="arrow-up" size={16} color="#FFFFFF" />
              </View>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#0A0A0C",
    paddingBottom: Platform.OS === "ios" ? 20 : 8,
    paddingHorizontal: 12,
  },
  inputWrapper: {
    backgroundColor: "#1A1A20",
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#2C2C30",
    paddingHorizontal: 16,
    paddingVertical: Platform.OS === "ios" ? 10 : 8,
    maxHeight: 120,
    marginBottom: 6,
  },
  input: {
    fontSize: 15,
    color: "#FFFFFF",
    maxHeight: 100,
    lineHeight: 20,
  },
  toolbar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  toolbarLeft: {
    flexDirection: "row",
    alignItems: "center",
  },
  toolbarRight: {
    flexDirection: "row",
    alignItems: "center",
  },
  toolbarBtn: {
    width: 36,
    height: 36,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 18,
  },
  modeIcon: {
    marginLeft: 4,
  },
  sendButtonDisabled: {
    opacity: 0.4,
  },
  sendIconContainer: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: "#6C5CE7",
    alignItems: "center",
    justifyContent: "center",
  },
  sendIconDisabled: {
    backgroundColor: "#2C2C30",
  },
  stopIcon: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: "#FF453A",
    alignItems: "center",
    justifyContent: "center",
  },
});
