import { useEffect, useState } from "react";
import { useRouter } from "expo-router";
import { View, Text, StyleSheet, Pressable, SafeAreaView } from "react-native";
import { api, clearToken, getToken } from "@/lib/api";

type Summary = {
  employees: number;
  items: number;
  low_stock: number;
  orders: number;
  open_orders: number;
  total_sales: number;
};

export default function Dashboard() {
  const router = useRouter();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      const token = await getToken();
      if (!token) {
        router.replace("/login");
        return;
      }
      try {
        setSummary(await api<Summary>("/api/reports/summary"));
      } catch (e) {
        setError(String(e));
        await clearToken();
        router.replace("/login");
      }
    })();
  }, []);

  const logout = async () => {
    await clearToken();
    router.replace("/login");
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.container}>
        <Text style={styles.h1}>대시보드</Text>
        {error && <Text style={styles.error}>{error}</Text>}
        {summary && (
          <View style={styles.grid}>
            <Card label="직원" value={summary.employees} />
            <Card label="품목" value={summary.items} />
            <Card label="재고 부족" value={summary.low_stock} highlight />
            <Card label="주문" value={summary.orders} />
            <Card label="미확정" value={summary.open_orders} />
            <Card
              label="총 매출"
              value={summary.total_sales.toLocaleString()}
            />
          </View>
        )}

        <Pressable style={styles.btn} onPress={() => router.push("/items")}>
          <Text style={styles.btnText}>📦 재고</Text>
        </Pressable>
        <Pressable style={styles.btn} onPress={() => router.push("/orders")}>
          <Text style={styles.btnText}>🛒 주문</Text>
        </Pressable>
        <Pressable style={[styles.btn, styles.btnGhost]} onPress={logout}>
          <Text style={styles.btnGhostText}>로그아웃</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

function Card({
  label,
  value,
  highlight,
}: {
  label: string;
  value: number | string;
  highlight?: boolean;
}) {
  return (
    <View style={[styles.card, highlight && styles.cardHi]}>
      <Text style={styles.cardLabel}>{label}</Text>
      <Text style={[styles.cardValue, highlight && styles.cardValueHi]}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#f0fdf4" },
  container: { padding: 16, gap: 12 },
  h1: { fontSize: 22, fontWeight: "700", color: "#14532d" },
  error: { color: "#b91c1c" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  card: {
    width: "48%",
    backgroundColor: "white",
    borderRadius: 8,
    padding: 12,
    borderWidth: 1,
    borderColor: "#bbf7d0",
  },
  cardHi: { borderColor: "#fecaca" },
  cardLabel: { color: "#64748b", fontSize: 12 },
  cardValue: { fontSize: 22, fontWeight: "700", color: "#0f172a", marginTop: 4 },
  cardValueHi: { color: "#b91c1c" },
  btn: {
    backgroundColor: "#15803d",
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: "center",
    marginTop: 8,
  },
  btnText: { color: "white", fontWeight: "600", fontSize: 15 },
  btnGhost: { backgroundColor: "transparent", borderWidth: 1, borderColor: "#15803d" },
  btnGhostText: { color: "#15803d", fontWeight: "600" },
});
