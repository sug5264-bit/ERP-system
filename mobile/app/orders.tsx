import { useEffect, useState } from "react";
import { FlatList, View, Text, StyleSheet, SafeAreaView } from "react-native";
import { api } from "@/lib/api";

type Order = {
  id: number;
  order_no: string;
  status: string;
  total: string;
  customer: { name: string } | null;
};

export default function Orders() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ items: Order[] }>("/api/sales/orders?page=1&size=50")
      .then((r) => setOrders(r.items))
      .catch((e) => setError(String(e)));
  }, []);

  const statusColor = (s: string) =>
    s === "confirmed" ? "#16a34a" : s === "cancelled" ? "#94a3b8" : "#d97706";

  return (
    <SafeAreaView style={styles.safe}>
      {error && <Text style={styles.error}>{error}</Text>}
      <FlatList
        data={orders}
        keyExtractor={(o) => String(o.id)}
        renderItem={({ item }) => (
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.title}>{item.order_no}</Text>
              <Text style={styles.sub}>{item.customer?.name ?? "-"}</Text>
            </View>
            <View style={{ alignItems: "flex-end" }}>
              <Text style={[styles.status, { color: statusColor(item.status) }]}>
                {item.status}
              </Text>
              <Text style={styles.amount}>
                ₩{Number(item.total).toLocaleString()}
              </Text>
            </View>
          </View>
        )}
        ItemSeparatorComponent={() => <View style={styles.sep} />}
        ListEmptyComponent={
          <Text style={{ padding: 16, color: "#64748b" }}>주문 없음</Text>
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "white" },
  error: { color: "#b91c1c", padding: 12 },
  row: { padding: 14, flexDirection: "row" },
  title: { fontSize: 15, fontWeight: "600", color: "#0f172a" },
  sub: { color: "#64748b", fontSize: 12, marginTop: 2 },
  status: { fontWeight: "600", textTransform: "uppercase", fontSize: 12 },
  amount: { color: "#475569", fontSize: 13, marginTop: 2 },
  sep: { height: 1, backgroundColor: "#e2e8f0" },
});
