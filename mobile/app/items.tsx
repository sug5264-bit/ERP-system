import { useEffect, useState } from "react";
import { FlatList, View, Text, StyleSheet, SafeAreaView } from "react-native";
import { api } from "@/lib/api";

type Item = {
  id: number;
  sku: string;
  name: string;
  unit_price: string;
  stock_qty: string;
};

export default function Items() {
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ items: Item[] }>("/api/inventory/items?page=1&size=50")
      .then((r) => setItems(r.items))
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <SafeAreaView style={styles.safe}>
      {error && <Text style={styles.error}>{error}</Text>}
      <FlatList
        data={items}
        keyExtractor={(i) => String(i.id)}
        renderItem={({ item }) => (
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.title}>{item.name}</Text>
              <Text style={styles.sub}>{item.sku}</Text>
            </View>
            <View style={{ alignItems: "flex-end" }}>
              <Text style={styles.qty}>재고 {item.stock_qty}</Text>
              <Text style={styles.price}>
                ₩{Number(item.unit_price).toLocaleString()}
              </Text>
            </View>
          </View>
        )}
        ItemSeparatorComponent={() => <View style={styles.sep} />}
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
  qty: { color: "#15803d", fontWeight: "600" },
  price: { color: "#475569", fontSize: 13 },
  sep: { height: 1, backgroundColor: "#e2e8f0" },
});
