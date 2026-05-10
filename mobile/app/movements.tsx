import { useEffect, useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  SafeAreaView,
  Alert,
  ActivityIndicator,
} from "react-native";
import { api } from "@/lib/api";

type Item = { id: number; sku: string; name: string; stock_qty: string };

export default function MovementScreen() {
  const [items, setItems] = useState<Item[]>([]);
  const [itemId, setItemId] = useState<number | null>(null);
  const [type, setType] = useState<"inbound" | "outbound">("inbound");
  const [qty, setQty] = useState("0");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = async () => {
    try {
      const r = await api<{ items: Item[] }>("/api/inventory/items?page=1&size=200");
      setItems(r.items);
      if (r.items[0] && itemId == null) setItemId(r.items[0].id);
    } catch (e: any) {
      setMsg(String(e?.message ?? e));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const submit = async () => {
    if (!itemId || Number(qty) <= 0) {
      Alert.alert("입력 오류", "품목과 수량을 확인하세요");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      await api("/api/inventory/movements", {
        method: "POST",
        body: JSON.stringify({
          item_id: itemId,
          type,
          quantity: Number(qty),
        }),
      });
      setMsg("저장됨 ✓");
      setQty("0");
      await load();
    } catch (e: any) {
      Alert.alert("저장 실패", String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.container}>
        <Text style={styles.h1}>재고 입출고</Text>

        <Text style={styles.label}>품목</Text>
        <View style={styles.list}>
          {items.map((i) => (
            <Pressable
              key={i.id}
              style={[
                styles.item,
                itemId === i.id && styles.itemActive,
              ]}
              onPress={() => setItemId(i.id)}
            >
              <Text style={styles.itemTitle}>{i.name}</Text>
              <Text style={styles.itemSub}>
                {i.sku} · 재고 {i.stock_qty}
              </Text>
            </Pressable>
          ))}
        </View>

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

        {msg ? <Text style={styles.msg}>{msg}</Text> : null}

        <Pressable style={styles.btn} onPress={submit} disabled={busy}>
          {busy ? (
            <ActivityIndicator color="white" />
          ) : (
            <Text style={styles.btnText}>저장</Text>
          )}
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#f0fdf4" },
  container: { padding: 16, gap: 8 },
  h1: { fontSize: 20, fontWeight: "700", color: "#14532d", marginBottom: 8 },
  label: { fontSize: 13, color: "#475569", marginTop: 8 },
  list: { gap: 6 },
  item: {
    backgroundColor: "white",
    padding: 10,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "#bbf7d0",
  },
  itemActive: { borderColor: "#15803d", backgroundColor: "#dcfce7" },
  itemTitle: { fontSize: 14, fontWeight: "600", color: "#0f172a" },
  itemSub: { fontSize: 12, color: "#64748b" },
  row: { flexDirection: "row", gap: 8 },
  toggle: {
    flex: 1,
    padding: 10,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "#bbf7d0",
    alignItems: "center",
    backgroundColor: "white",
  },
  toggleActive: { backgroundColor: "#15803d", borderColor: "#15803d" },
  toggleText: { color: "#0f172a", fontWeight: "600" },
  toggleActiveText: { color: "white", fontWeight: "600" },
  input: {
    backgroundColor: "white",
    borderWidth: 1,
    borderColor: "#bbf7d0",
    borderRadius: 6,
    padding: 10,
    fontSize: 16,
  },
  btn: {
    marginTop: 16,
    backgroundColor: "#15803d",
    paddingVertical: 14,
    borderRadius: 6,
    alignItems: "center",
  },
  btnText: { color: "white", fontWeight: "600", fontSize: 15 },
  msg: { color: "#16a34a", marginTop: 4 },
});
