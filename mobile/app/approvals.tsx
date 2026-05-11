import { useEffect, useState } from "react";
import { View, Text, StyleSheet, FlatList, Pressable, SafeAreaView, Alert } from "react-native";
import { api } from "@/lib/api";

type Approval = {
  id: number;
  title: string;
  resource_type: string;
  status: string;
  current_step: number;
};

export default function ApprovalsScreen() {
  const [rows, setRows] = useState<Approval[]>([]);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const r = await api<{ items: Approval[] }>("/api/approvals/requests?status=pending&page=1&size=50");
      setRows(r.items);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const decide = async (id: number, action: "approve" | "reject") => {
    try {
      await api(`/api/approvals/requests/${id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ comment: action === "approve" ? "승인" : "반려" }),
      });
      await load();
    } catch (e: any) {
      Alert.alert("실패", String(e?.message ?? e));
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.container}>
        <Text style={styles.h1}>결재 대기</Text>
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <FlatList
          data={rows}
          keyExtractor={(r) => String(r.id)}
          ListEmptyComponent={<Text style={styles.empty}>대기중인 결재가 없습니다</Text>}
          renderItem={({ item }) => (
            <View style={styles.card}>
              <Text style={styles.title}>{item.title}</Text>
              <Text style={styles.sub}>
                {item.resource_type} · 단계 {item.current_step}
              </Text>
              <View style={styles.row}>
                <Pressable
                  style={[styles.btn, styles.btnApprove]}
                  onPress={() => decide(item.id, "approve")}
                >
                  <Text style={styles.btnTextW}>승인</Text>
                </Pressable>
                <Pressable
                  style={[styles.btn, styles.btnReject]}
                  onPress={() => decide(item.id, "reject")}
                >
                  <Text style={styles.btnTextW}>반려</Text>
                </Pressable>
              </View>
            </View>
          )}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#f0fdf4" },
  container: { padding: 16, flex: 1 },
  h1: { fontSize: 20, fontWeight: "700", color: "#14532d", marginBottom: 8 },
  error: { color: "#b91c1c", marginBottom: 6 },
  empty: { color: "#64748b", marginTop: 40, textAlign: "center" },
  card: {
    backgroundColor: "white",
    padding: 12,
    borderRadius: 8,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: "#bbf7d0",
  },
  title: { fontSize: 15, fontWeight: "600", color: "#0f172a" },
  sub: { fontSize: 12, color: "#64748b", marginTop: 2 },
  row: { flexDirection: "row", gap: 8, marginTop: 10 },
  btn: { flex: 1, paddingVertical: 10, borderRadius: 6, alignItems: "center" },
  btnApprove: { backgroundColor: "#15803d" },
  btnReject: { backgroundColor: "#dc2626" },
  btnTextW: { color: "white", fontWeight: "600" },
});
