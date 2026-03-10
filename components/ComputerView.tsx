import React, { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Image,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface BrowserState {
  url: string;
  title: string;
  content: string;
  screenshot?: string;
  isLoading: boolean;
}

interface ComputerViewProps {
  browserState: BrowserState | null;
  onClose?: () => void;
}

/**
 * Computer/Browser view component - similar to ai-manus VNC viewer.
 * Shows the current state of the browser when browser tools are active.
 * Displays URL bar, page title, content preview, and optional screenshots.
 */
export function ComputerView({ browserState, onClose }: ComputerViewProps) {
  const [isMinimized, setIsMinimized] = useState(false);

  if (!browserState) return null;

  if (isMinimized) {
    return (
      <TouchableOpacity
        style={styles.minimizedBar}
        onPress={() => setIsMinimized(false)}
        activeOpacity={0.7}
      >
        <View style={styles.minimizedContent}>
          <View style={styles.minimizedDot} />
          <Ionicons name="globe-outline" size={14} color="#FF9F0A" />
          <Text style={styles.minimizedTitle} numberOfLines={1}>
            {browserState.title || browserState.url || "Browser"}
          </Text>
        </View>
        <Ionicons name="chevron-up" size={14} color="#636366" />
      </TouchableOpacity>
    );
  }

  return (
    <View style={styles.container}>
      {/* Title bar */}
      <View style={styles.titleBar}>
        <View style={styles.titleLeft}>
          <View style={styles.trafficLights}>
            <TouchableOpacity
              style={[styles.trafficLight, styles.trafficRed]}
              onPress={onClose}
            />
            <View style={[styles.trafficLight, styles.trafficYellow]} />
            <TouchableOpacity
              style={[styles.trafficLight, styles.trafficGreen]}
              onPress={() => setIsMinimized(true)}
            />
          </View>
          <Text style={styles.titleText} numberOfLines={1}>
            {browserState.title || "Browser"}
          </Text>
        </View>
        <View style={styles.titleRight}>
          {browserState.isLoading && (
            <Ionicons name="sync" size={14} color="#6C5CE7" />
          )}
        </View>
      </View>

      {/* URL bar */}
      <View style={styles.urlBar}>
        <Ionicons name="lock-closed" size={12} color="#30D158" />
        <Text style={styles.urlText} numberOfLines={1}>
          {browserState.url || "about:blank"}
        </Text>
      </View>

      {/* Content area */}
      <ScrollView
        style={styles.contentArea}
        contentContainerStyle={styles.contentInner}
        showsVerticalScrollIndicator={true}
      >
        {browserState.screenshot ? (
          <Image
            source={{ uri: browserState.screenshot }}
            style={styles.screenshot}
            resizeMode="contain"
          />
        ) : (
          <View style={styles.textContent}>
            {browserState.content ? (
              <Text style={styles.pageContent} selectable>
                {browserState.content}
              </Text>
            ) : (
              <View style={styles.emptyState}>
                <Ionicons name="globe-outline" size={48} color="#2C2C30" />
                <Text style={styles.emptyText}>
                  {browserState.isLoading ? "Loading page..." : "No content"}
                </Text>
              </View>
            )}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#0D0D10",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#222228",
    overflow: "hidden",
    maxHeight: 350,
    marginHorizontal: 16,
    marginVertical: 8,
  },
  titleBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#1A1A20",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#222228",
  },
  titleLeft: {
    flexDirection: "row",
    alignItems: "center",
    flex: 1,
    gap: 10,
  },
  titleRight: {
    marginLeft: 8,
  },
  trafficLights: {
    flexDirection: "row",
    gap: 6,
  },
  trafficLight: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  trafficRed: {
    backgroundColor: "#FF453A",
  },
  trafficYellow: {
    backgroundColor: "#FFD60A",
  },
  trafficGreen: {
    backgroundColor: "#30D158",
  },
  titleText: {
    fontFamily: "Inter_500Medium",
    fontSize: 12,
    color: "#8E8E93",
    flex: 1,
  },
  urlBar: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#141418",
    paddingHorizontal: 12,
    paddingVertical: 6,
    gap: 6,
    borderBottomWidth: 1,
    borderBottomColor: "#1E1E24",
  },
  urlText: {
    fontFamily: "monospace",
    fontSize: 11,
    color: "#A0A0A8",
    flex: 1,
  },
  contentArea: {
    maxHeight: 250,
  },
  contentInner: {
    padding: 12,
  },
  textContent: {
    minHeight: 80,
  },
  pageContent: {
    fontFamily: "Inter_400Regular",
    fontSize: 12,
    color: "#C0C0C8",
    lineHeight: 18,
  },
  screenshot: {
    width: "100%",
    height: 200,
    borderRadius: 6,
  },
  emptyState: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 32,
    gap: 8,
  },
  emptyText: {
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: "#3A3A40",
  },
  minimizedBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#141418",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    marginHorizontal: 16,
    marginVertical: 4,
    borderWidth: 1,
    borderColor: "#222228",
  },
  minimizedContent: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    flex: 1,
  },
  minimizedDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: "#30D158",
  },
  minimizedTitle: {
    fontFamily: "Inter_500Medium",
    fontSize: 12,
    color: "#8E8E93",
    flex: 1,
  },
});
