import React, { useState, useRef, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Image,
  Modal,
  SafeAreaView,
  StatusBar,
  Animated,
  Dimensions,
  ScrollView,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { AgentPlan } from "@/lib/chat";

const { width: SCREEN_WIDTH } = Dimensions.get("window");

interface BrowserState {
  url: string;
  title: string;
  content: string;
  screenshot?: string;
  isLoading: boolean;
}

interface ComputerViewProps {
  browserState: BrowserState | null;
  plan?: AgentPlan | null;
  onClose?: () => void;
}

function LiveIndicator() {
  const opacity = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.3, duration: 800, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1, duration: 800, useNativeDriver: true }),
      ]),
    ).start();
  }, [opacity]);
  return (
    <View style={styles.liveRow}>
      <Animated.View style={[styles.liveDot, { opacity }]} />
      <Text style={styles.liveText}>Live</Text>
    </View>
  );
}

function PlanBottomBar({ plan }: { plan: AgentPlan }) {
  const [expanded, setExpanded] = useState(false);
  const completedCount = plan.steps.filter((s) => s.status === "completed").length;
  const totalCount = plan.steps.length;
  const currentStep = plan.steps.find((s) => s.status === "running") ||
    plan.steps[plan.steps.length - 1];

  return (
    <View style={styles.planBar}>
      <TouchableOpacity
        style={styles.planBarHeader}
        onPress={() => setExpanded(!expanded)}
        activeOpacity={0.7}
      >
        <View style={styles.planBarLeft}>
          <Ionicons
            name={completedCount === totalCount ? "checkmark-circle" : "layers-outline"}
            size={15}
            color={completedCount === totalCount ? "#30D158" : "#8E8E93"}
          />
          <Text style={styles.planBarTitle} numberOfLines={1}>
            {currentStep?.description || plan.title || "Menjalankan tugas"}
          </Text>
        </View>
        <View style={styles.planBarRight}>
          <Text style={styles.planBarCount}>
            {completedCount} / {totalCount}
          </Text>
          <Ionicons
            name={expanded ? "chevron-down" : "chevron-up"}
            size={13}
            color="#636366"
          />
        </View>
      </TouchableOpacity>

      {expanded && (
        <View style={styles.planBarSteps}>
          {plan.steps.map((step, i) => (
            <View key={step.id || i} style={styles.planBarStep}>
              <Ionicons
                name={
                  step.status === "completed"
                    ? "checkmark-circle"
                    : step.status === "running"
                    ? "radio-button-on"
                    : step.status === "failed"
                    ? "close-circle"
                    : "radio-button-off"
                }
                size={13}
                color={
                  step.status === "completed"
                    ? "#30D158"
                    : step.status === "running"
                    ? "#6C5CE7"
                    : step.status === "failed"
                    ? "#FF453A"
                    : "#3A3A3F"
                }
              />
              <Text
                style={[
                  styles.planBarStepText,
                  step.status === "completed" && styles.planBarStepDone,
                  step.status === "running" && styles.planBarStepRunning,
                ]}
                numberOfLines={1}
              >
                {step.description}
              </Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

function FullScreenBrowser({
  browserState,
  plan,
  onClose,
}: {
  browserState: BrowserState;
  plan?: AgentPlan | null;
  onClose?: () => void;
}) {
  return (
    <View style={styles.fullContainer}>
      <StatusBar barStyle="light-content" backgroundColor="#000000" />

      {/* Header */}
      <SafeAreaView style={styles.fullHeader}>
        <View style={styles.fullHeaderInner}>
          <TouchableOpacity onPress={onClose} style={styles.headerCloseBtn} activeOpacity={0.7}>
            <Ionicons name="close" size={20} color="#FFFFFF" />
          </TouchableOpacity>
          <Text style={styles.fullHeaderTitle}>Komputer Manus</Text>
          <TouchableOpacity style={styles.headerCloseBtn} activeOpacity={0.7}>
            <Ionicons name="scan-outline" size={18} color="#8E8E93" />
          </TouchableOpacity>
        </View>
      </SafeAreaView>

      {/* Browser viewport */}
      <View style={styles.browserViewport}>
        {/* URL bar */}
        <View style={styles.browserUrlBar}>
          <Ionicons name="lock-closed" size={10} color="#34C759" />
          <Text style={styles.browserUrlText} numberOfLines={1}>
            {browserState.url || "about:blank"}
          </Text>
          {browserState.isLoading && (
            <Ionicons name="sync" size={12} color="#6C5CE7" />
          )}
        </View>

        {/* Screenshot or content */}
        <View style={styles.browserContent}>
          {browserState.screenshot ? (
            <Image
              source={{ uri: browserState.screenshot }}
              style={styles.browserScreenshot}
              resizeMode="cover"
            />
          ) : (
            <ScrollView style={styles.browserTextScroll}>
              {browserState.content ? (
                <Text style={styles.browserTextContent}>{browserState.content}</Text>
              ) : (
                <View style={styles.browserEmpty}>
                  <Ionicons name="globe-outline" size={56} color="#2A2A30" />
                  <Text style={styles.browserEmptyText}>
                    {browserState.isLoading ? "Memuat halaman..." : "Belum ada halaman"}
                  </Text>
                </View>
              )}
            </ScrollView>
          )}

          {/* "Ambil kendali" overlay button */}
          <View style={styles.takeControlOverlay}>
            <TouchableOpacity style={styles.takeControlBtn} activeOpacity={0.75}>
              <Ionicons name="camera-outline" size={15} color="#FFFFFF" />
              <Text style={styles.takeControlText}>Ambil kendali</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Bottom nav bar */}
        <View style={styles.navBar}>
          <TouchableOpacity style={styles.navBtn} activeOpacity={0.7}>
            <Ionicons name="play-skip-back" size={18} color="#8E8E93" />
          </TouchableOpacity>
          <LiveIndicator />
          <TouchableOpacity style={styles.navBtn} activeOpacity={0.7}>
            <Ionicons name="play-skip-forward" size={18} color="#8E8E93" />
          </TouchableOpacity>
        </View>
      </View>

      {/* Plan bottom bar */}
      {plan && plan.steps.length > 0 && (
        <PlanBottomBar plan={plan} />
      )}
    </View>
  );
}

export function ComputerView({ browserState, plan, onClose }: ComputerViewProps) {
  const [fullScreen, setFullScreen] = useState(false);

  if (!browserState) return null;

  return (
    <>
      {/* Compact inline card */}
      <TouchableOpacity
        style={styles.compactCard}
        onPress={() => setFullScreen(true)}
        activeOpacity={0.8}
      >
        <View style={styles.compactHeader}>
          <View style={styles.compactHeaderLeft}>
            <Ionicons name="desktop-outline" size={14} color="#FF9F0A" />
            <Text style={styles.compactTitle}>Komputer Manus</Text>
          </View>
          <View style={styles.compactHeaderRight}>
            {browserState.isLoading ? (
              <Ionicons name="sync" size={12} color="#6C5CE7" />
            ) : (
              <View style={styles.compactLiveDot} />
            )}
            <Ionicons name="expand-outline" size={13} color="#636366" />
          </View>
        </View>

        <View style={styles.compactBody}>
          {browserState.screenshot ? (
            <Image
              source={{ uri: browserState.screenshot }}
              style={styles.compactScreenshot}
              resizeMode="cover"
            />
          ) : (
            <View style={styles.compactNoScreenshot}>
              <Ionicons name="globe-outline" size={24} color="#2C2C30" />
            </View>
          )}
        </View>

        <View style={styles.compactFooter}>
          <Ionicons name="lock-closed" size={9} color="#34C759" />
          <Text style={styles.compactUrl} numberOfLines={1}>
            {browserState.url || "about:blank"}
          </Text>
        </View>
      </TouchableOpacity>

      {/* Full screen modal */}
      <Modal
        visible={fullScreen}
        animationType="slide"
        statusBarTranslucent
        onRequestClose={() => setFullScreen(false)}
      >
        <FullScreenBrowser
          browserState={browserState}
          plan={plan}
          onClose={() => setFullScreen(false)}
        />
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  // ─── Compact inline card ───────────────────────────────
  compactCard: {
    backgroundColor: "#111115",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#222228",
    overflow: "hidden",
    marginHorizontal: 16,
    marginVertical: 6,
  },
  compactHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: "#161619",
    borderBottomWidth: 1,
    borderBottomColor: "#1E1E24",
  },
  compactHeaderLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  compactTitle: {
    fontFamily: "Inter_500Medium",
    fontSize: 12,
    color: "#E8E8ED",
  },
  compactHeaderRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  compactLiveDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: "#30D158",
  },
  compactBody: {
    height: 120,
    backgroundColor: "#0A0A0F",
    overflow: "hidden",
  },
  compactScreenshot: {
    width: "100%",
    height: "100%",
  },
  compactNoScreenshot: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  compactFooter: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 5,
    backgroundColor: "#0D0D12",
  },
  compactUrl: {
    flex: 1,
    fontFamily: "monospace",
    fontSize: 10,
    color: "#636366",
  },

  // ─── Full screen modal ────────────────────────────────
  fullContainer: {
    flex: 1,
    backgroundColor: "#000000",
  },
  fullHeader: {
    backgroundColor: "#000000",
  },
  fullHeaderInner: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  headerCloseBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: "rgba(255,255,255,0.08)",
    alignItems: "center",
    justifyContent: "center",
  },
  fullHeaderTitle: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 15,
    color: "#FFFFFF",
    letterSpacing: -0.3,
  },
  browserViewport: {
    flex: 1,
    backgroundColor: "#1A1A1F",
    marginHorizontal: 12,
    borderRadius: 12,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "#2A2A30",
    marginBottom: 8,
  },
  browserUrlBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "#111116",
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderBottomWidth: 1,
    borderBottomColor: "#222228",
  },
  browserUrlText: {
    flex: 1,
    fontFamily: "monospace",
    fontSize: 11,
    color: "rgba(255,255,255,0.55)",
  },
  browserContent: {
    flex: 1,
    position: "relative",
  },
  browserScreenshot: {
    width: "100%",
    height: "100%",
  },
  browserTextScroll: {
    flex: 1,
    padding: 12,
  },
  browserTextContent: {
    fontFamily: "Inter_400Regular",
    fontSize: 12,
    color: "#C0C0C8",
    lineHeight: 18,
  },
  browserEmpty: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    paddingVertical: 60,
  },
  browserEmptyText: {
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: "#3A3A40",
  },
  // "Ambil kendali" overlay
  takeControlOverlay: {
    position: "absolute",
    bottom: 16,
    left: 0,
    right: 0,
    alignItems: "center",
  },
  takeControlBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(0,0,0,0.72)",
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 9,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
  },
  takeControlText: {
    fontFamily: "Inter_500Medium",
    fontSize: 13,
    color: "#FFFFFF",
  },
  // Bottom nav bar
  navBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 24,
    paddingVertical: 10,
    backgroundColor: "#111116",
    borderTopWidth: 1,
    borderTopColor: "#222228",
  },
  navBtn: {
    padding: 4,
  },
  liveRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  liveDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: "#30D158",
  },
  liveText: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 13,
    color: "#FFFFFF",
  },

  // ─── Plan bottom bar ──────────────────────────────────
  planBar: {
    backgroundColor: "#111115",
    borderTopWidth: 1,
    borderTopColor: "#222228",
    paddingBottom: 8,
  },
  planBarHeader: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 10,
    gap: 8,
  },
  planBarLeft: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  planBarTitle: {
    flex: 1,
    fontFamily: "Inter_500Medium",
    fontSize: 13,
    color: "#E8E8ED",
    letterSpacing: -0.2,
  },
  planBarRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  planBarCount: {
    fontFamily: "Inter_400Regular",
    fontSize: 12,
    color: "#636366",
  },
  planBarSteps: {
    paddingHorizontal: 16,
    paddingBottom: 6,
    gap: 6,
  },
  planBarStep: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  planBarStepText: {
    flex: 1,
    fontFamily: "Inter_400Regular",
    fontSize: 12,
    color: "#636366",
    lineHeight: 17,
  },
  planBarStepDone: {
    color: "#444450",
  },
  planBarStepRunning: {
    color: "#E8E8ED",
  },
});
