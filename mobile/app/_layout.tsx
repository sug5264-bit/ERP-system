import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

export default function RootLayout() {
  return (
    <>
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: "#15803d" },
          headerTintColor: "#fff",
          headerTitleStyle: { fontWeight: "600" },
        }}
      >
        <Stack.Screen name="index" options={{ title: "WellGreen ERP" }} />
        <Stack.Screen name="login" options={{ title: "로그인" }} />
        <Stack.Screen name="items" options={{ title: "재고" }} />
        <Stack.Screen name="orders" options={{ title: "주문" }} />
        <Stack.Screen name="movements" options={{ title: "재고 입출고" }} />
      </Stack>
    </>
  );
}
