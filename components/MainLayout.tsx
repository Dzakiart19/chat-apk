import React, { useState, useCallback } from "react";
import {
  View,
  StyleSheet,
  Dimensions,
  Platform,
  SafeAreaView,
} from "react-native";
import { LeftPanel } from "./LeftPanel";
import { ChatPage } from "./ChatPage";
import { ToolPanel } from "./ToolPanel";

interface MainLayoutProps {
  sessionId?: string;
}

export function MainLayout({ sessionId: initialSessionId }: MainLayoutProps) {
  const [isLeftPanelShow, setIsLeftPanelShow] = useState(true);
  const [toolPanelWidth, setToolPanelWidth] = useState(0);
  const [sessionId, setSessionId] = useState(initialSessionId);

  const toggleLeftPanel = useCallback(() => {
    setIsLeftPanelShow(!isLeftPanelShow);
  }, [isLeftPanelShow]);

  const handleNewSession = useCallback((newSessionId: string) => {
    setSessionId(newSessionId);
  }, []);

  const handleToolPanelResize = useCallback((width: number) => {
    setToolPanelWidth(width);
  }, []);

  const screenWidth = Dimensions.get("window").width;
  const leftPanelWidth = isLeftPanelShow ? 300 : 0;
  const chatAreaWidth = screenWidth - leftPanelWidth - toolPanelWidth;

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.mainContainer}>
        {/* Left Panel - Session List */}
        <View
          style={[
            styles.leftPanel,
            {
              width: leftPanelWidth,
              display: isLeftPanelShow ? "flex" : "none",
            },
          ]}
        >
          <LeftPanel
            isOpen={isLeftPanelShow}
            onToggle={toggleLeftPanel}
            onNewSession={handleNewSession}
          />
        </View>

        {/* Chat Area */}
        <View style={[styles.chatArea, { width: chatAreaWidth }]}>
          <ChatPage
            sessionId={sessionId}
            isLeftPanelShow={isLeftPanelShow}
            onToggleLeftPanel={toggleLeftPanel}
          />
        </View>

        {/* Tool Panel - Right Side */}
        {toolPanelWidth > 0 && (
          <View style={[styles.toolPanel, { width: toolPanelWidth }]}>
            <ToolPanel
              sessionId={sessionId}
              onResize={handleToolPanelResize}
            />
          </View>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0A0A0C",
  },
  mainContainer: {
    flex: 1,
    flexDirection: "row",
    backgroundColor: "#0A0A0C",
  },
  leftPanel: {
    backgroundColor: "#1A1A20",
    borderRightWidth: 1,
    borderRightColor: "#2C2C30",
    overflow: "hidden",
  },
  chatArea: {
    flex: 1,
    backgroundColor: "#0A0A0C",
  },
  toolPanel: {
    backgroundColor: "#1A1A20",
    borderLeftWidth: 1,
    borderLeftColor: "#2C2C30",
    overflow: "hidden",
  },
});
