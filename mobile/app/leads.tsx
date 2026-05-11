import { useEffect, useState } from "react";
import {
  View, Text, TextInput, Pressable, StyleSheet, SafeAreaView,
  FlatList, Alert,
} from "react-native";
import { api } from "@/lib/api";

type Lead = {
  id: number;
  name: string;
  company: string | null;
  email: string | null;
  status: string;
};

export default function LeadsScreen() {
  const [rows, setRows] = useState<Lead[]>([]);
  const [form, setForm] = useState({ name: "", company: "", email: "", source: "mobile" });
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const r = await api<{ items: Lead[] }>("/api/crm/leads?page=1&size=50");
      setRows(r.items);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const submit = async () => {
    if (!form.name.trim()) {
      Alert.alert("입력 오류", "이름은 필수입니다");
      return;
    }
    try {
      await api("/api/crm/leads", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          company: form.company || null,
          email: form.email || null,
          source: form.source,
        }),
      });
      setForm({ name: "", company: "", email: "", source: "mobile" });
      await load();
    } catch (e: any) {
      Alert.alert("저장 실패", String(e?.message ?? e));
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.container}>
        <Text style={styles.h1}>CRM 리드</Text>
        {error ? <Text style={styles.error}>{error}</Text> : null}

        <View style={styles.form}>
          <TextInput
            placeholder="이름"
            value={form.name}
            onChangeText={(t) => setForm({ ...form, name: t })}
            style={styles.input}
          />
          <TextInput
            placeholder="회사"
            value={form.company}
            onChangeText={(t) => setForm({ ...form, company: t })}
            style={styles.input}
          />
          <TextInput
            placeholder="이메일"
            keyboardType="email-address"
            autoCapitalize="none"
            value={form.email}
            onChangeText={(t) => setForm({ ...form, email: t })}
            style={styles.input}
          />
          <Pressable style={styles.btn} onPress={submit}>
            <Text style={styles.btnText}>+ 리드 등록</Text>
          </Pressable>
        </View>

        <FlatList
          data={rows}
          keyExtractor={(r) => String(r.id)}
          renderItem={({ item }) => (
            <View style={styles.card}>
              <Text style={styles.title}>{item.name}</Text>
              <Text style={styles.sub}>
                {item.company || "-"} · {item.email || "-"} · {item.status}
              </Text>
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
  form: { gap: 8, marginBottom: 12 },
  input: {
    backgroundColor: "white",
    borderWidth: 1,
    borderColor: "#bbf7d0",
    borderRadius: 6,
    padding: 10,
    fontSize: 15,
  },
  btn: {
    backgroundColor: "#15803d",
    paddingVertical: 12,
    borderRadius: 6,
    alignItems: "center",
  },
  btnText: { color: "white", fontWeight: "600" },
  card: {
    backgroundColor: "white",
    padding: 10,
    borderRadius: 6,
    marginBottom: 6,
    borderWidth: 1,
    borderColor: "#bbf7d0",
  },
  title: { fontSize: 14, fontWeight: "600", color: "#0f172a" },
  sub: { fontSize: 12, color: "#64748b" },
});
