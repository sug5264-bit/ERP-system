import { useState } from "react";
import {
  View, Text, TextInput, Pressable, StyleSheet, SafeAreaView,
  Alert, ActivityIndicator,
} from "react-native";
import { api } from "@/lib/api";

type Item = {
  id: number;
  sku: string;
  name: string;
  barcode: string;
  stock_qty: number;
};

export default function ScanScreen() {
  const [barcode, setBarcode] = useState("");
  const [item, setItem] = useState<Item | null>(null);
  const [qty, setQty] = useState("1");
  const [type, setType] = useState<"inbound" | "outbound">("outbound");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const lookup = async () => {
    if (!barcode.trim()) return;
    setError("");
    setItem(null);
    try {
      const it = await api<Item>(`/api/inventory/scan/${encodeURIComponent(barcode.trim())}`);
      setItem(it);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    }
  };

  const submit = async () => {
    if (!item || Number(qty) <= 0) {
      Alert.alert("입력 오류", "품목과 수량을 확인하세요");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const params = new URLSearchParams({
        barcode: item.barcode,
        movement_type: type,
        quantity: qty,
      });
      const res = await api<{ new_stock: number }>(
        `/api/inventory/scan-movement?${params}`,
        { method: "POST" }
      );
      Alert.alert("완료", `새 재고: ${res.new_stock}`);
      setQty("1");
      // Re-lookup to refresh stock
      await lookup();
    } catch (e: any) {
      Alert.alert("실패", String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.container}>
        <Text style={styles.h1}>바코드 스캔</Text>
        <Text style={styles.hint}>실제 배포 시 카메라 스캐너 통합 — 지금은 수동 입력</Text>
        {error ? <Text style={styles.error}>{error}</Text> : null}

        <TextInput
          placeholder="바코드 (예: 8801234567890)"
          value={barcode}
          onChangeText={setBarcode}
          autoCapitalize="none"
          style={styles.input}
        />
        <Pressable style={styles.btn} onPress={lookup}>
          <Text style={styles.btnText}>🔍 조회</Text>
        </Pressable>

        {item && (
          <View style={styles.card}>
            <Text style={styles.title}>{item.name}</Text>
            <Text style={styles.sub}>SKU {item.sku} · 재고 {item.stock_qty}</Text>

            <Text style={styles.label}>유형</Text>
            <View style={styles.row}>
              {(["inbound", "outbound"] as const).map((t) => (
                <Pressable
                  key={t}
                  style={[styles.toggle, type === t && styles.toggleActive]}
                  onPress={() => setType(t)}
                >
                  <Text style={type === t ? styles.toggleActiveText : styles.toggleText}>
                    {t === "inbound" ? "입고" : "출고"}
                  </Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.label}>수량</Text>
            <TextInput
              keyboardType="numeric"
              value={qty}
              onChangeText={setQty}
              style={styles.input}
            />

            <Pressable style={styles.btnPrimary} onPress={submit} disabled={busy}>
              {busy ? (
                <ActivityIndicator color="white" />
              ) : (
                <Text style={styles.btnText}>저장</Text>
              )}
            </Pressable>
          </View>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#f0fdf4" },
  container: { padding: 16, gap: 8 },
  h1: { fontSize: 20, fontWeight: "700", color: "#14532d" },
  hint: { fontSize: 12, color: "#64748b", marginBottom: 8 },
  error: { color: "#b91c1c", marginBottom: 4 },
  input: {
    backgroundColor: "white",
    borderWidth: 1,
    borderColor: "#bbf7d0",
    borderRadius: 6,
    padding: 10,
    fontSize: 16,
  },
  label: { fontSize: 13, color: "#475569", marginTop: 8 },
  card: {
    backgroundColor: "white",
    padding: 12,
    borderRadius: 8,
    marginTop: 12,
    borderWidth: 1,
    borderColor: "#bbf7d0",
    gap: 8,
  },
  title: { fontSize: 16, fontWeight: "700", color: "#0f172a" },
  sub: { fontSize: 13, color: "#64748b" },
  row: { flexDirection: "row", gap: 8 },
  toggle: {
    flex: 1, padding: 10, borderRadius: 6, borderWidth: 1,
    borderColor: "#bbf7d0", alignItems: "center", backgroundColor: "white",
  },
  toggleActive: { backgroundColor: "#15803d", borderColor: "#15803d" },
  toggleText: { color: "#0f172a", fontWeight: "600" },
  toggleActiveText: { color: "white", fontWeight: "600" },
  btn: {
    backgroundColor: "#15803d", paddingVertical: 12, borderRadius: 6,
    alignItems: "center",
  },
  btnPrimary: {
    backgroundColor: "#15803d", paddingVertical: 14, borderRadius: 6,
    alignItems: "center", marginTop: 8,
  },
  btnText: { color: "white", fontWeight: "600", fontSize: 15 },
});
